"""Jiya - R10 timetable validation: hard rules (via the existing clash service), completeness, advisory warnings, persistence.

Every scenario generates a real timetable first and then damages the SAVED rows (as stale or hand-edited data would be),
because validation must judge the database, never a client-provided preview.
"""
import pytest

from app.extensions import db
from app.models import (
    AvailabilityStatus, ClassType, FacultyAvailability, Room, RoomType, SlotType, TeachingAssignment, TimeSlot, Timetable, TimetableEntry, TimetableStatus,
    UnscheduledItem,
)
from app.modules.jiya import timetable_service as service
from app.modules.pragya import clash_service as cs
from app.tests.jiya.test_generation import EMPTY, admin_id, counts, disable_slots, entries, gen, term, unscheduled
from app.tests.pragya.helpers import faculty, odd_slot, sid

URL = "/api/v1/timetables"


@pytest.fixture()
def data(app, seeded):
    return None


@pytest.fixture()
def tt(data):
    return gen()["id"]


def validate(client, headers, timetable_id, **body):
    return client.post(f"{URL}/{timetable_id}/validate", json=body, headers=headers)


def report(client, headers, timetable_id):
    r = validate(client, headers, timetable_id)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def codes(rep, key="hard_errors"):
    return sorted({c["code"] for c in rep[key]})


def refresh(timetable_id):
    db.session.expire_all()
    return db.session.get(Timetable, timetable_id)


def first_entry(timetable_id, subject_code=None, batch_section=None):
    for e in entries(timetable_id):
        if subject_code and e.assignment.subject.code != subject_code:
            continue
        if batch_section and e.batch.section != batch_section:
            continue
        return e
    raise AssertionError("no such entry")


class TestValidComplete:
    def test_a_complete_clean_timetable_passes_and_is_recorded(self, client, admin_headers, tt):
        rep = report(client, admin_headers, tt)
        assert (rep["validation_passed"], rep["is_valid"], rep["is_complete"]) == (True, True, True)
        assert rep["counts"] == {"required_sessions": 32, "scheduled_sessions": 32, "unscheduled_sessions": 0, "scheduled_periods": 36, "hard_errors": 0, "warnings": 0}
        assert rep["hard_errors"] == [] and rep["warnings"] == [] and rep["unscheduled"] == []
        t = refresh(tt)
        assert t.validation_passed is True and t.validated_at is not None and t.status == TimetableStatus.VALIDATED
        assert rep["status"] == "validated" and rep["validated_at"]

    def test_the_list_and_detail_show_the_result(self, client, admin_headers, tt):
        report(client, admin_headers, tt)
        item = client.get(f"{URL}/{tt}", headers=admin_headers).get_json()["data"]
        assert item["validation_passed"] is True and item["status"] == "validated" and item["validated_at"]

    def test_validation_changes_no_entries_or_unscheduled_items(self, client, admin_headers, tt):
        before = sorted((e.id, e.assignment_id, e.time_slot_id, e.room_id) for e in entries(tt))
        report(client, admin_headers, tt)
        assert sorted((e.id, e.assignment_id, e.time_slot_id, e.room_id) for e in entries(tt)) == before
        assert counts()["Timetable"] == 1 and counts()["UnscheduledItem"] == 0

    def test_the_request_body_is_ignored_the_database_decides(self, client, admin_headers, tt):
        first_entry(tt).room.is_available = False
        db.session.commit()
        r = validate(client, admin_headers, tt, is_valid=True, validation_passed=True, hard_errors=[])
        assert r.status_code == 200 and r.get_json()["data"]["validation_passed"] is False
        assert refresh(tt).validation_passed is False


class TestHardConflicts:
    def _extra(self, tt, source, **over):
        """A second entry in a DIFFERENT slot row covering the same clock time (the unique keys cannot see this)."""
        dup = odd_slot(source.time_slot.day_of_week, 9, (source.time_slot.start_time.hour, source.time_slot.start_time.minute), (source.time_slot.end_time.hour, source.time_slot.end_time.minute))
        fields = dict(timetable_id=tt, assignment_id=source.assignment_id, faculty_id=source.faculty_id, batch_id=source.batch_id, room_id=source.room_id, time_slot_id=dup.id)
        fields.update(over)
        db.session.add(TimetableEntry(**fields))
        db.session.commit()

    def _fails_with(self, client, admin_headers, tt, *expected):
        rep = report(client, admin_headers, tt)
        assert rep["validation_passed"] is False and rep["is_valid"] is False
        for code in expected:
            assert code in codes(rep), codes(rep)
        t = refresh(tt)
        assert t.validation_passed is False and t.status == TimetableStatus.DRAFT
        return rep

    def test_faculty_overlap(self, client, admin_headers, tt):
        src = first_entry(tt, "CS301", "A")
        other_batch = first_entry(tt, "CS302", "B")
        self._extra(tt, src, batch_id=other_batch.batch_id, room_id=other_batch.room_id)
        self._fails_with(client, admin_headers, tt, "faculty_clash")

    def test_batch_overlap(self, client, admin_headers, tt):
        src = first_entry(tt, "CS301", "A")
        other_faculty = first_entry(tt, "CS303", "B")
        self._extra(tt, src, faculty_id=other_faculty.faculty_id, room_id=other_faculty.room_id)
        self._fails_with(client, admin_headers, tt, "batch_clash")

    def test_room_overlap(self, client, admin_headers, tt):
        src = first_entry(tt, "CS301", "A")
        other = first_entry(tt, "CS303", "B")
        self._extra(tt, src, faculty_id=other.faculty_id, batch_id=other.batch_id)
        self._fails_with(client, admin_headers, tt, "room_clash")

    def test_room_too_small(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")  # batch A has 58 students
        e.room_id = db.session.scalar(db.select(Room.id).filter_by(code="R101"))  # 40 seats
        db.session.commit()
        self._fails_with(client, admin_headers, tt, "room_too_small")

    def test_room_out_of_service(self, client, admin_headers, tt):
        first_entry(tt, "CS301", "A").room.is_available = False
        db.session.commit()
        self._fails_with(client, admin_headers, tt, "room_unavailable")

    def test_theory_in_a_laboratory_and_lab_in_a_classroom(self, client, admin_headers, tt):
        theory = first_entry(tt, "CS301", "A")
        theory.room_id = db.session.scalar(db.select(Room.id).filter_by(code="LAB1"))
        lab = first_entry(tt, "CS351", "A")
        lab_rows = [e for e in entries(tt) if e.assignment_id == lab.assignment_id]
        for e in lab_rows:
            e.room_id = db.session.scalar(db.select(Room.id).filter_by(code="R202"))
        db.session.commit()
        rep = self._fails_with(client, admin_headers, tt, "room_type_mismatch")
        assert len([c for c in rep["hard_errors"] if c["code"] == "room_type_mismatch"]) >= 3

    def test_disabled_slot(self, client, admin_headers, tt):
        slot = first_entry(tt, "CS301", "A").time_slot
        slot.is_active = False
        db.session.commit()
        self._fails_with(client, admin_headers, tt, "slot_inactive")

    def test_break_slot(self, client, admin_headers, tt):
        slot = first_entry(tt, "CS301", "A").time_slot
        slot.slot_type = SlotType.BREAK
        db.session.commit()
        self._fails_with(client, admin_headers, tt, "slot_is_break")

    def test_lab_session_cut_short(self, client, admin_headers, tt):
        lab = first_entry(tt, "CS351", "A")
        db.session.delete(lab)
        db.session.commit()
        self._fails_with(client, admin_headers, tt, "lab_not_consecutive")

    def test_lab_periods_split_apart(self, client, admin_headers, tt):
        rows = [e for e in entries(tt) if e.assignment.subject.code == "CS351"]
        rows.sort(key=lambda e: (e.time_slot.day_of_week, e.time_slot.period_no))
        first, second = rows[0], rows[1]
        busy = {e.time_slot_id for e in entries(tt) if e.faculty_id == second.faculty_id or e.batch_id == second.batch_id or e.room_id == second.room_id}
        target = next(s for s in db.session.scalars(db.select(TimeSlot).where(TimeSlot.slot_type == SlotType.CLASS, TimeSlot.day_of_week == second.time_slot.day_of_week, TimeSlot.period_no > second.time_slot.period_no + 1))
                      if s.id not in busy)
        second.time_slot_id = target.id  # same day, not adjacent
        db.session.commit()
        self._fails_with(client, admin_headers, tt, "lab_not_consecutive")

    def test_faculty_hard_unavailability(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        db.session.add(FacultyAvailability(faculty_id=e.faculty_id, time_slot_id=e.time_slot_id, status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        rep = self._fails_with(client, admin_headers, tt, "faculty_unavailable")
        assert any(c["details"].get("entry_id") == e.id for c in rep["hard_errors"])

    def test_each_hard_error_is_readable(self, client, admin_headers, tt):
        first_entry(tt, "CS301", "A").room.is_available = False
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert all(c["severity"] == "hard" and len(c["message"]) > 20 for c in rep["hard_errors"])
        assert rep["counts"]["hard_errors"] == len(rep["hard_errors"])

    def test_matches_the_existing_validator(self, client, admin_headers, tt):
        first_entry(tt, "CS301", "A").room.is_available = False
        db.session.commit()
        rep = report(client, admin_headers, tt)
        existing = cs.validate_timetable(tt)
        assert codes(rep) == sorted({c.code for c in existing.hard})


class TestCompleteness:
    def test_partial_generation_is_not_complete_and_lists_every_missing_session_with_its_reason(self, client, admin_headers, data):
        disable_slots(lambda s: s.day_of_week != 0 or s.period_no > 2)
        tid = gen()["id"]
        rep = report(client, admin_headers, tid)
        assert rep["is_valid"] is True and rep["is_complete"] is False and rep["validation_passed"] is False
        assert rep["counts"]["required_sessions"] == 32
        assert rep["counts"]["scheduled_sessions"] + rep["counts"]["unscheduled_sessions"] == 32
        assert rep["counts"]["unscheduled_sessions"] == len(rep["unscheduled"]) > 0
        for u in rep["unscheduled"]:
            assert u["reason_code"] and u["reason_text"] and u["batch"]["name"] and u["subject"]["code"] and u["faculty"]["name"]
        assert rep["hard_errors"] == []
        assert refresh(tid).status == TimetableStatus.DRAFT

    def test_a_missing_session_with_no_recorded_reason_is_reported_as_not_scheduled(self, client, admin_headers, tt):
        gone = first_entry(tt, "CS301", "A")
        db.session.delete(gone)
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert rep["validation_passed"] is False and rep["is_complete"] is False and rep["counts"]["scheduled_sessions"] == 31
        assert [(u["subject"]["code"], u["reason_code"]) for u in rep["unscheduled"]] == [("CS301", "not_scheduled")]
        assert "no reason was recorded" in rep["unscheduled"][0]["reason_text"]

    def test_a_recorded_unscheduled_item_is_used_as_the_reason(self, client, admin_headers, tt):
        gone = first_entry(tt, "CS303", "A")
        db.session.add(UnscheduledItem(timetable_id=tt, assignment_id=gone.assignment_id, session_no=2, reason_code="rooms_busy", reason_text="Recorded earlier."))
        db.session.delete(gone)
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert [(u["reason_code"], u["reason_text"], u["session_no"]) for u in rep["unscheduled"]] == [("rooms_busy", "Recorded earlier.", 2)]

    def test_a_missing_lab_session_counts_as_one_session(self, client, admin_headers, tt):
        rows = [e for e in entries(tt) if e.assignment.subject.code == "CS351" and e.batch.section == "A"]
        day = rows[0].time_slot.day_of_week
        for e in [r for r in rows if r.time_slot.day_of_week == day]:
            db.session.delete(e)
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert rep["counts"]["scheduled_sessions"] == 31 and rep["counts"]["scheduled_periods"] == 34
        assert rep["hard_errors"] == [] and rep["is_complete"] is False

    def test_a_stale_unscheduled_item_is_only_a_warning(self, client, admin_headers, tt):
        a = db.session.scalars(db.select(TeachingAssignment)).first()
        db.session.add(UnscheduledItem(timetable_id=tt, assignment_id=a.id, session_no=1, reason_code="rooms_busy", reason_text="Old."))
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert rep["validation_passed"] is True and "stale_unscheduled_item" in codes(rep, "warnings")

    def test_more_sessions_than_required_is_a_hard_error(self, client, admin_headers, tt):
        src = first_entry(tt, "CS301", "A")
        free = next(s for s in db.session.scalars(db.select(TimeSlot).where(TimeSlot.slot_type == SlotType.CLASS)) if s.id not in {e.time_slot_id for e in entries(tt)})
        db.session.add(TimetableEntry(timetable_id=tt, assignment_id=src.assignment_id, faculty_id=src.faculty_id, batch_id=src.batch_id, room_id=src.room_id, time_slot_id=free.id))
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert "too_many_sessions" in codes(rep) and rep["validation_passed"] is False

    def test_an_empty_timetable_is_never_valid_or_complete(self, client, admin_headers, data):
        t = Timetable(term_id=term().id, name="Empty", version=1, generated_by=admin_id())
        db.session.add(t)
        db.session.commit()
        rep = report(client, admin_headers, t.id)
        assert rep["validation_passed"] is False and rep["is_complete"] is False and rep["counts"]["scheduled_sessions"] == 0
        assert rep["counts"]["unscheduled_sessions"] == 32 and {u["reason_code"] for u in rep["unscheduled"]} == {"not_scheduled"}


class TestWarningsAreAdvisory:
    def test_preferences_produce_warnings_but_never_fail(self, client, admin_headers, data):
        f = faculty("F001")
        db.session.add(FacultyAvailability(faculty_id=f.id, time_slot_id=sid(0, 1), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        tid = gen()["id"]
        rep = report(client, admin_headers, tid)
        assert rep["validation_passed"] is True and rep["is_valid"] is True and rep["hard_errors"] == []
        assert rep["counts"]["warnings"] > 0 and codes(rep, "warnings") == ["outside_preferred_slots"]
        assert all(w["severity"] == "advisory" for w in rep["warnings"])
        assert refresh(tid).status == TimetableStatus.VALIDATED


class TestRepeatValidationAndState:
    def test_repeating_gives_the_same_answer(self, client, admin_headers, tt):
        one, two = report(client, admin_headers, tt), report(client, admin_headers, tt)
        for key in ("validation_passed", "is_valid", "is_complete", "counts", "hard_errors", "warnings", "unscheduled", "status"):
            assert one[key] == two[key]
        assert counts()["Timetable"] == 1

    def test_status_follows_the_result_both_ways(self, client, admin_headers, tt):
        room = first_entry(tt, "CS301", "A").room
        assert report(client, admin_headers, tt)["status"] == "validated"
        room.is_available = False
        db.session.commit()
        rep = report(client, admin_headers, tt)
        assert rep["status"] == "draft" and refresh(tt).validation_passed is False
        db.session.get(Room, room.id).is_available = True
        db.session.commit()
        assert report(client, admin_headers, tt)["status"] == "validated" and refresh(tt).validation_passed is True

    def test_a_failing_validation_never_leaves_validation_passed_true(self, client, admin_headers, tt):
        t = refresh(tt)
        t.validation_passed = True   # stale value from an earlier run
        t.status = TimetableStatus.VALIDATED
        first_entry(tt, "CS301", "A").room.is_available = False
        db.session.commit()
        report(client, admin_headers, tt)
        t = refresh(tt)
        assert t.validation_passed is False and t.status == TimetableStatus.DRAFT

    def test_a_failure_while_validating_changes_nothing(self, client, admin_headers, tt, monkeypatch):
        t = refresh(tt)
        t.validation_passed = True
        db.session.commit()
        def boom(timetable_id):
            raise RuntimeError("validator crashed")
        monkeypatch.setattr(cs, "validate_timetable", boom)
        assert validate(client, admin_headers, tt).status_code == 500  # the app turns unexpected errors into a 500 envelope
        t = refresh(tt)
        assert t.validation_passed is True and t.validated_at is None

    def test_validating_one_version_does_not_touch_another(self, client, admin_headers, tt):
        other = gen()["id"]
        report(client, admin_headers, tt)
        assert refresh(other).validation_passed is False and refresh(other).status == TimetableStatus.DRAFT


class TestNeverApprovesOrPublishes:
    def test_a_pass_stops_at_validated(self, client, admin_headers, tt):
        report(client, admin_headers, tt)
        t = refresh(tt)
        assert t.status == TimetableStatus.VALIDATED
        assert t.approved_by is None and t.approved_at is None and t.published_at is None

    @pytest.mark.parametrize("status", [TimetableStatus.PENDING_APPROVAL, TimetableStatus.APPROVED, TimetableStatus.PUBLISHED, TimetableStatus.REJECTED, TimetableStatus.ARCHIVED])
    def test_other_statuses_are_never_changed_by_validation(self, client, admin_headers, tt, status):
        t = refresh(tt)
        t.status = status
        db.session.commit()
        assert report(client, admin_headers, tt)["validation_passed"] is True
        t = refresh(tt)
        assert t.status == status and t.published_at is None and t.approved_by is None
        first_entry(tt, "CS301", "A").room.is_available = False
        db.session.commit()
        assert report(client, admin_headers, tt)["validation_passed"] is False
        assert refresh(tt).status == status

    def test_a_validated_timetable_can_still_be_discarded_to_free_the_setup_data(self, client, admin_headers, tt):
        report(client, admin_headers, tt)
        assert client.get(f"{URL}/{tt}", headers=admin_headers).get_json()["data"]["can_discard"] is True
        assert client.delete(f"{URL}/{tt}", headers=admin_headers).status_code == 200
        assert counts() == EMPTY

    def test_there_is_no_publish_or_approve_endpoint_here(self, client, admin_headers, tt):
        for action in ("publish", "approve", "submit"):
            assert client.post(f"{URL}/{tt}/{action}", headers=admin_headers).status_code in (404, 405)


class TestPermissions:
    def test_login_is_required(self, client, tt):
        assert client.post(f"{URL}/{tt}/validate").status_code == 401

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers"])
    def test_non_admins_are_forbidden_and_nothing_changes(self, client, request, tt, who):
        headers = request.getfixturevalue(who)
        assert validate(client, headers, tt).status_code == 403
        t = refresh(tt)
        assert t.validation_passed is False and t.validated_at is None and t.status == TimetableStatus.DRAFT

    def test_unknown_timetable_is_404(self, client, admin_headers, data):
        r = validate(client, admin_headers, 9999)
        assert r.status_code == 404 and r.get_json()["success"] is False
