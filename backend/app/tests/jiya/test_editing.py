"""R15 - manual editing of one session of a saved timetable, with the same hard rules the generator obeys.

Every scenario generates a real timetable, edits it through the HTTP API and checks both the answer and the saved rows.
Seed reminder: Mon-Fri, periods 1-3 class, period 4 BREAK, periods 5-7 class (60 minutes each); batch A 58 students, B 42.
"""
import pytest

from app.extensions import db
from app.models import (
    AvailabilityStatus, FacultyAvailability, Room, SlotType, TeachingAssignment, TimeSlot, Timetable, TimetableEntry, TimetableStatus,
)
from app.modules.jiya import validation_service
from app.tests.jiya.test_generation import admin_id, counts, entries, gen, term
from app.tests.jiya.test_validation import first_entry, refresh
from app.tests.pragya.helpers import faculty, odd_slot, sid

URL = "/api/v1/timetables"


@pytest.fixture()
def data(app, seeded):
    return None


@pytest.fixture()
def tt(data):
    return gen()["id"]


def snapshot(timetable_id):
    return sorted((e.id, e.assignment_id, e.faculty_id, e.batch_id, e.room_id, e.time_slot_id) for e in entries(timetable_id))


def patch(client, headers, timetable_id, entry_id, **body):
    return client.patch(f"{URL}/{timetable_id}/entries/{entry_id}", json=body, headers=headers)


def options(client, headers, timetable_id, entry_id):
    r = client.get(f"{URL}/{timetable_id}/entries/{entry_id}/edit-options", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def conflict_codes(response):
    return sorted({c["code"] for c in response.get_json()["error"]["details"]["conflicts"]})


def rejected(client, headers, tt, entry, expect_code=None, **body):
    """Send an edit that must be refused with a conflict, and prove nothing was saved."""
    before, state = snapshot(tt), (refresh(tt).validation_passed, refresh(tt).status, refresh(tt).validated_at)
    r = patch(client, headers, tt, entry.id, **body)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "edit_conflict", r.get_json()
    db.session.expire_all()
    assert snapshot(tt) == before
    t = refresh(tt)
    assert (t.validation_passed, t.status, t.validated_at) == state
    if expect_code:
        assert expect_code in conflict_codes(r), conflict_codes(r)
    return r


def first_free_option(opts, avoid_current=True):
    for o in opts["options"]:
        if not (avoid_current and o["is_current"]):
            return o
    raise AssertionError("no alternative position")


class TestSuccessfulEdits:
    def test_move_a_theory_session_to_an_eligible_slot(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        per_assignment_before = sum(1 for x in entries(tt) if x.assignment_id == e.assignment_id)
        target = first_free_option(options(client, admin_headers, tt, e.id))
        room = next(r for r in target["rooms"])
        r = patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=room["id"])
        assert r.status_code == 200, r.get_json()
        body = r.get_json()["data"]
        db.session.expire_all()
        moved = [x for x in entries(tt) if x.id in body["edited_entry_ids"]]
        assert len(moved) == 1 and moved[0].time_slot_id == target["time_slot_id"] and moved[0].room_id == room["id"]
        assert (moved[0].assignment_id, moved[0].faculty_id, moved[0].batch_id) == (e.assignment_id, e.faculty_id, e.batch_id)
        assert sum(1 for x in entries(tt) if x.assignment_id == e.assignment_id) == per_assignment_before and len(entries(tt)) == 36
        assert body["validation"]["validation_passed"] is True and body["timetable"]["id"] == tt

    def test_change_only_the_room(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        opts = options(client, admin_headers, tt, e.id)
        current = next(o for o in opts["options"] if o["is_current"])
        other = next(r for r in current["rooms"] if not r["is_current"])
        r = patch(client, admin_headers, tt, e.id, room_id=other["id"])
        assert r.status_code == 200
        db.session.expire_all()
        row = next(x for x in entries(tt) if x.assignment_id == e.assignment_id and x.time_slot_id == e.time_slot_id)
        assert row.room_id == other["id"]

    def test_change_only_the_time(self, client, admin_headers, tt):
        e = first_entry(tt, "CS302", "B")
        keep_room = e.room_id
        opts = options(client, admin_headers, tt, e.id)
        target = next(o for o in opts["options"] if not o["is_current"] and any(r["id"] == keep_room for r in o["rooms"]))
        assert patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"]).status_code == 200
        db.session.expire_all()
        assert any(x.time_slot_id == target["time_slot_id"] and x.room_id == keep_room and x.assignment_id == e.assignment_id for x in entries(tt))

    def test_a_lab_moves_as_one_block_and_keeps_its_length(self, client, admin_headers, tt):
        e = first_entry(tt, "CS351", "A")
        before = sorted(x.time_slot_id for x in entries(tt) if x.assignment_id == e.assignment_id)
        opts = options(client, admin_headers, tt, e.id)
        assert opts["periods"] == 2 and len(opts["entry_ids"]) == 2
        target = first_free_option(opts)
        lab_room = target["rooms"][0]
        r = patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=lab_room["id"])
        assert r.status_code == 200, r.get_json()
        db.session.expire_all()
        rows = [x for x in entries(tt) if x.id in r.get_json()["data"]["edited_entry_ids"]]
        slots = sorted((db.session.get(TimeSlot, x.time_slot_id) for x in rows), key=lambda s: s.period_no)
        assert len(rows) == 2 and slots[0].day_of_week == slots[1].day_of_week and slots[1].period_no == slots[0].period_no + 1
        assert slots[0].id == target["time_slot_id"] and {x.room_id for x in rows} == {lab_room["id"]}
        assert sum(1 for x in entries(tt) if x.assignment_id == e.assignment_id) == len(before)

    def test_no_session_is_added_removed_or_converted(self, client, admin_headers, tt):
        before = {a.id: sum(1 for x in entries(tt) if x.assignment_id == a.id) for a in db.session.scalars(db.select(TeachingAssignment))}
        e = first_entry(tt, "CS303", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        db.session.expire_all()
        assert {a.id: sum(1 for x in entries(tt) if x.assignment_id == a.id) for a in db.session.scalars(db.select(TeachingAssignment))} == before
        assert counts()["Timetable"] == 1 and counts()["UnscheduledItem"] == 0 and refresh(tt).version == 1

    def test_a_soft_preference_is_a_warning_not_a_block(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        other = next(o for o in options(client, admin_headers, tt, e.id)["options"] if o["time_slot_id"] != target["time_slot_id"] and not o["is_current"])
        db.session.add(FacultyAvailability(faculty_id=e.faculty_id, time_slot_id=other["time_slot_id"], status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        r = patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        assert r.status_code == 200
        assert [w["code"] for w in r.get_json()["data"]["warnings"]] == ["outside_preferred_slots"]

    def test_exactly_at_the_weekly_limit_is_allowed(self, client, admin_headers, tt):
        e = first_entry(tt, "CS303", "B")  # F005 teaches 3 h
        db.session.get(type(e.faculty), e.faculty_id).max_weekly_hours = 3
        db.session.commit()
        target = first_free_option(options(client, admin_headers, tt, e.id))
        assert patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"]).status_code == 200


class TestHardConflictsAreRejected:
    def test_faculty_clash(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "B")           # F001
        busy_slot = first_entry(tt, "CS301", "A").time_slot_id  # F001 also teaches batch A here
        rejected(client, admin_headers, tt, mine, "faculty_clash", time_slot_id=busy_slot)

    def test_batch_clash(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "A")
        other = first_entry(tt, "CS302", "A")           # a different teacher, same batch
        rejected(client, admin_headers, tt, mine, "batch_clash", time_slot_id=other.time_slot_id)

    def test_room_clash(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "A")
        other = first_entry(tt, "CS303", "B")
        rejected(client, admin_headers, tt, mine, "room_clash", time_slot_id=other.time_slot_id, room_id=other.room_id)

    def test_overlap_through_a_different_slot_record(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "B")
        busy = first_entry(tt, "CS301", "A").time_slot
        odd = odd_slot(busy.day_of_week, 9, (busy.start_time.hour, busy.start_time.minute + 30), (busy.end_time.hour, busy.end_time.minute + 30))
        r = rejected(client, admin_headers, tt, mine, "faculty_clash", time_slot_id=odd.id)
        assert "overlaps" in next(c["message"] for c in r.get_json()["error"]["details"]["conflicts"] if c["code"] == "faculty_clash")

    def test_room_too_small(self, client, admin_headers, tt):
        rejected(client, admin_headers, tt, first_entry(tt, "CS301", "A"), "room_too_small", room_id=Room.query.filter_by(code="R101").one().id)

    def test_room_out_of_service(self, client, admin_headers, tt):
        room = Room.query.filter_by(code="R202").one()
        room.is_available = False
        db.session.commit()
        rejected(client, admin_headers, tt, first_entry(tt, "CS301", "A"), "room_unavailable", room_id=room.id)

    def test_theory_in_a_laboratory(self, client, admin_headers, tt):
        rejected(client, admin_headers, tt, first_entry(tt, "CS301", "A"), "room_type_mismatch", room_id=Room.query.filter_by(code="LAB1").one().id)

    def test_lab_in_a_classroom(self, client, admin_headers, tt):
        rejected(client, admin_headers, tt, first_entry(tt, "CS351", "A"), "room_type_mismatch", room_id=Room.query.filter_by(code="R202").one().id)

    def test_break_slot(self, client, admin_headers, tt):
        brk = db.session.scalar(db.select(TimeSlot).where(TimeSlot.slot_type == SlotType.BREAK))
        rejected(client, admin_headers, tt, first_entry(tt, "CS301", "A"), "slot_is_break", time_slot_id=brk.id)

    def test_disabled_slot(self, client, admin_headers, tt):
        free = db.session.get(TimeSlot, sid(4, 7))
        free.is_active = False
        db.session.commit()
        rejected(client, admin_headers, tt, first_entry(tt, "CS301", "A"), "slot_inactive", time_slot_id=free.id)

    def test_lab_without_enough_consecutive_periods(self, client, admin_headers, tt):
        r = rejected(client, admin_headers, tt, first_entry(tt, "CS351", "A"), "not_consecutive", time_slot_id=sid(1, 7))  # period 7 is the last of the day
        assert "2 consecutive periods" in r.get_json()["error"]["message"]

    def test_lab_window_that_crosses_the_break(self, client, admin_headers, tt):
        rejected(client, admin_headers, tt, first_entry(tt, "CS351", "A"), "slot_is_break", time_slot_id=sid(1, 3))  # periods 3 and 4 (break)

    def test_hard_unavailability(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, mine.id))
        db.session.add(FacultyAvailability(faculty_id=mine.faculty_id, time_slot_id=target["time_slot_id"], status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        rejected(client, admin_headers, tt, mine, "faculty_unavailable", time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])

    def test_workload_overflow(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS303", "B")  # F005: 3 h
        mine.faculty.max_weekly_hours = 3
        db.session.commit()
        target = next(o for o in options(client, admin_headers, tt, mine.id)["options"] if o["period_no"] == 7 and not o["is_current"])
        db.session.get(TimeSlot, target["time_slot_id"]).end_time = db.session.get(TimeSlot, target["time_slot_id"]).end_time.replace(hour=16, minute=30)  # a 90-minute period
        db.session.commit()
        r = rejected(client, admin_headers, tt, mine, "workload_exceeded", time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        assert "3.5 h" in r.get_json()["error"]["message"] or "3.5 h" in str(r.get_json()["error"]["details"])

    def test_several_problems_are_all_reported(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "A")
        r = rejected(client, admin_headers, tt, mine, time_slot_id=first_entry(tt, "CS302", "A").time_slot_id, room_id=Room.query.filter_by(code="R101").one().id)
        assert {"batch_clash", "room_too_small"} <= set(conflict_codes(r)) and "more problem" in r.get_json()["error"]["message"]

    def test_a_rejection_message_says_what_to_do(self, client, admin_headers, tt):
        r = rejected(client, admin_headers, tt, first_entry(tt, "CS301", "A"), room_id=Room.query.filter_by(code="R101").one().id)
        assert "seats 40" in r.get_json()["error"]["message"]


class TestServerDoesNotTrustTheClient:
    def test_a_position_missing_from_the_options_is_still_refused(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "B")
        listed = {o["time_slot_id"] for o in options(client, admin_headers, tt, mine.id)["options"]}
        busy = first_entry(tt, "CS301", "A").time_slot_id
        assert busy not in listed
        rejected(client, admin_headers, tt, mine, "faculty_clash", time_slot_id=busy)

    def test_options_exclude_breaks_disabled_slots_and_busy_times(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "B")
        db.session.get(TimeSlot, sid(2, 6)).is_active = False
        db.session.commit()
        ids = {o["time_slot_id"] for o in options(client, admin_headers, tt, mine.id)["options"]}
        assert sid(0, 4) not in ids and sid(2, 6) not in ids
        assert not ids & {e.time_slot_id for e in entries(tt) if e.faculty_id == mine.faculty_id and e.id != mine.id}

    def test_options_only_list_suitable_rooms_smallest_first(self, client, admin_headers, tt):
        mine = first_entry(tt, "CS301", "A")  # 58 students, theory
        for o in options(client, admin_headers, tt, mine.id)["options"]:
            caps = [r["capacity"] for r in o["rooms"]]
            assert caps == sorted(caps) and all(c >= 58 for c in caps) and all(r["room_type"] != "lab" for r in o["rooms"])

    def test_lab_options_are_two_period_windows_in_laboratories(self, client, admin_headers, tt):
        opts = options(client, admin_headers, tt, first_entry(tt, "CS351", "A").id)
        assert opts["periods"] == 2 and opts["options"]
        assert all(r["room_type"] == "lab" for o in opts["options"] for r in o["rooms"])
        assert all(o["period_no"] != 3 and o["period_no"] != 7 for o in opts["options"])  # a window may not start at 3 (break) or 7 (no next period)

    def test_the_assignment_faculty_and_batch_cannot_be_changed(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        for body in ({"assignment_id": 1}, {"faculty_id": 2}, {"batch_id": 2}, {"timetable_id": 9}, {"status": "approved"}, {"entry_id": 3}):
            r = client.patch(f"{URL}/{tt}/entries/{e.id}", json=body, headers=admin_headers)
            assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error", body

    @pytest.mark.parametrize("body", [{}, {"time_slot_id": "x"}, {"room_id": 0}, {"room_id": True}, {"time_slot_id": -1}])
    def test_bad_input_is_refused(self, client, admin_headers, tt, body):
        before = snapshot(tt)
        assert patch(client, admin_headers, tt, first_entry(tt, "CS301", "A").id, **body).status_code == 400
        assert snapshot(tt) == before

    def test_unknown_slot_or_room(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        assert patch(client, admin_headers, tt, e.id, time_slot_id=99999).status_code == 400
        assert patch(client, admin_headers, tt, e.id, room_id=99999).status_code == 400

    def test_moving_to_where_it_already_is(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        r = patch(client, admin_headers, tt, e.id, time_slot_id=e.time_slot_id, room_id=e.room_id)
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "no_change"

    def test_a_broken_lab_session_cannot_be_moved(self, client, admin_headers, tt):
        lab = first_entry(tt, "CS351", "A")
        db.session.delete([x for x in entries(tt) if x.assignment_id == lab.assignment_id][0])
        db.session.commit()
        survivor = [x for x in entries(tt) if x.assignment_id == lab.assignment_id][0]
        before = snapshot(tt)
        r = patch(client, admin_headers, tt, survivor.id, time_slot_id=sid(3, 1))
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "session_malformed" and snapshot(tt) == before


class TestLookups:
    def test_unknown_timetable_or_entry(self, client, admin_headers, tt):
        assert patch(client, admin_headers, 9999, 1, room_id=1).status_code == 404
        assert patch(client, admin_headers, tt, 99999, room_id=1).status_code == 404

    def test_an_entry_of_another_timetable_is_not_editable_here(self, client, admin_headers, tt):
        other = gen()["id"]
        foreign = first_entry(other)
        before = snapshot(other)
        assert patch(client, admin_headers, tt, foreign.id, room_id=Room.query.filter_by(code="R202").one().id).status_code == 404
        assert client.get(f"{URL}/{tt}/entries/{foreign.id}/edit-options", headers=admin_headers).status_code == 404
        assert snapshot(other) == before


class TestImmutableStatuses:
    @pytest.mark.parametrize("status", [TimetableStatus.APPROVED, TimetableStatus.PUBLISHED, TimetableStatus.PENDING_APPROVAL, TimetableStatus.ARCHIVED])
    def test_only_draft_validated_and_rejected_can_be_edited(self, client, admin_headers, tt, status):
        t = refresh(tt)
        t.status = status
        db.session.commit()
        e = first_entry(tt, "CS301", "A")
        before = snapshot(tt)
        r = patch(client, admin_headers, tt, e.id, room_id=Room.query.filter_by(code="R202").one().id)
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "timetable_not_editable"
        assert client.get(f"{URL}/{tt}/entries/{e.id}/edit-options", headers=admin_headers).status_code == 409
        db.session.expire_all()
        assert snapshot(tt) == before and refresh(tt).status == status

    def test_the_detail_says_whether_a_timetable_can_be_edited(self, client, admin_headers, tt):
        assert client.get(f"{URL}/{tt}", headers=admin_headers).get_json()["data"]["can_edit"] is True
        refresh(tt).status = TimetableStatus.APPROVED
        db.session.commit()
        assert client.get(f"{URL}/{tt}", headers=admin_headers).get_json()["data"]["can_edit"] is False

    def test_a_validated_timetable_is_editable(self, client, admin_headers, tt):
        client.post(f"{URL}/{tt}/validate", headers=admin_headers)
        assert refresh(tt).status == TimetableStatus.VALIDATED
        e = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        assert patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"]).status_code == 200


class TestValidationStateAfterAnEdit:
    def test_a_stale_valid_result_never_survives(self, client, admin_headers, tt):
        assert client.post(f"{URL}/{tt}/validate", headers=admin_headers).get_json()["data"]["validation_passed"] is True
        first_validated = refresh(tt).validated_at
        first_entry(tt, "CS303", "B").room.is_available = False  # unrelated damage that makes the timetable invalid
        db.session.commit()
        e = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        r = patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        assert r.status_code == 200
        v = r.get_json()["data"]["validation"]
        assert v["validation_passed"] is False and any(c["code"] == "room_unavailable" for c in v["hard_errors"])
        t = refresh(tt)
        assert t.validation_passed is False and t.status == TimetableStatus.DRAFT and t.validated_at >= first_validated

    def test_the_stored_result_matches_the_new_contents(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        r = patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        t = refresh(tt)
        again = client.post(f"{URL}/{tt}/validate", headers=admin_headers).get_json()["data"]
        assert t.validation_passed is r.get_json()["data"]["validation"]["validation_passed"] is again["validation_passed"]

    def test_an_edit_never_approves_or_publishes(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        t = refresh(tt)
        assert t.status in (TimetableStatus.DRAFT, TimetableStatus.VALIDATED) and t.approved_by is None and t.published_at is None

    def test_an_incomplete_timetable_stays_unvalidated_after_an_edit(self, client, admin_headers, data):
        from app.tests.jiya.test_generation import disable_slots
        disable_slots(lambda s: s.day_of_week > 2)
        tid = gen()["id"]
        e = entries(tid)[0]
        target = first_free_option(options(client, admin_headers, tid, e.id))
        r = patch(client, admin_headers, tid, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        assert r.status_code == 200 and r.get_json()["data"]["validation"]["is_complete"] is False
        assert refresh(tid).validation_passed is False


class TestRollbackAndConcurrency:
    def test_a_failure_while_revalidating_leaves_the_original_rows(self, client, admin_headers, tt, monkeypatch):
        client.post(f"{URL}/{tt}/validate", headers=admin_headers)
        e = first_entry(tt, "CS301", "A")
        target = first_free_option(options(client, admin_headers, tt, e.id))
        before, t0 = snapshot(tt), refresh(tt)
        state = (t0.validation_passed, t0.status, t0.validated_at)
        monkeypatch.setattr(validation_service, "evaluate", lambda timetable: (_ for _ in ()).throw(RuntimeError("boom")))
        r = patch(client, admin_headers, tt, e.id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        assert r.status_code == 500
        db.session.expire_all()
        assert snapshot(tt) == before
        t = refresh(tt)
        assert (t.validation_passed, t.status, t.validated_at) == state

    def test_the_second_of_two_conflicting_edits_is_refused(self, client, admin_headers, tt):
        """Two admins looked at the same timetable; both want the same free period for the same teacher."""
        a, b = first_entry(tt, "CS301", "A"), first_entry(tt, "CS301", "B")  # same teacher
        shared = next(o for o in options(client, admin_headers, tt, a.id)["options"] if o["time_slot_id"] in {x["time_slot_id"] for x in options(client, admin_headers, tt, b.id)["options"]} and not o["is_current"])
        first = patch(client, admin_headers, tt, a.id, time_slot_id=shared["time_slot_id"], room_id=shared["rooms"][0]["id"])
        assert first.status_code == 200
        before = snapshot(tt)
        second = patch(client, admin_headers, tt, b.id, time_slot_id=shared["time_slot_id"], room_id=shared["rooms"][-1]["id"])
        assert second.status_code == 409 and "faculty_clash" in conflict_codes(second)
        assert snapshot(tt) == before

    def test_an_edit_made_from_a_stale_entry_id_is_refused(self, client, admin_headers, tt):
        e = first_entry(tt, "CS301", "A")
        old_id = e.id
        target = first_free_option(options(client, admin_headers, tt, e.id))
        patch(client, admin_headers, tt, old_id, time_slot_id=target["time_slot_id"], room_id=target["rooms"][0]["id"])
        r = patch(client, admin_headers, tt, old_id, room_id=Room.query.filter_by(code="R202").one().id)
        assert r.status_code == 404

    def test_the_lock_is_taken_before_anything_is_read(self, client, admin_headers, tt, monkeypatch):
        """On MySQL the timetable row is locked FOR UPDATE; here we prove the order: lock first, then entries."""
        from app.modules.jiya import edit_service
        order = []
        real_lock, real_session = edit_service._lock, edit_service.session_entries
        monkeypatch.setattr(edit_service, "_lock", lambda tid: (order.append("lock"), real_lock(tid))[1])
        monkeypatch.setattr(edit_service, "session_entries", lambda t, e: (order.append("read"), real_session(t, e))[1])
        e = first_entry(tt, "CS301", "A")
        patch(client, admin_headers, tt, e.id, room_id=Room.query.filter_by(code="R202").one().id)
        assert order[:2] == ["lock", "read"]


class TestPermissions:
    def test_login_is_required(self, client, tt):
        e = first_entry(tt, "CS301", "A")
        assert client.patch(f"{URL}/{tt}/entries/{e.id}", json={"room_id": 1}).status_code == 401
        assert client.get(f"{URL}/{tt}/entries/{e.id}/edit-options").status_code == 401

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers"])
    def test_non_admins_cannot_edit_or_even_list_options(self, client, request, tt, who):
        headers = request.getfixturevalue(who)
        e = first_entry(tt, "CS301", "A")
        before = snapshot(tt)
        assert patch(client, headers, tt, e.id, room_id=Room.query.filter_by(code="R202").one().id).status_code == 403
        assert client.get(f"{URL}/{tt}/entries/{e.id}/edit-options", headers=headers).status_code == 403
        assert snapshot(tt) == before
