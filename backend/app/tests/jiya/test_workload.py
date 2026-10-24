"""R14 - faculty weekly-hour limits (hard) and workload balancing (soft) in generation, preview, detail and validation.

Seed reminder (60-minute periods): F001 teaches 8 theory sessions + one 2-period lab = 10 h; F002 6 h; F003 5 h; F004 6 h; F005 3 h; F006 6 h.
Every faculty member's seeded maximum is 18 h.
"""
from collections import defaultdict
from datetime import time
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models import AvailabilityStatus, ClassType, Faculty, FacultyAvailability, SlotType, TeachingAssignment, TimeSlot, Timetable, TimetableStatus
from app.modules.isha import workload_service as ws
from app.modules.jiya import generator
from app.modules.pragya import clash_service as cs
from app.tests.jiya.test_generation import assert_no_overlaps, entries, gen, term, unscheduled
from app.tests.pragya.helpers import faculty, sid

URL = "/api/v1/timetables"


@pytest.fixture()
def data(app, seeded):
    return None


def set_max(code, hours):
    faculty(code).max_weekly_hours = hours
    db.session.commit()


def minutes_of(timetable_id, code):
    return sum((db.session.get(TimeSlot, e.time_slot_id).end_time.hour * 60 + db.session.get(TimeSlot, e.time_slot_id).end_time.minute)
               - (db.session.get(TimeSlot, e.time_slot_id).start_time.hour * 60 + db.session.get(TimeSlot, e.time_slot_id).start_time.minute)
               for e in entries(timetable_id) if e.faculty_id == faculty(code).id)


def wl(result, code):
    return next(r for r in result["generation"]["workload"] if r["employee_code"] == code)


def shorten_class_slots(minutes):
    for s in db.session.scalars(db.select(TimeSlot).where(TimeSlot.slot_type == SlotType.CLASS)):
        total = s.start_time.hour * 60 + s.start_time.minute + minutes
        s.end_time = time(total // 60, total % 60)
    db.session.commit()


class TestWorkloadIsDuration:
    def test_theory_and_lab_hours_for_each_faculty(self, data):
        result = gen()
        expected = {"F001": 10, "F002": 6, "F003": 5, "F004": 6, "F005": 3, "F006": 6}
        assert {r["employee_code"]: r["scheduled_hours"] for r in result["generation"]["workload"]} == expected
        assert all(r["max_hours"] == 18 and r["overload_hours"] == 0 and r["status"] == "ok" for r in result["generation"]["workload"])

    def test_a_two_period_lab_counts_both_periods(self, data):
        for a in db.session.scalars(db.select(TeachingAssignment).where(TeachingAssignment.faculty_id == faculty("F003").id)).all():
            if a.subject.class_type == ClassType.THEORY:
                db.session.delete(a)
        db.session.commit()
        set_max("F003", 2)
        result = gen()
        assert wl(result, "F003")["scheduled_hours"] == 2 and wl(result, "F003")["status"] == "at_limit"
        assert len([e for e in entries(result["id"]) if e.faculty_id == faculty("F003").id]) == 2  # two entries, 2 hours

    def test_a_lab_that_does_not_fit_is_not_half_scheduled(self, data):
        for a in db.session.scalars(db.select(TeachingAssignment).where(TeachingAssignment.faculty_id == faculty("F003").id)).all():
            if a.subject.class_type == ClassType.THEORY:
                db.session.delete(a)
        db.session.commit()
        set_max("F003", 1)  # one period would fit by entry count, but the lab needs 2 hours
        result = gen()
        assert [e for e in entries(result["id"]) if e.faculty_id == faculty("F003").id] == []
        items = [i for i in unscheduled(result["id"]) if i.assignment.faculty_id == faculty("F003").id]
        assert [i.reason_code for i in items] == ["workload_limit"]
        assert "maximum of 1 h" in items[0].reason_text and "CS351" in items[0].reason_text

    def test_hours_use_the_real_slot_length_not_the_number_of_entries(self, data):
        shorten_class_slots(45)
        set_max("F001", 8)  # 10 periods of 45 min = 7.5 h fits; 10 entries would not fit "8 hours" if counted as hours
        result = gen()
        assert len([e for e in entries(result["id"]) if e.faculty_id == faculty("F001").id]) == 10
        assert wl(result, "F001")["scheduled_hours"] == 7.5 and wl(result, "F001")["status"] == "ok"
        assert result["generation"]["status"] == "complete"
        assert minutes_of(result["id"], "F001") == 450

    def test_mixed_period_lengths_are_summed_exactly(self, data):
        slot = db.session.get(TimeSlot, sid(0, 7))
        slot.end_time = time(16, 30)  # the last Monday period is now 90 minutes
        db.session.commit()
        assert ws.slot_minutes(slot) == 90
        result = gen()
        assert minutes_of(result["id"], "F001") / 60 == wl(result, "F001")["scheduled_hours"]


class TestDifferentLimits:
    def test_each_faculty_member_gets_their_own_limit(self, data):
        set_max("F005", 2)   # needs 3 h
        set_max("F001", 10)  # needs exactly 10 h
        set_max("F002", 12)
        result = gen()
        assert wl(result, "F005")["scheduled_hours"] == 2 and wl(result, "F001")["scheduled_hours"] == 10
        assert wl(result, "F001")["status"] == "at_limit" and wl(result, "F002")["max_hours"] == 12
        assert minutes_of(result["id"], "F005") == 120
        missing = unscheduled(result["id"])
        assert [(i.assignment.faculty.employee_code, i.reason_code) for i in missing] == [("F005", "workload_limit")]

    def test_no_limit_is_ever_exceeded(self, data):
        for code, hours in (("F001", 7), ("F002", 3), ("F003", 4), ("F004", 5), ("F005", 1), ("F006", 6)):
            set_max(code, hours)
        result = gen()
        for r in result["generation"]["workload"]:
            assert r["scheduled_hours"] <= r["max_hours"], r
        assert_no_overlaps(result["id"])
        assert cs.validate_timetable(result["id"]).is_valid
        assert result["generation"]["status"] == "partial" and result["generation"]["unscheduled_sessions"] > 0

    def test_every_session_is_scheduled_or_recorded_when_limits_bite(self, data):
        set_max("F001", 5)
        result = gen()
        g = result["generation"]
        assert g["scheduled_sessions"] + g["unscheduled_sessions"] == g["required_sessions"] == 32
        assert set(g["unscheduled_reasons"]) == {"workload_limit"}
        for i in unscheduled(result["id"]):
            assert len(i.reason_text) > 40 and "5 h" in i.reason_text


class TestOverAssignedWarning:
    def test_preview_flags_the_mismatch_before_generation(self, client, admin_headers):
        set_max("F005", 2)
        r = client.get(f"{URL}/workload-preview?term_id={term().id}", headers=admin_headers)
        body = r.get_json()["data"]
        row = next(x for x in body["workload"] if x["employee_code"] == "F005")
        assert row["status"] == "over_assigned" and row["assigned_hours"] == 3 and row["max_hours"] == 2 and row["over_assigned_hours"] == 1
        assert len(body["warnings"]) == 1 and "F005" not in body["warnings"][0] and "2 h" in body["warnings"][0] and "1 h too many" in body["warnings"][0]
        assert all(x["scheduled_hours"] == 0 for x in body["workload"])

    def test_preview_is_quiet_when_everything_fits(self, client, admin_headers):
        body = client.get(f"{URL}/workload-preview?term_id={term().id}", headers=admin_headers).get_json()["data"]
        assert body["warnings"] == [] and {x["status"] for x in body["workload"]} == {"ok"}

    def test_preview_does_not_create_anything(self, client, admin_headers):
        client.get(f"{URL}/workload-preview?term_id={term().id}", headers=admin_headers)
        assert Timetable.query.count() == 0

    def test_generation_repeats_the_warning_in_its_summary(self, client, admin_headers):
        set_max("F005", 2)
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        g = made["generation"]
        assert any("assigned at least 3 h" in w and "maximum is 2 h" in w for w in g["warnings"])
        assert next(r for r in g["workload"] if r["employee_code"] == "F005")["status"] == "at_limit"  # placed up to the limit

    def test_the_warning_uses_a_lower_bound_so_it_never_cries_wolf(self, client, admin_headers):
        shorten_class_slots(30)  # 3 h of F005 work is really 1.5 h
        set_max("F005", 2)
        body = client.get(f"{URL}/workload-preview?term_id={term().id}", headers=admin_headers).get_json()["data"]
        assert next(x for x in body["workload"] if x["employee_code"] == "F005")["status"] == "ok" and body["warnings"] == []

    def test_preview_validation(self, client, admin_headers):
        assert client.get(f"{URL}/workload-preview", headers=admin_headers).status_code == 400
        assert client.get(f"{URL}/workload-preview?term_id=x", headers=admin_headers).status_code == 400


class TestBalancingIsSoft:
    def test_a_persons_week_is_spread_across_days(self, data):
        result = gen()
        per_day = defaultdict(int)
        for e in entries(result["id"]):
            if e.faculty_id == faculty("F001").id:
                per_day[db.session.get(TimeSlot, e.time_slot_id).day_of_week] += 1
        assert len(per_day) == 5 and max(per_day.values()) <= 3, dict(per_day)

    def test_preference_cannot_override_the_hard_limit(self, data):
        f = faculty("F001")
        for p in range(1, 4):
            db.session.add(FacultyAvailability(faculty_id=f.id, time_slot_id=sid(0, p), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        set_max("F001", 4)
        result = gen()
        assert wl(result, "F001")["scheduled_hours"] <= 4 and cs.validate_timetable(result["id"]).is_valid

    def test_balancing_never_breaks_a_hard_rule(self, data):
        result = gen()
        assert_no_overlaps(result["id"])
        assert cs.validate_timetable(result["id"]).is_valid and result["generation"]["status"] == "complete"

    def test_a_session_is_not_dropped_just_to_improve_balance(self, data):
        result = gen()
        assert result["generation"]["scheduled_sessions"] == 32


class TestMissingOrUnsetLimits:
    @pytest.mark.parametrize("value", [None, 0, -3, True, "18"])
    def test_a_missing_or_invalid_limit_means_no_limit_not_a_default(self, value):
        assert ws.limit_minutes(SimpleNamespace(max_weekly_hours=value)) is None

    def test_a_valid_limit_is_converted_to_minutes(self):
        assert ws.limit_minutes(SimpleNamespace(max_weekly_hours=18)) == 1080

    def test_the_row_for_an_unset_limit(self):
        f = SimpleNamespace(id=1, employee_code="X1", max_weekly_hours=None, user=SimpleNamespace(full_name="Dr X"))
        r = ws.row(f, 600, 600)
        assert r["status"] == "no_limit" and r["max_hours"] is None and r["overload_hours"] == 0
        assert "no weekly hour limit" in ws.assignment_warnings([r])[0]

    def test_generation_enforces_nothing_and_says_so_when_no_limit_is_configured(self, data, monkeypatch):
        set_max("F005", 1)
        real = ws.limit_minutes
        monkeypatch.setattr(ws, "limit_minutes", lambda f: None if f.employee_code == "F005" else real(f))
        result = gen()
        assert wl(result, "F005")["scheduled_hours"] == 3 and wl(result, "F005")["max_hours"] is None
        assert any("no weekly hour limit" in w for w in result["generation"]["warnings"])
        assert result["generation"]["status"] == "complete"

    def test_the_database_itself_refuses_a_zero_limit(self, data):
        from sqlalchemy.exc import IntegrityError
        faculty("F005").max_weekly_hours = 0
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


class TestValidationOfSavedOverload:
    def test_a_saved_timetable_over_the_limit_fails_with_a_clear_hard_error(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        assert client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]["validation_passed"] is True
        set_max("F001", 8)  # the saved timetable has F001 at 10 h
        rep = client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]
        assert rep["validation_passed"] is False and rep["is_valid"] is False
        err = next(c for c in rep["hard_errors"] if c["code"] == "workload_exceeded")
        assert err["severity"] == "hard" and "10 h" in err["message"] and "maximum is 8 h" in err["message"] and "2 h over" in err["message"]
        assert err["details"]["faculty_id"] == faculty("F001").id
        db.session.expire_all()
        t = db.session.get(Timetable, made["id"])
        assert t.validation_passed is False and t.status == TimetableStatus.DRAFT  # a previously validated timetable drops back to draft

    def test_it_passes_again_once_the_limit_covers_the_load(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        set_max("F001", 9)
        assert client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]["validation_passed"] is False
        set_max("F001", 10)
        rep = client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]
        assert rep["validation_passed"] is True and not any(c["code"] == "workload_exceeded" for c in rep["hard_errors"])

    def test_exactly_at_the_limit_is_allowed(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        set_max("F001", 10)
        assert client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]["validation_passed"] is True

    def test_overload_is_measured_in_real_hours(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        shorten_class_slots(45)   # F001's 10 periods are now 7.5 h
        set_max("F001", 8)
        assert client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]["validation_passed"] is True
        set_max("F001", 7)
        rep = client.post(f"{URL}/{made['id']}/validate", headers=admin_headers).get_json()["data"]
        assert any(c["code"] == "workload_exceeded" and "7.5 h" in c["message"] for c in rep["hard_errors"])

    def test_an_overload_failure_does_not_approve_or_publish(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        t = db.session.get(Timetable, made["id"])
        t.status = TimetableStatus.APPROVED
        db.session.commit()
        set_max("F001", 8)
        client.post(f"{URL}/{made['id']}/validate", headers=admin_headers)
        db.session.expire_all()
        t = db.session.get(Timetable, made["id"])
        assert t.status == TimetableStatus.APPROVED and t.validation_passed is False and t.published_at is None


class TestDetailAndVersions:
    def test_detail_shows_workload_per_faculty(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        detail = client.get(f"{URL}/{made['id']}", headers=admin_headers).get_json()["data"]
        by_code = {r["employee_code"]: r for r in detail["workload"]}
        assert by_code["F001"]["scheduled_hours"] == 10 and by_code["F001"]["assigned_hours"] == 10 and by_code["F001"]["max_hours"] == 18
        assert set(by_code) == {"F001", "F002", "F003", "F004", "F005", "F006"}

    def test_detail_marks_an_overloaded_saved_timetable(self, client, admin_headers):
        made = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        set_max("F001", 8)
        row = next(r for r in client.get(f"{URL}/{made['id']}", headers=admin_headers).get_json()["data"]["workload"] if r["employee_code"] == "F001")
        assert row["status"] == "over_limit" and row["overload_hours"] == 2

    def test_versions_still_increment_and_each_respects_the_limits(self, client, admin_headers):
        set_max("F005", 2)
        first = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        second = client.post(f"{URL}/generate", json={"term_id": term().id}, headers=admin_headers).get_json()["data"]
        assert (first["version"], second["version"]) == (1, 2)
        for t in (first, second):
            assert minutes_of(t["id"], "F005") == 120


class TestPermissions:
    def test_login_required(self, client, seeded):
        assert client.get(f"{URL}/workload-preview?term_id=1").status_code == 401

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers"])
    def test_non_admins_are_forbidden(self, client, request, who):
        headers = request.getfixturevalue(who)
        assert client.get(f"{URL}/workload-preview?term_id={term().id}", headers=headers).status_code == 403
