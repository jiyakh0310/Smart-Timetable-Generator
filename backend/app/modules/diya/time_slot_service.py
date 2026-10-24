"""Diya - R6 Time-Slot Management: validation and business rules.

A time slot is one period on one weekday (day_of_week 0=Monday ... 6=Sunday).
The database guarantees: unique (day, period), start < end, day 0-6.
This service adds what the database cannot express:
  * slots on the same day must not overlap in time (back-to-back is fine: 10:00 end / 10:00 start),
  * period numbers must follow time order within a day (labs use consecutive periods),
  * a slot used by a timetable or by faculty availability cannot be deleted (disable it instead).
"""
import re
from datetime import time

from sqlalchemy import cast, func, or_, String
from sqlalchemy.exc import IntegrityError

from app.common.errors import AppError
from app.extensions import db
from app.models import FacultyAvailability, SlotType, TimeSlot, TimetableEntry

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_PERIOD_NO = 20
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
CREATE_FIELDS = {"days", "period_no", "start_time", "end_time", "slot_type", "is_active"}
UPDATE_FIELDS = {"day_of_week", "period_no", "start_time", "end_time", "slot_type", "is_active"}


# ---------- formatting ----------
def fmt(t: time) -> str:
    return t.strftime("%H:%M")


def usage_counts(slot_ids: list[int]) -> dict[int, dict]:
    """How many timetable entries / availability rows reference each slot (two queries, not N+1)."""
    usage = {sid: {"timetable_entries": 0, "faculty_availability": 0} for sid in slot_ids}
    if not slot_ids:
        return usage
    for model, key in ((TimetableEntry, "timetable_entries"), (FacultyAvailability, "faculty_availability")):
        rows = db.session.execute(
            db.select(model.time_slot_id, func.count()).where(model.time_slot_id.in_(slot_ids)).group_by(model.time_slot_id)
        ).all()
        for slot_id, count in rows:
            usage[slot_id][key] = count
    return usage


def serialize(slot: TimeSlot, usage: dict) -> dict:
    return {
        "id": slot.id,
        "day_of_week": slot.day_of_week,
        "day_name": DAY_NAMES[slot.day_of_week],
        "period_no": slot.period_no,
        "start_time": fmt(slot.start_time),
        "end_time": fmt(slot.end_time),
        "slot_type": slot.slot_type.value,
        "is_active": bool(slot.is_active),
        "usage": usage,
        "in_use": usage["timetable_entries"] > 0 or usage["faculty_availability"] > 0,
    }


def serialize_many(slots: list[TimeSlot]) -> list[dict]:
    usage = usage_counts([s.id for s in slots])
    return [serialize(s, usage[s.id]) for s in slots]


# ---------- queries ----------
def list_statement(day=None, slot_type=None, active=None, q=None):
    stmt = db.select(TimeSlot).order_by(TimeSlot.day_of_week, TimeSlot.period_no)
    if day is not None:
        stmt = stmt.where(TimeSlot.day_of_week == day)
    if slot_type is not None:
        stmt = stmt.where(TimeSlot.slot_type == slot_type)
    if active is not None:
        stmt = stmt.where(TimeSlot.is_active == active)
    if q:
        term = q.strip()
        clauses = [cast(TimeSlot.start_time, String).like(f"{term}%"), cast(TimeSlot.end_time, String).like(f"{term}%")]
        if term.isdigit():
            clauses.append(TimeSlot.period_no == int(term))
        stmt = stmt.where(or_(*clauses))
    return stmt


def get_or_404(slot_id: int) -> TimeSlot:
    slot = db.session.get(TimeSlot, slot_id)
    if slot is None:
        raise AppError("not_found", "Time slot not found.", 404)
    return slot


# ---------- validation ----------
def _int(value, field, errors, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = "Must be a whole number."
        return None
    if value < minimum or value > maximum:
        errors[field] = f"Must be between {minimum} and {maximum}."
        return None
    return value


def _time(value, field, errors):
    if not isinstance(value, str) or not _TIME_RE.match(value.strip()):
        errors[field] = "Use 24-hour time as HH:MM, e.g. 09:00."
        return None
    hh, mm = value.strip().split(":")
    return time(int(hh), int(mm))


def _days(value, errors) -> list[int]:
    if not isinstance(value, list) or not value:
        errors["days"] = "Select at least one day."
    elif any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in value):
        errors["days"] = "Days must be numbers from 0 (Monday) to 6 (Sunday)."
    elif len(set(value)) != len(value):
        errors["days"] = "Each day can only be selected once."
    else:
        return value
    return []


def _required(data: dict, field: str, errors: dict):
    """Value of a mandatory field, or record 'required' and return None."""
    if data.get(field) in (None, ""):
        errors[field] = "This field is required."
        return None
    return data[field]


def _slot_type(value, errors):
    try:
        return SlotType(value)
    except (ValueError, TypeError):
        errors["slot_type"] = "Choose class or break."
        return None


def _reject_unknown(data: dict, allowed: set[str]):
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise AppError("validation_error", f"Unknown field(s): {', '.join(unknown)}.", 400, {u: "Not allowed." for u in unknown})


def _check_times(start, end, errors):
    if start and end and start >= end:
        errors["end_time"] = "End time must be after the start time."


def _raise_if(errors):
    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)


def _check_conflicts(day: int, period_no: int, start: time, end: time, exclude_id: int | None = None) -> None:
    """Raise 409 if this slot clashes with another slot on the same weekday."""
    others = db.select(TimeSlot).where(TimeSlot.day_of_week == day)
    if exclude_id is not None:
        others = others.where(TimeSlot.id != exclude_id)
    name = DAY_NAMES[day]

    same_period = db.session.scalar(others.where(TimeSlot.period_no == period_no))
    if same_period:
        raise AppError(
            "duplicate_slot",
            f"{name} already has Period {period_no} ({fmt(same_period.start_time)}-{fmt(same_period.end_time)}).",
            409,
            {"period_no": f"Period {period_no} already exists on {name}."},
        )

    overlapping = db.session.scalar(others.where(TimeSlot.start_time < end, TimeSlot.end_time > start))
    if overlapping:
        raise AppError(
            "overlapping_slot",
            f"{name} {fmt(start)}-{fmt(end)} overlaps Period {overlapping.period_no} ({fmt(overlapping.start_time)}-{fmt(overlapping.end_time)}).",
            409,
            {"start_time": f"Overlaps Period {overlapping.period_no} on {name}.", "end_time": f"Overlaps Period {overlapping.period_no} on {name}."},
        )

    out_of_order = db.session.scalar(
        others.where(
            or_(
                db.and_(TimeSlot.period_no < period_no, TimeSlot.start_time >= start),
                db.and_(TimeSlot.period_no > period_no, TimeSlot.start_time < start),
            )
        )
    )
    if out_of_order:
        raise AppError(
            "invalid_period_order",
            f"Period numbers must follow time order on {name}: Period {out_of_order.period_no} starts at {fmt(out_of_order.start_time)}.",
            409,
            {"period_no": "Period number does not match the time order for this day."},
        )


# ---------- commands ----------
def create_slots(data: dict) -> list[TimeSlot]:
    """Create the same period on one or more weekdays (all-or-nothing)."""
    _reject_unknown(data, CREATE_FIELDS)
    errors: dict = {}

    clean_days = _days(data.get("days"), errors)
    raw_period = _required(data, "period_no", errors)
    period_no = _int(raw_period, "period_no", errors, 1, MAX_PERIOD_NO) if raw_period is not None else None
    raw_start = _required(data, "start_time", errors)
    start = _time(raw_start, "start_time", errors) if raw_start is not None else None
    raw_end = _required(data, "end_time", errors)
    end = _time(raw_end, "end_time", errors) if raw_end is not None else None
    slot_type = _slot_type(data.get("slot_type", "class"), errors)
    is_active = data.get("is_active", True)
    if not isinstance(is_active, bool):
        errors["is_active"] = "Must be true or false."
    _check_times(start, end, errors)
    _raise_if(errors)

    for day in clean_days:
        _check_conflicts(day, period_no, start, end)
    slots = [
        TimeSlot(day_of_week=day, period_no=period_no, start_time=start, end_time=end, slot_type=slot_type, is_active=is_active)
        for day in clean_days
    ]
    db.session.add_all(slots)
    _commit()
    return slots


def update_slot(slot: TimeSlot, data: dict) -> TimeSlot:
    _reject_unknown(data, UPDATE_FIELDS)
    if not data:
        raise AppError("validation_error", "Nothing to update.", 400)
    errors: dict = {}

    day = _int(data["day_of_week"], "day_of_week", errors, 0, 6) if "day_of_week" in data else slot.day_of_week
    period_no = _int(data["period_no"], "period_no", errors, 1, MAX_PERIOD_NO) if "period_no" in data else slot.period_no
    start = _time(data["start_time"], "start_time", errors) if "start_time" in data else slot.start_time
    end = _time(data["end_time"], "end_time", errors) if "end_time" in data else slot.end_time
    slot_type = _slot_type(data["slot_type"], errors) if "slot_type" in data else slot.slot_type
    is_active = data.get("is_active", slot.is_active)
    if not isinstance(is_active, bool):
        errors["is_active"] = "Must be true or false."
    _check_times(start, end, errors)
    _raise_if(errors)

    # Moving a slot that a timetable already uses could silently change what has been scheduled.
    moved = (day, period_no, start, end) != (slot.day_of_week, slot.period_no, slot.start_time, slot.end_time)
    if moved and usage_counts([slot.id])[slot.id]["timetable_entries"] > 0:
        raise AppError(
            "slot_in_use",
            "This time slot is used by a timetable, so its day, period or times cannot be changed. You can still disable it or change its type.",
            409,
        )

    _check_conflicts(day, period_no, start, end, exclude_id=slot.id)
    slot.day_of_week, slot.period_no, slot.start_time, slot.end_time = day, period_no, start, end
    slot.slot_type, slot.is_active = slot_type, is_active
    _commit()
    return slot


def delete_slot(slot: TimeSlot) -> None:
    usage = usage_counts([slot.id])[slot.id]
    if usage["timetable_entries"] or usage["faculty_availability"]:
        parts = []
        if usage["timetable_entries"]:
            parts.append(f"{usage['timetable_entries']} timetable entr{'y' if usage['timetable_entries'] == 1 else 'ies'}")
        if usage["faculty_availability"]:
            parts.append(f"{usage['faculty_availability']} faculty availability record(s)")
        raise AppError(
            "slot_in_use",
            f"This time slot is in use ({' and '.join(parts)}) and cannot be deleted. Disable it instead to stop it being scheduled.",
            409,
            usage,
        )
    db.session.delete(slot)
    _commit()


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        # Two admins saving the same period at once: the unique constraint is the last line of defence.
        db.session.rollback()
        raise AppError("duplicate_slot", "That day and period already exist.", 409) from None
