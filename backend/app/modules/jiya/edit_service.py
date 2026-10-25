"""Jiya - R15 manual editing of one session of a saved timetable (Admin only).

WHAT CAN BE EDITED
  * Only `draft` and `validated` timetables (EDITABLE). Approved, published and every other status are immutable (409).
  * One SESSION at a time: a theory class (one entry) or a whole lab session (`lab_block_periods` consecutive entries).
    The caller names any entry of the session and gives the new start `time_slot_id` and/or `room_id`; a lab keeps its
    length and moves as one block. The assignment, faculty, batch and session length can never change, so an edit cannot add,
    remove or convert a required session.
HOW IT IS KEPT SAFE
  * Every rule comes from the existing services: `check_session` (overlaps by real clock time, capacity, room type and service,
    breaks / disabled slots, lab length and consecutiveness, hard unavailability) and `workload_service` (weekly hours).
    The client's list of eligible choices is a convenience only; this module re-checks everything.
  * The moved session must leave NO hard conflict in its new position (even one that already existed there); advisory notes
    (a faculty preference) are returned as warnings and never block.
  * One transaction: the timetable row is locked (after ending any read snapshot), the rows are re-read under the lock, the
    session is replaced, the whole timetable is re-validated and the result recorded, then everything commits. Any failure
    rolls back and the original entries are untouched. Two admins editing at once are serialised, so the second is checked
    against the first one's result.
  * Because the moved rows are replaced, a moved session gets new entry ids. A previous validation result never survives:
    the fresh result for the new contents is recorded (`validation_passed`, `validated_at`, draft <-> validated).
  * No audit table exists in this project, so each successful edit is written to the application log.
"""
from flask import current_app, g

from app.common.errors import AppError
from app.common.fields import reject_unknown
from app.extensions import db
from app.models import ClassType, Room, TimeSlot, Timetable, TimetableEntry
from app.modules.isha import workload_service
from app.modules.jiya import generator, timetable_service as service, validation_service
from app.modules.pragya import clash_service as clash
from app.modules.pragya.clash_service import HARD, Conflict, Placement, PlanningContext

EDITABLE = service.EDITABLE
ROOM_CODES = {"room_clash", "room_too_small", "room_unavailable", "room_type_mismatch"}


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _lock(timetable_id: int) -> Timetable:
    """End any read snapshot, then take the row lock; every read after this sees what the previous editor committed."""
    db.session.commit()
    db.session.execute(db.select(Timetable.id).where(Timetable.id == timetable_id).with_for_update())
    return service.get_or_404(timetable_id)


def _require_editable(timetable: Timetable):
    if timetable.status not in EDITABLE:
        raise AppError("timetable_not_editable", f"A {timetable.status.value} timetable cannot be edited; only draft or validated timetables can.", 409)


def _entry_or_404(timetable: Timetable, entry_id: int) -> TimetableEntry:
    entry = db.session.get(TimetableEntry, entry_id)
    if entry is None or entry.timetable_id != timetable.id:
        raise AppError("not_found", "That entry is not part of this timetable.", 404)
    return entry


def session_entries(timetable: Timetable, entry: TimetableEntry) -> list[TimetableEntry]:
    """The entry plus, for a lab, the other periods of the same session (in time order)."""
    subject = entry.assignment.subject
    if subject.class_type != ClassType.LAB:
        return [entry]
    block = subject.lab_block_periods
    same_day = sorted(
        (e for e in db.session.scalars(db.select(TimetableEntry).where(TimetableEntry.timetable_id == timetable.id, TimetableEntry.assignment_id == entry.assignment_id))
         if e.time_slot.day_of_week == entry.time_slot.day_of_week),
        key=lambda e: e.time_slot.period_no,
    )
    runs, run = [], []
    for e in same_day:
        if run and e.time_slot.period_no != run[-1].time_slot.period_no + 1:
            runs.append(run)
            run = []
        run.append(e)
    runs.append(run)
    mine = next(r for r in runs if entry in r)
    chunk = mine[(mine.index(entry) // block) * block:][:block]
    if len(chunk) != block:
        raise AppError("session_malformed", f"This lab session has {len(chunk)} of its {block} periods saved, so it cannot be moved. Regenerate the timetable instead.", 409)
    return chunk


def window(start: TimeSlot, length: int) -> list[TimeSlot]:
    """`length` consecutive periods on the start slot's day (may come back shorter when the day does not have them)."""
    wanted = range(start.period_no, start.period_no + length)
    rows = db.session.scalars(db.select(TimeSlot).where(TimeSlot.day_of_week == start.day_of_week, TimeSlot.period_no.in_(list(wanted))).order_by(TimeSlot.period_no)).all()
    return list(rows)


def _hard_conflicts(timetable, session, faculty, batch, subject, room: Room, slots: list[TimeSlot], length: int, context=None) -> list[Conflict]:
    if len(slots) != length:
        return [Conflict("not_consecutive", HARD, f"A {length}-period session needs {length} consecutive periods starting at {clash.describe(slots[0]) if slots else 'that slot'}, but the day does not have them.", {})]
    placement = Placement(faculty.id, batch.id, room.id, tuple(s.id for s in slots), subject.id)
    found = clash.check_session(placement, clash.load_periods(timetable.id), ignore_entry_ids={e.id for e in session}, context=context)
    out = [c for c in found if c.severity == HARD]
    overload = workload_service.edit_overload(faculty, timetable.id, session, slots)
    if overload:
        out.append(overload)
    return out


def edit_entry(timetable_id: int, entry_id: int, data: dict) -> dict:
    reject_unknown(data, {"time_slot_id", "room_id"}, AppError)
    errors = {k: "Must be a positive whole number." for k in ("time_slot_id", "room_id") if k in data and not _positive_int(data[k])}
    if errors:
        raise AppError("validation_error", "Choose a valid time slot and room.", 400, errors)
    if not data:
        raise AppError("validation_error", "Choose a new time slot and/or room.", 400, {"time_slot_id": "Choose a new time slot or room."})
    try:
        timetable = _lock(timetable_id)
        _require_editable(timetable)
        entry = _entry_or_404(timetable, entry_id)
        session = session_entries(timetable, entry)
        length = len(session)
        first = session[0]
        start = db.session.get(TimeSlot, data.get("time_slot_id", first.time_slot_id))
        room = db.session.get(Room, data.get("room_id", first.room_id))
        if start is None:
            raise AppError("validation_error", "Unknown time slot.", 400, {"time_slot_id": "Choose an existing time slot."})
        if room is None:
            raise AppError("validation_error", "Unknown room.", 400, {"room_id": "Choose an existing room."})
        slots = window(start, length)
        if [s.id for s in slots] == [e.time_slot_id for e in session] and room.id == first.room_id:
            raise AppError("no_change", "That is where this session already is. Choose a different time slot or room.", 409)

        subject = entry.assignment.subject
        conflicts = _hard_conflicts(timetable, session, first.faculty, first.batch, subject, room, slots, length)
        if conflicts:
            raise AppError("edit_conflict", conflicts[0].message + (f" (+{len(conflicts) - 1} more problem{'s' if len(conflicts) > 2 else ''})" if len(conflicts) > 1 else ""), 409,
                           {"conflicts": [c.to_dict() for c in conflicts]})
        advisory = [c.to_dict() for c in clash.check_session(Placement(first.faculty_id, first.batch_id, room.id, tuple(s.id for s in slots), subject.id),
                                                               clash.load_periods(timetable.id), ignore_entry_ids={e.id for e in session}) if c.severity != HARD]

        old = [(e.time_slot_id, e.room_id) for e in session]
        assignment_id, faculty_id, batch_id = first.assignment_id, first.faculty_id, first.batch_id
        for e in session:
            db.session.delete(e)
        db.session.flush()  # free the old slots before the new rows are inserted (unique keys)
        created = [TimetableEntry(timetable_id=timetable.id, assignment_id=assignment_id, faculty_id=faculty_id, batch_id=batch_id, room_id=room.id, time_slot_id=s.id) for s in slots]
        db.session.add_all(created)
        db.session.flush()
        validation = validation_service.evaluate(timetable)  # the stored result must describe the NEW contents
        edited_ids = [e.id for e in created]
        user_id = getattr(g, "current_user", None) and g.current_user.id
        current_app.logger.info("timetable_entry_edited timetable=%s user=%s assignment=%s from=%s to=%s validation_passed=%s", timetable.id, user_id, assignment_id, old,
                                [(s.id, room.id) for s in slots], validation["validation_passed"])
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    result = service.detail(service.get_or_404(timetable_id))
    return {"timetable": result, "edited_entry_ids": edited_ids, "warnings": advisory, "validation": validation}


def options(timetable_id: int, entry_id: int) -> dict:
    """Eligible choices for one session (a convenience for the UI; edit_entry re-checks everything on save)."""
    timetable = service.get_or_404(timetable_id)
    _require_editable(timetable)
    entry = _entry_or_404(timetable, entry_id)
    session = session_entries(timetable, entry)
    length, first = len(session), session[0]
    subject = entry.assignment.subject
    ctx = PlanningContext()
    scheduled = clash.load_periods(timetable.id)
    ignore = {e.id for e in session}
    current_ids = [e.time_slot_id for e in session]
    out = []
    for run in generator.windows_for(generator.class_slots(), length):
        ids = tuple(s.id for s in run)
        probe = Placement(first.faculty_id, first.batch_id, first.room_id, ids, subject.id)
        blocking = {c.code for c in clash.check_session(probe, scheduled, ignore_entry_ids=ignore, context=ctx) if c.severity == HARD} - ROOM_CODES
        if blocking or workload_service.edit_overload(first.faculty, timetable.id, session, list(run)):
            continue
        rooms = clash.rank_rooms(subject, first.batch, ids, scheduled, ignore_entry_ids=ignore, context=ctx)
        if not rooms:
            continue
        out.append({
            "time_slot_id": run[0].id,
            "day_of_week": run[0].day_of_week,
            "day_name": clash.DAY_NAMES[run[0].day_of_week],
            "period_no": run[0].period_no,
            "start_time": run[0].start_time.strftime("%H:%M"),
            "end_time": run[-1].end_time.strftime("%H:%M"),
            "is_current": list(ids) == current_ids,
            "rooms": [{"id": r.id, "code": r.code, "name": r.name, "capacity": r.capacity, "room_type": r.room_type.value, "is_current": r.id == first.room_id} for r in rooms],
        })
    return {
        "entry_id": entry.id,
        "entry_ids": [e.id for e in session],
        "periods": length,
        "subject": {"code": subject.code, "name": subject.name, "class_type": subject.class_type.value},
        "batch": {"id": first.batch.id, "name": first.batch.name},
        "faculty": {"id": first.faculty.id, "name": first.faculty.user.full_name},
        "current": {"time_slot_id": session[0].time_slot_id, "room_id": first.room_id},
        "options": out,
    }
