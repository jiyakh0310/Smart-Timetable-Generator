"""Isha - R13 Faculty availability and preferences (Admin-managed).

Meaning of the three statuses (stored in faculty_availability.status):
  * unavailable - HARD constraint: the generator must never schedule this faculty member in that slot.
  * preferred   - SOFT preference only: the generator may favour it, but must never treat it as a requirement.
  * available   - the default. No row is stored for it (the model documents "no row = available").

Rules:
  * only ACTIVE CLASS slots can be configured (breaks and disabled slots are rejected),
  * one entry per slot (duplicates in a request are rejected; the table is also unique per faculty + slot),
  * saving replaces the settings for all active class slots at once, but rows that point at slots which are
    currently disabled are left untouched, so a temporarily disabled slot never loses anyone's data.
"""
from app.common.errors import AppError
from app.extensions import db
from app.models import AvailabilityStatus, Faculty, FacultyAvailability, SlotType, TimeSlot
from app.modules.diya.time_slot_service import DAY_NAMES, fmt

STATUSES = {s.value: s for s in AvailabilityStatus}


def view(faculty: Faculty) -> dict:
    """Every time slot with this faculty member's status; the UI draws the weekly grid from this."""
    rows = {r.time_slot_id: r.status for r in db.session.scalars(db.select(FacultyAvailability).where(FacultyAvailability.faculty_id == faculty.id))}
    slots = db.session.scalars(db.select(TimeSlot).order_by(TimeSlot.day_of_week, TimeSlot.period_no)).all()
    items = [
        {
            "time_slot_id": s.id,
            "day_of_week": s.day_of_week,
            "day_name": DAY_NAMES[s.day_of_week],
            "period_no": s.period_no,
            "start_time": fmt(s.start_time),
            "end_time": fmt(s.end_time),
            "slot_type": s.slot_type.value,
            "is_active": bool(s.is_active),
            "status": rows.get(s.id, AvailabilityStatus.AVAILABLE).value,
        }
        for s in slots
    ]
    return {
        "faculty": {"id": faculty.id, "name": faculty.user.full_name, "employee_code": faculty.employee_code, "is_active": bool(faculty.user.is_active)},
        "slots": items,
        "summary": {
            "unavailable": sum(1 for i in items if i["status"] == "unavailable"),
            "preferred": sum(1 for i in items if i["status"] == "preferred"),
        },
    }


def replace(faculty: Faculty, data: dict) -> dict:
    unknown = sorted(set(data) - {"entries"})
    if unknown:
        raise AppError("validation_error", f"Unknown field(s): {', '.join(unknown)}.", 400, {u: "Not allowed." for u in unknown})
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise AppError("validation_error", "'entries' must be a list.", 400, {"entries": "Send a list of {time_slot_id, status}."})

    errors: dict = {}
    wanted: dict[int, AvailabilityStatus] = {}
    for i, entry in enumerate(entries):
        key = f"entries.{i}"
        if not isinstance(entry, dict) or set(entry) - {"time_slot_id", "status"}:
            errors[key] = "Each entry must be {time_slot_id, status}."
            continue
        slot_id, status = entry.get("time_slot_id"), entry.get("status")
        if isinstance(slot_id, bool) or not isinstance(slot_id, int):
            errors[key] = "time_slot_id must be a whole number."
        elif status not in STATUSES:
            errors[key] = "status must be available, unavailable or preferred."
        elif slot_id in wanted:
            errors[key] = f"Time slot {slot_id} appears more than once."
        else:
            wanted[slot_id] = STATUSES[status]
    if errors:
        raise AppError("validation_error", "Please correct the availability entries.", 400, errors)

    slots = {s.id: s for s in db.session.scalars(db.select(TimeSlot).where(TimeSlot.id.in_(list(wanted)))).all()} if wanted else {}
    for i, entry in enumerate(entries):
        slot = slots.get(entry["time_slot_id"])
        key = f"entries.{i}"
        if slot is None:
            errors[key] = f"Time slot {entry['time_slot_id']} does not exist."
        elif slot.slot_type != SlotType.CLASS:
            errors[key] = f"{DAY_NAMES[slot.day_of_week]} period {slot.period_no} is a break and cannot be configured."
        elif not slot.is_active:
            errors[key] = f"{DAY_NAMES[slot.day_of_week]} period {slot.period_no} is disabled and cannot be configured."
    if errors:
        raise AppError("validation_error", "Some time slots cannot be used.", 400, errors)

    active_class_ids = set(db.session.scalars(db.select(TimeSlot.id).where(TimeSlot.is_active.is_(True), TimeSlot.slot_type == SlotType.CLASS)).all())
    existing = {r.time_slot_id: r for r in faculty.availability}
    for slot_id in active_class_ids:
        desired = wanted.get(slot_id)
        row = existing.get(slot_id)
        if desired is None or desired == AvailabilityStatus.AVAILABLE:  # default: store nothing
            if row is not None:
                faculty.availability.remove(row)
        elif row is not None:
            row.status = desired
        else:
            faculty.availability.append(FacultyAvailability(time_slot_id=slot_id, status=desired))
    db.session.commit()
    return view(faculty)
