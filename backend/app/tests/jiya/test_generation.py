"""Jiya - R7 constraint-based generation: the generator, the service rules and the HTTP endpoints.

Seed reminder: Mon-Fri, period 1 = 09:00-10:00 ... period 3 = 11:00-12:00, period 4 = BREAK, periods 5-7 = 13:00-16:00 (30 class slots).
Batch A = 58 students, B = 42. Classrooms R101 40, R102 45, R201 60, R202 70; SEM1 120 (seminar); labs LAB1 60, LAB2 45.
The demo term needs 32 sessions (36 periods): theory = 1 period, CS351 / CS352 labs = 2 consecutive periods.
"""
from collections import defaultdict

import pytest
from sqlalchemy.exc import IntegrityError

from app.common.errors import AppError
from app.extensions import db
from app.models import (
    AcademicTerm, AvailabilityStatus, Batch, ClassType, Faculty, FacultyAvailability, Room, RoomType, SlotType, Subject, TeachingAssignment, TimeSlot,
    Timetable, TimetableEntry, TimetableStatus, UnscheduledItem, User,
)
from app.modules.jiya import generator, timetable_service as service
from app.modules.pragya import clash_service as cs
from app.tests.pragya.helpers import faculty, odd_slot, sid

URL = "/api/v1/timetables"
EMPTY = {"Timetable": 0, "TimetableEntry": 0, "UnscheduledItem": 0}


def term():
    return db.session.scalar(db.select(AcademicTerm))


def admin_id():
    return db.session.scalar(db.select(User).filter_by(email="admin@timetable.test")).id


def gen():
    return service.generate(term().id, admin_id())


def entries(timetable_id):
    return db.session.scalars(db.select(TimetableEntry).where(TimetableEntry.timetable_id == timetable_id)).all()


def unscheduled(timetable_id):
    return db.session.scalars(db.select(UnscheduledItem).where(UnscheduledItem.timetable_id == timetable_id)).all()


def counts():
    return {m.__name__: db.session.scalar(db.select(db.func.count()).select_from(m)) for m in (Timetable, TimetableEntry, UnscheduledItem)}


def assert_no_overlaps(timetable_id):
    """Independent proof: no faculty, batch or room has two classes that overlap in clock time."""
    rows = [(e, db.session.get(TimeSlot, e.time_slot_id)) for e in entries(timetable_id)]
    for key in ("faculty_id", "batch_id", "room_id"):
        for i, (a, sa) in enumerate(rows):
            for b, sb in rows[i + 1:]:
                if getattr(a, key) == getattr(b, key):
                    assert not (sa.day_of_week == sb.day_of_week and sa.start_time < sb.end_time and sb.start_time < sa.end_time), (key, a.id, b.id)


def disable_slots(where):
    for s in db.session.scalars(db.select(TimeSlot)).all():
        if where(s):
            s.is_active = False
    db.session.commit()


def post_generate(client, headers):
    return client.post(f"{URL}/generate", json={"term_id": term().id}, headers=headers)


@pytest.fixture()
def data(app, seeded):
    return None


class TestSuccessfulGeneration:
    def test_theory_and_labs_are_all_scheduled_as_a_draft(self, data):
        result = gen()
        g = result["generation"]
        assert (g["status"], g["required_sessions"], g["scheduled_sessions"], g["unscheduled_sessions"], g["scheduled_periods"]) == ("complete", 32, 32, 0, 36)
        assert result["status"] == "draft" and result["version"] == 1 and result["validation_passed"] is False
        timetable = db.session.get(Timetable, result["id"])
        assert timetable.status == TimetableStatus.DRAFT and timetable.approved_by is None and timetable.published_at is None
        assert len(entries(timetable.id)) == 36 and unscheduled(timetable.id) == []

    def test_every_assignment_gets_exactly_the_periods_it_needs(self, data):
        result = gen()
        per_assignment = defaultdict(int)
        for e in entries(result["id"]):
            per_assignment[e.assignment_id] += 1
        for a in db.session.scalars(db.select(TeachingAssignment)).all():
            length = a.subject.lab_block_periods if a.subject.class_type == ClassType.LAB else 1
            assert per_assignment[a.id] == a.sessions_per_week * length, a.subject.code

    def test_result_passes_the_existing_validator_with_no_hard_conflicts(self, data):
        assert cs.validate_timetable(gen()["id"]).is_valid

    def test_no_overlaps_and_only_active_class_slots(self, data):
        result = gen()
        assert_no_overlaps(result["id"])
        for e in entries(result["id"]):
            s = db.session.get(TimeSlot, e.time_slot_id)
            assert s.slot_type == SlotType.CLASS and s.is_active

    def test_capacity_and_room_type_rules(self, data):
        result = gen()
        for e in entries(result["id"]):
            room, batch, subject = db.session.get(Room, e.room_id), db.session.get(Batch, e.batch_id), e.assignment.subject
            assert room.capacity >= batch.strength and room.is_available
            assert (room.room_type == RoomType.LAB) == (subject.class_type == ClassType.LAB)

    def test_lab_sessions_are_consecutive_periods_in_one_lab(self, data):
        result = gen()
        checked = 0
        for a in db.session.scalars(db.select(TeachingAssignment)).all():
            if a.subject.class_type != ClassType.LAB:
                continue
            rows = sorted(((db.session.get(TimeSlot, e.time_slot_id), e.room_id) for e in entries(result["id"]) if e.assignment_id == a.id), key=lambda r: (r[0].day_of_week, r[0].period_no))
            assert len(rows) == a.sessions_per_week * 2
            for (first, room1), (second, room2) in zip(rows[0::2], rows[1::2]):
                assert first.day_of_week == second.day_of_week and second.period_no == first.period_no + 1 and room1 == room2
                checked += 1
        assert checked >= 2

    def test_is_deterministic(self, data):
        first, second = gen(), gen()
        def shape(tid):
            return sorted((e.assignment_id, e.time_slot_id, e.room_id) for e in entries(tid))
        assert shape(first["id"]) == shape(second["id"])


class TestHardRules:
    def test_overlapping_slot_records_never_double_book(self, data):
        odd_slot(0, 8, (9, 30), (10, 30))  # a second slot row covering 09:30-10:30 overlaps periods 1 and 2 in real time
        result = gen()
        assert_no_overlaps(result["id"])
        assert cs.validate_timetable(result["id"]).is_valid

    def test_hard_unavailability_is_never_used(self, data):
        f = faculty("F001")
        for s in db.session.scalars(db.select(TimeSlot).where(TimeSlot.day_of_week.in_([0, 1]))).all():
            db.session.add(FacultyAvailability(faculty_id=f.id, time_slot_id=s.id, status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        result = gen()
        days = {db.session.get(TimeSlot, e.time_slot_id).day_of_week for e in entries(result["id"]) if e.faculty_id == f.id}
        assert days and days.isdisjoint({0, 1})
        assert cs.validate_timetable(result["id"]).is_valid

    def test_faculty_unavailable_everywhere_reports_each_session(self, data):
        f = faculty("F001")
        for s in db.session.scalars(db.select(TimeSlot)).all():
            db.session.add(FacultyAvailability(faculty_id=f.id, time_slot_id=s.id, status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        result = gen()
        missing = sum(a.sessions_per_week for a in db.session.scalars(db.select(TeachingAssignment)).all() if a.faculty_id == f.id)
        items = unscheduled(result["id"])
        assert missing > 0 and len(items) == missing and {i.reason_code for i in items} == {"faculty_unavailable"}
        assert all(f.user.full_name in i.reason_text for i in items)
        assert result["generation"]["status"] == "partial" and result["generation"]["scheduled_sessions"] == 32 - missing

    def test_capacity_too_small_everywhere_is_reported_not_forced(self, data):
        for r in db.session.scalars(db.select(Room).where(Room.room_type != RoomType.LAB)).all():
            if r.code != "R101":  # only the 40-seat room stays in service
                r.is_available = False
        db.session.commit()
        result = gen()
        items = unscheduled(result["id"])
        assert items and {i.reason_code for i in items} == {"no_suitable_room"}
        assert all(i.assignment.subject.class_type == ClassType.THEORY for i in items)
        assert all(db.session.get(Room, e.room_id).room_type == RoomType.LAB for e in entries(result["id"]))

    def test_no_laboratory_in_service_leaves_only_labs_unscheduled(self, data):
        for r in db.session.scalars(db.select(Room).where(Room.room_type == RoomType.LAB)).all():
            r.is_available = False
        db.session.commit()
        result = gen()
        items = unscheduled(result["id"])
        assert items and all(i.assignment.subject.class_type == ClassType.LAB and i.reason_code == "no_suitable_room" for i in items)
        assert all(db.session.get(Room, e.room_id).room_type != RoomType.LAB for e in entries(result["id"]))
        assert "laboratory" in items[0].reason_text

    def test_required_room_type_of_a_theory_subject_is_respected(self, data):
        db.session.scalar(db.select(Subject).filter_by(code="MA301")).required_room_type = RoomType.SEMINAR_HALL
        db.session.commit()
        result = gen()
        ma = [e for e in entries(result["id"]) if e.assignment.subject.code == "MA301"]
        assert ma and all(db.session.get(Room, e.room_id).room_type == RoomType.SEMINAR_HALL for e in ma)

    def test_labs_that_cannot_get_consecutive_periods_are_reported(self, data):
        disable_slots(lambda s: s.period_no in (2, 6))  # leaves 1, 3, (break 4), 5, 7 - never two in a row
        result = gen()
        items = unscheduled(result["id"])
        labs = sum(a.sessions_per_week for a in db.session.scalars(db.select(TeachingAssignment)).all() if a.subject.class_type == ClassType.LAB)
        assert len(items) == labs and {i.reason_code for i in items} == {"no_consecutive_window"}
        assert "consecutive" in items[0].reason_text
        assert entries(result["id"]) and all(e.assignment.subject.class_type == ClassType.THEORY for e in entries(result["id"]))

    def test_breaks_and_disabled_slots_are_never_used(self, data):
        disable_slots(lambda s: s.day_of_week == 4)
        result = gen()
        assert entries(result["id"])
        for e in entries(result["id"]):
            s = db.session.get(TimeSlot, e.time_slot_id)
            assert s.day_of_week != 4 and s.slot_type == SlotType.CLASS and s.is_active

    def test_inactive_faculty_member_is_reported(self, data):
        f = faculty("F002")
        f.user.is_active = False
        db.session.commit()
        result = gen()
        items = unscheduled(result["id"])
        assert items and {i.reason_code for i in items} == {"faculty_inactive"}
        assert all(i.assignment.faculty_id == f.id for i in items)


class TestInsufficientCapacity:
    def test_too_few_slots_every_session_is_accounted_for_with_a_reason(self, data):
        disable_slots(lambda s: s.day_of_week != 0 or s.period_no > 2)  # only Monday periods 1-2 remain
        result = gen()
        g = result["generation"]
        assert g["scheduled_sessions"] + g["unscheduled_sessions"] == g["required_sessions"] == 32
        assert g["unscheduled_sessions"] > 0 and g["status"] == "partial"
        items = unscheduled(result["id"])
        assert len(items) == g["unscheduled_sessions"]
        for i in items:
            assert i.reason_code and len(i.reason_text) > 30 and i.assignment.subject.code in i.reason_text
        assert sum(g["unscheduled_reasons"].values()) == g["unscheduled_sessions"]
        assert_no_overlaps(result["id"])

    def test_no_session_is_silently_dropped(self, data):
        disable_slots(lambda s: s.day_of_week > 1)
        result = gen()
        placed, missing = defaultdict(int), defaultdict(int)
        for e in entries(result["id"]):
            placed[e.assignment_id] += 1
        for i in unscheduled(result["id"]):
            missing[i.assignment_id] += 1
        assert sum(missing.values()) > 0
        for a in db.session.scalars(db.select(TeachingAssignment)).all():
            length = 2 if a.subject.class_type == ClassType.LAB else 1
            assert placed[a.id] // length + missing[a.id] == a.sessions_per_week, a.subject.code


class TestSoftPreferences:
    def test_a_preference_never_blocks_a_placement(self, data):
        f = faculty("F001")
        db.session.add(FacultyAvailability(faculty_id=f.id, time_slot_id=sid(0, 1), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        result = gen()
        assert result["generation"]["status"] == "complete"
        mine = [e for e in entries(result["id"]) if e.faculty_id == f.id]
        assert any(e.time_slot_id != sid(0, 1) for e in mine)  # more classes than the one preferred period
        assert result["generation"]["warnings"] and "preferred" in result["generation"]["warnings"][0]

    def test_a_preferred_period_is_used_when_it_is_free(self, data):
        f = faculty("F001")
        db.session.add(FacultyAvailability(faculty_id=f.id, time_slot_id=sid(2, 3), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        result = gen()
        assert any(e.faculty_id == f.id and e.time_slot_id == sid(2, 3) for e in entries(result["id"]))


class TestVersionsAndRetries:
    def test_each_generation_is_a_new_version_without_duplicates(self, data):
        results = [gen(), gen(), gen()]
        assert [r["version"] for r in results] == [1, 2, 3]
        assert all(len(entries(r["id"])) == 36 for r in results)
        assert counts()["TimetableEntry"] == 108
        assert {t.status for t in db.session.scalars(db.select(Timetable)).all()} == {TimetableStatus.DRAFT}

    def test_earlier_versions_are_untouched(self, data):
        first = gen()
        before = sorted((e.assignment_id, e.time_slot_id, e.room_id) for e in entries(first["id"]))
        gen()
        assert sorted((e.assignment_id, e.time_slot_id, e.room_id) for e in entries(first["id"])) == before

    def test_a_lost_version_race_is_retried(self, data, monkeypatch):
        real, calls = service._save, {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError("insert", {}, Exception("duplicate version"))
            return real(*args, **kwargs)

        monkeypatch.setattr(service, "_save", flaky)
        result = gen()
        assert calls["n"] == 2 and result["version"] == 1 and counts()["Timetable"] == 1

    def test_a_race_that_keeps_losing_saves_nothing(self, data, monkeypatch):
        def always(*args, **kwargs):
            raise IntegrityError("insert", {}, Exception("duplicate version"))

        monkeypatch.setattr(service, "_save", always)
        with pytest.raises(AppError) as err:
            gen()
        assert err.value.code == "generation_conflict" and err.value.status == 409
        assert counts() == EMPTY


class TestRollback:
    def test_a_plan_that_breaks_a_hard_rule_is_rejected_and_nothing_is_saved(self, data, monkeypatch):
        a = db.session.scalars(db.select(TeachingAssignment).order_by(TeachingAssignment.id)).first()
        room = db.session.scalar(db.select(Room).filter_by(code="R201"))
        bad = generator.Plan(required_sessions=2, placed=[
            generator.PlannedSession(a.id, 1, a.faculty_id, a.batch_id, a.subject_id, room.id, (sid(0, 1),)),
            generator.PlannedSession(a.id, 2, a.faculty_id, a.batch_id, a.subject_id, room.id, (sid(0, 2),)),
            generator.PlannedSession(a.id, 3, a.faculty_id, a.batch_id, a.subject_id, room.id, (sid(0, 3),)),
        ])
        # a second class for the same faculty member in the same period violates the unique key / validator
        bad.placed.append(generator.PlannedSession(a.id, 4, a.faculty_id, a.batch_id, a.subject_id, room.id, (sid(0, 3),)))
        monkeypatch.setattr(generator, "plan_term", lambda assignments: bad)
        with pytest.raises(AppError) as err:  # the database's unique key refuses it; nothing may be left behind
            gen()
        assert err.value.status == 409
        assert counts() == EMPTY

    def test_a_valid_looking_plan_with_a_hard_conflict_is_caught_by_the_validator(self, data, monkeypatch):
        a = db.session.scalars(db.select(TeachingAssignment).order_by(TeachingAssignment.id)).first()
        small = db.session.scalar(db.select(Room).filter_by(code="R101"))  # 40 seats, batch A has 58
        bad = generator.Plan(required_sessions=1, placed=[generator.PlannedSession(a.id, 1, a.faculty_id, a.batch_id, a.subject_id, small.id, (sid(0, 1),))])
        monkeypatch.setattr(generator, "plan_term", lambda assignments: bad)
        with pytest.raises(AppError) as err:
            gen()
        assert err.value.code == "generation_invalid"
        assert counts() == EMPTY

    def test_an_unexpected_failure_while_planning_leaves_no_trace(self, data, monkeypatch):
        gen()
        before = counts()

        def boom(assignments):
            raise RuntimeError("planner crashed")

        monkeypatch.setattr(generator, "plan_term", boom)
        with pytest.raises(RuntimeError):
            gen()
        assert counts() == before

    def test_a_failure_after_rows_are_flushed_rolls_everything_back(self, data, monkeypatch):
        def broken(timetable_id):
            raise RuntimeError("validator crashed")

        monkeypatch.setattr(cs, "validate_timetable", broken)
        with pytest.raises(RuntimeError):
            gen()
        assert counts() == EMPTY


class TestEndpoints:
    def test_generate_over_http(self, client, admin_headers):
        r = post_generate(client, admin_headers)
        assert r.status_code == 201
        body = r.get_json()["data"]
        assert body["status"] == "draft" and body["generation"]["scheduled_sessions"] == 32 and body["can_discard"] is True

    def test_list_and_detail(self, client, admin_headers):
        first = post_generate(client, admin_headers).get_json()["data"]
        post_generate(client, admin_headers)
        listing = client.get(f"{URL}?term_id={term().id}", headers=admin_headers).get_json()["data"]
        assert [t["version"] for t in listing["items"]] == [2, 1] and listing["items"][0]["periods"] == 36
        assert client.get(f"{URL}?status=published", headers=admin_headers).get_json()["data"]["total"] == 0
        assert client.get(f"{URL}?status=nonsense", headers=admin_headers).status_code == 400
        detail = client.get(f"{URL}/{first['id']}", headers=admin_headers).get_json()["data"]
        assert len(detail["entries"]) == 36 and detail["unscheduled"] == []
        assert {"batch", "subject", "faculty", "room", "time_slot"} <= set(detail["entries"][0])

    def test_detail_lists_unscheduled_with_reasons(self, client, admin_headers):
        disable_slots(lambda s: s.day_of_week != 0)
        made = post_generate(client, admin_headers).get_json()["data"]
        detail = client.get(f"{URL}/{made['id']}", headers=admin_headers).get_json()["data"]
        assert detail["unscheduled"] and all(u["reason_code"] and u["reason_text"] and u["batch"]["name"] for u in detail["unscheduled"])

    @pytest.mark.parametrize("body", [{}, {"term_id": "x"}, {"term_id": True}, {"term_id": 0}, {"term_id": 9999}])
    def test_input_validation(self, client, admin_headers, body):
        r = client.post(f"{URL}/generate", json=body, headers=admin_headers)
        assert r.status_code == 400 and r.get_json()["success"] is False and counts()["Timetable"] == 0

    def test_unknown_fields_are_rejected(self, client, admin_headers):
        r = client.post(f"{URL}/generate", json={"term_id": term().id, "status": "approved"}, headers=admin_headers)
        assert r.status_code == 400 and counts()["Timetable"] == 0

    def test_an_inactive_term_is_refused(self, client, admin_headers):
        term().is_active = False
        db.session.commit()
        r = post_generate(client, admin_headers)
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "term_inactive" and counts()["Timetable"] == 0

    def test_a_term_without_assignments_is_refused(self, client, admin_headers):
        for a in db.session.scalars(db.select(TeachingAssignment)).all():
            db.session.delete(a)
        db.session.commit()
        r = post_generate(client, admin_headers)
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "no_assignments" and counts()["Timetable"] == 0

    def test_unknown_timetable_is_404(self, client, admin_headers):
        assert client.get(f"{URL}/999", headers=admin_headers).status_code == 404
        assert client.delete(f"{URL}/999", headers=admin_headers).status_code == 404


class TestPermissions:
    def test_login_is_required(self, client, seeded):
        assert client.get(URL).status_code == 401
        assert client.get(f"{URL}/1").status_code == 401
        assert client.post(f"{URL}/generate", json={"term_id": 1}).status_code == 401
        assert client.delete(f"{URL}/1").status_code == 401

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers"])
    def test_non_admins_are_forbidden_and_nothing_is_created(self, client, request, who):
        headers = request.getfixturevalue(who)
        assert client.get(URL, headers=headers).status_code == 403
        assert client.get(f"{URL}/1", headers=headers).status_code == 403
        assert post_generate(client, headers).status_code == 403
        assert client.delete(f"{URL}/1", headers=headers).status_code == 403
        assert counts()["Timetable"] == 0


class TestDiscardDraft:
    def test_discarding_a_draft_frees_the_setup_data(self, client, admin_headers):
        made = post_generate(client, admin_headers).get_json()["data"]
        a = db.session.scalars(db.select(TeachingAssignment)).first()
        assert client.delete(f"/api/v1/teaching-assignments/{a.id}", headers=admin_headers).status_code == 409  # frozen while a timetable uses it
        assert client.delete(f"{URL}/{made['id']}", headers=admin_headers).status_code == 200
        assert counts() == EMPTY
        assert client.delete(f"/api/v1/teaching-assignments/{a.id}", headers=admin_headers).status_code == 200

    def test_only_a_draft_can_be_discarded(self, client, admin_headers):
        made = post_generate(client, admin_headers).get_json()["data"]
        for status in (TimetableStatus.APPROVED, TimetableStatus.PUBLISHED):
            db.session.get(Timetable, made["id"]).status = status
            db.session.commit()
            r = client.delete(f"{URL}/{made['id']}", headers=admin_headers)
            assert r.status_code == 409 and r.get_json()["error"]["code"] == "timetable_not_draft"
        assert len(entries(made["id"])) == 36

    def test_discarding_one_version_leaves_the_others_and_numbers_move_forward(self, client, admin_headers):
        one = post_generate(client, admin_headers).get_json()["data"]
        two = post_generate(client, admin_headers).get_json()["data"]
        client.delete(f"{URL}/{two['id']}", headers=admin_headers)
        assert len(entries(one["id"])) == 36 and counts()["Timetable"] == 1
        assert post_generate(client, admin_headers).get_json()["data"]["version"] == 2  # the highest remaining is 1


class TestRegression:
    def test_generation_changes_no_setup_data(self, data):
        def snapshot():
            return tuple(db.session.scalar(db.select(db.func.count()).select_from(m)) for m in (TeachingAssignment, Room, TimeSlot, Faculty, FacultyAvailability))
        before = snapshot()
        gen()
        assert snapshot() == before

    def test_assignments_become_frozen_after_generation(self, client, admin_headers):
        post_generate(client, admin_headers)
        a = db.session.scalars(db.select(TeachingAssignment)).first()
        other = db.session.scalar(db.select(Faculty).where(Faculty.id != a.faculty_id))
        r = client.patch(f"/api/v1/teaching-assignments/{a.id}", json={"faculty_id": other.id}, headers=admin_headers)
        assert r.status_code == 409
