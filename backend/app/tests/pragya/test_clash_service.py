"""Pragya - R8 clash detection and R9 allocation checks (PRA-TC07 .. PRA-TC18, PRA-TC10/11 boundaries).

These test the reusable service functions directly; the HTTP wrappers are tested in test_clash_api.py.
Seed reminder: Mon-Fri, period 1 = 09:00-10:00 ... period 3 = 11:00-12:00, period 4 = BREAK 12:00-13:00, periods 5-7 = 13:00-16:00.
Batch A = 58 students, batch B = 42. Rooms: R101 40, R102 45, R201 60, R202 70, LAB1 60 (lab), LAB2 45 (lab), SEM1 120 (seminar hall).
"""
from datetime import time

import pytest

from app.extensions import db
from app.models import AvailabilityStatus, FacultyAvailability, Room, RoomType, Subject, TimeSlot
from app.modules.pragya import clash_service as cs
from app.modules.pragya.clash_service import ADVISORY, HARD, Placement, ScheduledPeriod
from app.tests.pragya.helpers import assignment, batch, faculty, new_timetable, odd_slot, place, room, sid, slot, subject


def codes(conflicts, severity=None):
    return sorted(c.code for c in conflicts if severity is None or c.severity == severity)


def theory(room_code="R201", day=0, period=1, fac="F001", section="A", subject_code="CS301"):
    return Placement(faculty(fac).id, batch(section).id, room(room_code).id, (sid(day, period),), subject(subject_code).id)


def lab(room_code="LAB1", slots=((0, 1), (0, 2)), fac="F001", section="A", subject_code="CS351"):
    return Placement(faculty(fac).id, batch(section).id, room(room_code).id, tuple(sid(d, p) for d, p in slots), subject(subject_code).id)


@pytest.fixture()
def tt(seeded):
    """A timetable with one entry: F001 teaches batch A (CS301) in R201 on Monday period 1."""
    t = new_timetable()
    entry = place(t, assignment("A", "CS301"), "R201", 0, 1)
    return t, entry


# ---------------------------------------------------------------- overlap definition (pure)
class TestOverlapDefinition:
    def test_same_slot_overlaps(self, seeded):
        assert cs.slots_overlap(slot(0, 1), slot(0, 1))

    def test_touching_slots_do_not_overlap(self, seeded):
        assert not cs.slots_overlap(slot(0, 1), slot(0, 2))  # 09:00-10:00 vs 10:00-11:00
        assert not cs.slots_overlap(slot(0, 2), slot(0, 1))  # symmetric

    def test_different_days_never_overlap(self, seeded):
        assert not cs.slots_overlap(slot(0, 1), slot(1, 1))

    def test_partially_overlapping_slots_overlap_both_ways(self, seeded):
        s = odd_slot(0, 20, (9, 30), (10, 30))
        assert cs.slots_overlap(s, slot(0, 1)) and cs.slots_overlap(slot(0, 1), s)
        assert cs.slots_overlap(s, slot(0, 2))

    def test_a_slot_one_minute_short_of_touching_overlaps(self, seeded):
        s = odd_slot(0, 20, (9, 59), (10, 30))
        assert cs.slots_overlap(s, slot(0, 1))

    def test_a_slot_that_starts_exactly_when_another_ends_does_not(self, seeded):
        s = odd_slot(0, 20, (10, 0), (10, 30))
        assert not cs.slots_overlap(s, slot(0, 1)) and cs.slots_overlap(s, slot(0, 2))

    def test_consecutive_means_same_day_and_adjacent_period_numbers(self, seeded):
        assert cs.are_consecutive([slot(0, 1), slot(0, 2), slot(0, 3)])
        assert not cs.are_consecutive([slot(0, 3), slot(0, 5)])  # period 4 (a break) sits between them
        assert not cs.are_consecutive([slot(0, 1), slot(1, 2)])
        assert not cs.are_consecutive([slot(0, 1), slot(0, 3)])


# ---------------------------------------------------------------- R8: faculty / batch / room clashes
class TestClashes:
    def test_PRA_TC07_faculty_clash(self, tt):
        t, _ = tt
        conflicts = cs.check_session(theory(room_code="R202", section="B"), timetable_id=t.id)  # same teacher + slot, other batch and room
        assert codes(conflicts) == ["faculty_clash"] and conflicts[0].severity == HARD

    def test_PRA_TC08_batch_clash(self, tt):
        t, _ = tt
        conflicts = cs.check_session(theory(room_code="R202", fac="F002"), timetable_id=t.id)  # same batch + slot, other teacher and room
        assert codes(conflicts) == ["batch_clash"]

    def test_PRA_TC09_room_clash(self, tt):
        t, _ = tt
        conflicts = cs.check_session(theory(room_code="R201", fac="F002", section="B"), timetable_id=t.id)  # same room + slot only
        assert codes(conflicts) == ["room_clash"]

    def test_all_three_clash_kinds_are_reported_together(self, tt):
        t, _ = tt
        assert codes(cs.check_session(theory(), timetable_id=t.id)) == ["batch_clash", "faculty_clash", "room_clash"]

    def test_PRA_TC10_back_to_back_classes_do_not_clash(self, tt):
        t, _ = tt
        # same teacher, same batch, same room, the very next period: 10:00 start touches 10:00 end
        assert cs.check_session(theory(period=2), timetable_id=t.id) == []

    def test_PRA_TC10_the_same_resources_on_another_day_or_period_do_not_clash(self, tt):
        t, _ = tt
        assert cs.check_session(theory(day=1), timetable_id=t.id) == []
        assert cs.check_session(theory(period=3), timetable_id=t.id) == []

    def test_PRA_TC11_true_time_overlap_between_different_slots_is_detected(self, tt):
        t, _ = tt
        s = odd_slot(0, 20, (9, 30), (10, 30))  # a slot that overlaps Monday period 1 (09:00-10:00) by 30 minutes
        placement = Placement(faculty().id, batch("B").id, room("R201").id, (s.id,), subject("CS301").id)
        assert "room_clash" in codes(cs.check_session(placement, timetable_id=t.id))
        assert "faculty_clash" in codes(cs.check_session(placement, timetable_id=t.id))

    def test_PRA_TC11_a_slot_that_only_touches_the_existing_class_is_not_a_clash(self, tt):
        t, _ = tt
        s = odd_slot(0, 20, (10, 0), (10, 30))  # starts exactly when period 1 ends
        placement = Placement(faculty().id, batch("A").id, room("R201").id, (s.id,), subject("CS301").id)
        assert cs.check_session(placement, timetable_id=t.id) == []

    def test_PRA_TC12_editing_an_entry_ignores_the_entry_being_moved(self, tt):
        t, entry = tt
        assert codes(cs.check_session(theory(), timetable_id=t.id)) == ["batch_clash", "faculty_clash", "room_clash"]
        assert cs.check_session(theory(), timetable_id=t.id, ignore_entry_ids=[entry.id]) == []
        moved = cs.check_session(theory(room_code="R202", period=2), timetable_id=t.id, ignore_entry_ids=[entry.id])
        assert moved == []

    def test_a_clash_names_the_clashing_entry(self, tt):
        t, entry = tt
        conflict = cs.check_session(theory(room_code="R202", section="B"), timetable_id=t.id)[0]
        assert conflict.details["entry_id"] == entry.id and "Monday period 1" in conflict.message

    def test_without_a_timetable_nothing_clashes(self, seeded):
        assert cs.check_session(theory()) == []

    def test_scheduled_periods_can_be_supplied_in_memory_for_the_generator(self, seeded):
        in_memory = [ScheduledPeriod(None, faculty().id, batch("B").id, room("R202").id, sid(0, 1))]
        assert codes(cs.check_session(theory(room_code="R201"), scheduled=in_memory)) == ["faculty_clash"]
        assert codes(cs.check_session(theory(room_code="R202", fac="F002", section="A"), scheduled=in_memory)) == ["room_clash"]


# ---------------------------------------------------------------- R9: capacity and room type
class TestRoomSuitability:
    def test_PRA_TC13_a_room_with_enough_seats_is_fine(self, seeded):
        assert cs.check_session(theory(room_code="R201")) == []  # 60 seats for 58 students

    def test_PRA_TC14_a_room_that_is_too_small_is_rejected(self, seeded):
        conflicts = cs.check_session(theory(room_code="R102"))  # 45 seats for 58 students
        assert codes(conflicts) == ["room_too_small"]
        assert conflicts[0].details == {"room_id": room("R102").id, "capacity": 45, "strength": 58}

    def test_capacity_equal_to_the_batch_strength_is_allowed_and_one_less_is_not(self, seeded):
        db.session.add_all([Room(code="X58", name="Exact", capacity=58, room_type=RoomType.CLASSROOM), Room(code="X57", name="OneShort", capacity=57, room_type=RoomType.CLASSROOM)])
        db.session.commit()
        assert cs.check_session(theory(room_code="X58")) == []
        assert codes(cs.check_session(theory(room_code="X57"))) == ["room_too_small"]

    def test_an_out_of_service_room_is_rejected(self, seeded):
        room("R201").is_available = False
        db.session.commit()
        assert codes(cs.check_session(theory(room_code="R201"))) == ["room_unavailable"]

    def test_PRA_TC16_a_lab_session_needs_a_laboratory(self, seeded):
        conflicts = cs.check_session(lab(room_code="R201"))  # a classroom
        assert codes(conflicts) == ["room_type_mismatch"] and "needs a laboratory" in conflicts[0].message

    def test_a_lab_session_in_a_laboratory_is_fine(self, seeded):
        assert cs.check_session(lab(room_code="LAB1")) == []  # 60 seats for 58 students

    def test_a_laboratory_too_small_for_the_batch_is_rejected_on_capacity_only(self, seeded):
        assert codes(cs.check_session(lab(room_code="LAB2"))) == ["room_too_small"]  # 45 < 58, but it IS a laboratory

    def test_a_theory_class_cannot_use_a_laboratory(self, seeded):
        conflicts = cs.check_session(theory(room_code="LAB1"))
        assert codes(conflicts) == ["room_type_mismatch"] and "cannot use the laboratory" in conflicts[0].message

    def test_a_subjects_required_room_type_must_match(self, seeded):
        subject("CS301").required_room_type = RoomType.SEMINAR_HALL
        db.session.commit()
        assert codes(cs.check_session(theory(room_code="R201"))) == ["room_type_mismatch"]
        assert cs.check_session(theory(room_code="SEM1")) == []

    def test_without_a_subject_only_capacity_and_availability_are_checked(self, seeded):
        placement = Placement(faculty().id, batch("A").id, room("LAB1").id, (sid(0, 1),), None)
        assert cs.check_session(placement) == []

    def test_unknown_references_are_a_400_not_a_crash(self, seeded):
        from app.common.errors import AppError
        with pytest.raises(AppError) as err:
            cs.check_session(Placement(faculty().id, batch("A").id, 99999, (sid(0, 1),), None))
        assert err.value.status == 400


# ---------------------------------------------------------------- slots and lab sessions
class TestSlotsAndSessions:
    def test_a_break_slot_is_rejected(self, seeded):
        assert "slot_is_break" in codes(cs.check_session(theory(period=4)))

    def test_a_disabled_slot_is_rejected(self, seeded):
        slot(0, 7).is_active = False
        db.session.commit()
        assert "slot_inactive" in codes(cs.check_session(theory(period=7)))

    def test_an_unknown_slot_is_rejected(self, seeded):
        placement = Placement(faculty().id, batch("A").id, room("R201").id, (999999,), subject("CS301").id)
        assert "slot_unknown" in codes(cs.check_session(placement))

    def test_the_same_slot_listed_twice_is_rejected(self, seeded):
        placement = Placement(faculty().id, batch("A").id, room("LAB1").id, (sid(0, 1), sid(0, 1)), subject("CS351").id)
        assert "duplicate_slot" in codes(cs.check_session(placement))

    def test_PRA_lab_two_consecutive_periods_are_valid_including_after_the_break(self, seeded):
        assert cs.check_session(lab(slots=((0, 1), (0, 2)))) == []
        assert cs.check_session(lab(slots=((0, 2), (0, 3)))) == []
        assert cs.check_session(lab(slots=((0, 5), (0, 6)))) == []

    def test_slot_order_in_the_request_does_not_matter(self, seeded):
        assert cs.check_session(lab(slots=((0, 2), (0, 1)))) == []

    def test_a_lab_split_across_the_break_is_not_consecutive(self, seeded):
        conflicts = cs.check_session(lab(slots=((0, 3), (0, 5))))  # 11:00-12:00 and 13:00-14:00, period 4 is lunch
        assert codes(conflicts) == ["not_consecutive"]

    def test_a_lab_with_a_gap_or_on_two_days_is_not_consecutive(self, seeded):
        assert codes(cs.check_session(lab(slots=((0, 1), (0, 3))))) == ["not_consecutive"]
        assert codes(cs.check_session(lab(slots=((0, 2), (1, 3))))) == ["not_consecutive"]

    def test_a_lab_session_of_the_wrong_length_is_rejected(self, seeded):
        assert codes(cs.check_session(lab(slots=((0, 1),)))) == ["wrong_session_length"]
        assert codes(cs.check_session(lab(slots=((0, 1), (0, 2), (0, 3))))) == ["wrong_session_length"]

    def test_a_three_period_lab_needs_three_consecutive_periods(self, seeded):
        subject("CS351").lab_block_periods = 3
        subject("CS351").weekly_hours = 3
        db.session.commit()
        assert cs.check_session(lab(room_code="LAB1", slots=((0, 1), (0, 2), (0, 3)))) == []
        assert codes(cs.check_session(lab(room_code="LAB1", slots=((0, 1), (0, 2))))) == ["wrong_session_length"]
        assert codes(cs.check_session(lab(room_code="LAB1", slots=((0, 2), (0, 3), (0, 5))))) == ["not_consecutive"]

    def test_a_theory_class_is_exactly_one_period(self, seeded):
        placement = Placement(faculty().id, batch("A").id, room("R201").id, (sid(0, 1), sid(0, 2)), subject("CS301").id)
        assert "wrong_session_length" in codes(cs.check_session(placement))

    def test_clashes_are_checked_across_every_period_of_a_lab_session(self, seeded):
        t = new_timetable()
        place(t, assignment("B", "CS301"), "LAB1", 0, 2, faculty_id=faculty("F002").id)  # LAB1 busy in period 2 only
        assert codes(cs.check_session(lab(room_code="LAB1", slots=((0, 1), (0, 2))), timetable_id=t.id)) == ["room_clash"]
        assert cs.check_session(lab(room_code="LAB1", slots=((0, 5), (0, 6))), timetable_id=t.id) == []


# ---------------------------------------------------------------- hard unavailability vs soft preference
class TestAvailability:
    def _mark(self, code, day, period, status):
        db.session.add(FacultyAvailability(faculty_id=faculty(code).id, time_slot_id=sid(day, period), status=status))
        db.session.commit()

    def test_hard_unavailability_is_a_hard_conflict(self, seeded):
        self._mark("F001", 0, 1, AvailabilityStatus.UNAVAILABLE)
        conflicts = cs.check_session(theory())
        assert codes(conflicts) == ["faculty_unavailable"] and conflicts[0].severity == HARD
        assert cs.has_hard_conflict(conflicts)

    def test_unavailability_in_any_period_of_a_lab_blocks_the_whole_session(self, seeded):
        self._mark("F001", 0, 2, AvailabilityStatus.UNAVAILABLE)
        conflicts = cs.check_session(lab(slots=((0, 1), (0, 2))))
        assert codes(conflicts) == ["faculty_unavailable"] and conflicts[0].details["time_slot_id"] == sid(0, 2)

    def test_unavailability_of_another_faculty_member_is_irrelevant(self, seeded):
        self._mark("F002", 0, 1, AvailabilityStatus.UNAVAILABLE)
        assert cs.check_session(theory(fac="F001")) == []

    def test_a_soft_preference_is_only_advisory_and_never_blocks(self, seeded):
        self._mark("F001", 1, 1, AvailabilityStatus.PREFERRED)  # prefers Tuesday period 1; Monday period 1 is NOT preferred
        conflicts = cs.check_session(theory(day=0, period=1))
        assert codes(conflicts) == ["outside_preferred_slots"] and conflicts[0].severity == ADVISORY
        assert not cs.has_hard_conflict(conflicts)

    def test_a_preferred_slot_produces_no_note_at_all(self, seeded):
        self._mark("F001", 0, 1, AvailabilityStatus.PREFERRED)
        assert cs.check_session(theory(day=0, period=1)) == []

    def test_without_any_preferences_there_is_no_advisory(self, seeded):
        assert cs.check_session(theory()) == []

    def test_unavailable_wins_over_the_advisory_for_that_slot(self, seeded):
        self._mark("F001", 0, 1, AvailabilityStatus.UNAVAILABLE)
        self._mark("F001", 0, 2, AvailabilityStatus.PREFERRED)
        assert codes(cs.check_session(theory(period=1))) == ["faculty_unavailable"]  # no advisory piled on top
        assert cs.check_session(theory(period=2)) == []

    def test_PRA_TC20_the_ok_verdict_ignores_advisories(self, seeded):
        self._mark("F001", 1, 1, AvailabilityStatus.PREFERRED)
        assert not cs.has_hard_conflict(cs.check_session(theory(day=0, period=1)))


# ---------------------------------------------------------------- R9: ranking and explaining rooms
class TestRankRooms:
    def test_PRA_TC15_suitable_rooms_smallest_first(self, seeded):
        ranked = cs.rank_rooms(subject("CS301"), batch("A"), [sid(0, 1)])
        assert [r.code for r in ranked] == ["R201", "R202"]  # 60, 70 seats; labs and the seminar hall are excluded for a classroom theory subject

    def test_a_smaller_batch_gets_smaller_rooms_first(self, seeded):
        # batch B has 42 students: R101 (40 seats) is too small, then 45, 60, 70 in ascending order
        assert [r.code for r in cs.rank_rooms(subject("CS301"), batch("B"), [sid(0, 1)])] == ["R102", "R201", "R202"]

    def test_PRA_TC17_labs_only_rank_laboratories(self, seeded):
        assert [r.code for r in cs.rank_rooms(subject("CS351"), batch("B"), [sid(0, 1), sid(0, 2)])] == ["LAB2", "LAB1"]
        assert [r.code for r in cs.rank_rooms(subject("CS351"), batch("A"), [sid(0, 1), sid(0, 2)])] == ["LAB1"]

    def test_rooms_already_in_use_in_those_periods_drop_out(self, tt):
        t, _ = tt
        assert [r.code for r in cs.rank_rooms(subject("CS301"), batch("B"), [sid(0, 1)], timetable_id=t.id)] == ["R102", "R202"]
        assert "R201" in [r.code for r in cs.rank_rooms(subject("CS301"), batch("B"), [sid(0, 2)], timetable_id=t.id)]  # next period is free again

    def test_rooms_out_of_service_drop_out(self, seeded):
        room("R201").is_available = False
        db.session.commit()
        assert [r.code for r in cs.rank_rooms(subject("CS301"), batch("A"), [sid(0, 1)])] == ["R202"]

    def test_PRA_TC17_no_suitable_room_gives_an_empty_list_not_an_invalid_pick(self, seeded):
        big = Room(code="HUGE", name="Huge batch", capacity=1, room_type=RoomType.CLASSROOM)
        batch("A").strength = 500
        db.session.add(big)
        db.session.commit()
        assert cs.rank_rooms(subject("CS301"), batch("A"), [sid(0, 1)]) == []

    def test_explain_gives_a_reason_for_every_excluded_room(self, tt):
        t, _ = tt
        verdicts = {v.room.code: v for v in cs.explain_rooms(subject("CS301"), batch("A"), [sid(0, 1)], timetable_id=t.id)}
        assert verdicts["R201"].suitable is False and codes(verdicts["R201"].reasons) == ["room_clash"]
        assert codes(verdicts["R102"].reasons) == ["room_too_small"]
        assert codes(verdicts["LAB1"].reasons) == ["room_type_mismatch"]
        assert verdicts["R202"].suitable is True and verdicts["R202"].reasons == []

    def test_ignoring_an_entry_makes_its_room_available_again(self, tt):
        t, entry = tt
        assert "R201" in [r.code for r in cs.rank_rooms(subject("CS301"), batch("A"), [sid(0, 1)], timetable_id=t.id, ignore_entry_ids=[entry.id])]


# ---------------------------------------------------------------- validating a saved timetable
class TestValidateTimetable:
    def test_a_clean_timetable_is_valid(self, seeded):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        place(t, assignment("A", "CS301"), "R201", 0, 2)  # back to back
        place(t, assignment("B", "CS302"), "R102", 0, 1)
        report = cs.validate_timetable(t.id)
        assert report.is_valid and report.conflicts == []
        assert report.to_dict()["hard_count"] == 0

    def test_an_empty_timetable_is_valid(self, seeded):
        assert cs.validate_timetable(new_timetable().id).is_valid

    def test_unknown_timetable_is_404(self, seeded):
        from app.common.errors import AppError
        with pytest.raises(AppError) as err:
            cs.validate_timetable(99999)
        assert err.value.status == 404

    def test_overlap_between_different_slots_is_reported_once_not_twice(self, seeded):
        t = new_timetable()
        a = place(t, assignment("A", "CS301"), "R201", 0, 1)
        s = odd_slot(0, 20, (9, 30), (10, 30))  # overlaps period 1 in TIME but is a different slot row, so the database's unique key cannot catch it
        b = place(t, assignment("B", "CS301"), "R201", 0, 1, slot_id=s.id)
        report = cs.validate_timetable(t.id)
        assert [c.code for c in report.hard].count("room_clash") == 1
        clash = next(c for c in report.hard if c.code == "room_clash")
        assert {clash.details["entry_id"], clash.details["other_entry_id"]} == {a.id, b.id}
        assert not report.is_valid

    def test_problems_that_appear_after_the_timetable_was_saved_are_found(self, seeded):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        room("R201").capacity = 50  # shrunk after scheduling (the API would refuse this; the data might not)
        room("R201").is_available = False
        slot(0, 1).is_active = False
        db.session.add(FacultyAvailability(faculty_id=faculty("F001").id, time_slot_id=sid(0, 1), status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        assert {c.code for c in cs.validate_timetable(t.id).hard} == {"room_too_small", "room_unavailable", "slot_inactive", "faculty_unavailable"}

    def test_preferences_only_give_advisories_and_the_timetable_stays_valid(self, seeded):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        db.session.add(FacultyAvailability(faculty_id=faculty("F001").id, time_slot_id=sid(1, 1), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        report = cs.validate_timetable(t.id)
        assert report.is_valid and [c.code for c in report.advisory] == ["outside_preferred_slots"] and report.hard == []

    def test_a_theory_entry_in_a_laboratory_is_reported(self, seeded):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "LAB1", 0, 1)
        assert [c.code for c in cs.validate_timetable(t.id).hard] == ["room_type_mismatch"]

    @pytest.mark.parametrize(
        "periods, valid",
        [([(0, 1), (0, 2)], True), ([(0, 2), (0, 3)], True), ([(0, 1), (0, 2), (0, 5), (0, 6)], True), ([(0, 1)], False), ([(0, 1), (0, 3)], False),
         ([(0, 3), (0, 5)], False), ([(0, 1), (0, 2), (0, 3)], False), ([(0, 1), (1, 2)], False)],
    )
    def test_lab_entries_must_form_whole_runs_of_consecutive_periods(self, seeded, periods, valid):
        t = new_timetable()
        for day, period in periods:
            place(t, assignment("A", "CS351"), "LAB1", day, period)
        report = cs.validate_timetable(t.id)
        assert ("lab_not_consecutive" not in [c.code for c in report.hard]) is valid
        if not valid:
            assert not report.is_valid
