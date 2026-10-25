"""Isha - R14 faculty workload: one place that measures teaching time and compares it with `faculty.max_weekly_hours`.

DEFINITIONS
  * Workload is TEACHING DURATION, not a count of entries: each timetable entry (one period) contributes the real length of
    its time slot (end - start). A 2-period lab therefore counts both periods. Results are reported in hours.
  * The limit is `faculty.max_weekly_hours` (hours per week, a hard limit). The column is NOT NULL, but if a limit is ever
    missing or not a positive whole number it means "no limit configured": nothing is enforced and no default is invented.
  * Hours needed BEFORE scheduling are a LOWER BOUND: sessions_per_week x session length x the shortest active class period.
    Real durations are only known once periods are chosen, so a lower bound never raises a false alarm.
"""
from collections import defaultdict

from app.extensions import db
from app.models import ClassType, Faculty, SlotType, Subject, TeachingAssignment, TimeSlot, TimetableEntry
from app.modules.pragya.clash_service import HARD, Conflict


def slot_minutes(slot: TimeSlot) -> int:
    return (slot.end_time.hour * 60 + slot.end_time.minute) - (slot.start_time.hour * 60 + slot.start_time.minute)


def hours(minutes: int | float) -> float:
    return round(minutes / 60, 2)


def limit_minutes(faculty: Faculty) -> int | None:
    value = faculty.max_weekly_hours
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value * 60


def scheduled_minutes(timetable_id: int) -> dict[int, int]:
    """Teaching minutes per faculty member actually saved in a timetable."""
    totals = defaultdict(int)
    rows = db.session.execute(
        db.select(TimetableEntry.faculty_id, TimeSlot.start_time, TimeSlot.end_time).join(TimeSlot, TimeSlot.id == TimetableEntry.time_slot_id).where(TimetableEntry.timetable_id == timetable_id)
    )
    for faculty_id, start, end in rows:
        totals[faculty_id] += (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return dict(totals)


def shortest_class_minutes() -> int:
    slots = db.session.scalars(db.select(TimeSlot).where(TimeSlot.is_active.is_(True), TimeSlot.slot_type == SlotType.CLASS)).all()
    return min((slot_minutes(s) for s in slots), default=0)


def assigned_minutes(term_id: int) -> dict[int, int]:
    """Lower bound of the minutes each faculty member's assignments need per week in a term."""
    shortest = shortest_class_minutes()
    totals = defaultdict(int)
    for faculty_id, class_type, block, sessions in db.session.execute(
        db.select(TeachingAssignment.faculty_id, Subject.class_type, Subject.lab_block_periods, TeachingAssignment.sessions_per_week)
        .join(Subject, Subject.id == TeachingAssignment.subject_id).where(TeachingAssignment.term_id == term_id)
    ):
        totals[faculty_id] += sessions * (block if class_type == ClassType.LAB else 1) * shortest
    return dict(totals)


def row(faculty: Faculty, scheduled: int, assigned: int) -> dict:
    """One faculty member's workload line. Hours; `overload_hours` is hard (scheduled > max), `over_assigned_hours` a pre-generation warning."""
    limit = limit_minutes(faculty)
    over = max(scheduled - limit, 0) if limit is not None else 0
    over_assigned = max(assigned - limit, 0) if limit is not None else 0
    if limit is None:
        status = "no_limit"
    elif over:
        status = "over_limit"
    elif scheduled == limit:
        status = "at_limit"          # placed right up to the maximum (any over-assignment is shown in over_assigned_hours)
    elif over_assigned:
        status = "over_assigned"
    else:
        status = "ok"
    return {
        "faculty_id": faculty.id,
        "employee_code": faculty.employee_code,
        "name": faculty.user.full_name,
        "max_hours": hours(limit) if limit is not None else None,
        "assigned_hours": hours(assigned),
        "scheduled_hours": hours(scheduled),
        "overload_hours": hours(over),
        "over_assigned_hours": hours(over_assigned),
        "status": status,
    }


def rows(faculty_list: list[Faculty], scheduled: dict[int, int], assigned: dict[int, int]) -> list[dict]:
    return sorted((row(f, scheduled.get(f.id, 0), assigned.get(f.id, 0)) for f in faculty_list), key=lambda r: (r["name"], r["faculty_id"]))


def term_faculty(term_id: int) -> list[Faculty]:
    return db.session.scalars(
        db.select(Faculty).join(TeachingAssignment, TeachingAssignment.faculty_id == Faculty.id).where(TeachingAssignment.term_id == term_id).distinct().order_by(Faculty.id)
    ).all()


def preview(term_id: int) -> list[dict]:
    """Before generating: what each faculty member's assignments need against their limit."""
    return rows(term_faculty(term_id), {}, assigned_minutes(term_id))


def assignment_warnings(workload: list[dict]) -> list[str]:
    out = []
    for r in workload:
        if r["status"] == "over_assigned":
            out.append(f"{r['name']} is assigned at least {r['assigned_hours']:g} h of teaching per week but the maximum is {r['max_hours']:g} h "
                       f"({r['over_assigned_hours']:g} h too many). Sessions that would exceed the limit will be left unscheduled.")
        elif r["status"] == "no_limit":
            out.append(f"{r['name']} has no weekly hour limit configured, so none was enforced.")
    return out


def timetable_rows(timetable) -> list[dict]:
    """Saved timetable: scheduled hours from the saved entries, assigned hours from the term's assignments."""
    scheduled = scheduled_minutes(timetable.id)
    faculty = {f.id: f for f in term_faculty(timetable.term_id)}
    for fid in scheduled:
        if fid not in faculty:
            faculty[fid] = db.session.get(Faculty, fid)
    return rows(list(faculty.values()), scheduled, assigned_minutes(timetable.term_id))


def overload_conflicts(timetable) -> list[Conflict]:
    """Hard errors for every faculty member whose saved timetable exceeds their weekly maximum."""
    out = []
    for r in timetable_rows(timetable):
        if r["status"] == "over_limit":
            out.append(Conflict("workload_exceeded", HARD,
                                f"{r['name']} is scheduled for {r['scheduled_hours']:g} h per week but the maximum is {r['max_hours']:g} h ({r['overload_hours']:g} h over).",
                                {"faculty_id": r["faculty_id"], "scheduled_hours": r["scheduled_hours"], "max_hours": r["max_hours"], "overload_hours": r["overload_hours"]}))
    return out


def edit_overload(faculty: Faculty, timetable_id: int, ignore_entries, new_slots) -> Conflict | None:
    """Would moving a session leave this faculty member above their weekly maximum? `ignore_entries` are the session's old rows."""
    limit = limit_minutes(faculty)
    if limit is None:
        return None
    old = {e.id for e in ignore_entries}
    kept = sum(m for m in _entry_minutes(timetable_id, faculty.id, old))
    total = kept + sum(slot_minutes(s) for s in new_slots)
    if total <= limit:
        return None
    return Conflict("workload_exceeded", HARD,
                    f"{faculty.user.full_name} would be scheduled for {hours(total):g} h per week but the maximum is {hours(limit):g} h ({hours(total - limit):g} h over).",
                    {"faculty_id": faculty.id, "scheduled_hours": hours(total), "max_hours": hours(limit), "overload_hours": hours(total - limit)})


def _entry_minutes(timetable_id: int, faculty_id: int, skip_ids: set):
    rows = db.session.execute(
        db.select(TimetableEntry.id, TimeSlot.start_time, TimeSlot.end_time).join(TimeSlot, TimeSlot.id == TimetableEntry.time_slot_id)
        .where(TimetableEntry.timetable_id == timetable_id, TimetableEntry.faculty_id == faculty_id)
    )
    return [(end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) for eid, start, end in rows if eid not in skip_ids]
