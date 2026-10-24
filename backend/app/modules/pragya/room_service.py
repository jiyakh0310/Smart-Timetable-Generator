"""Pragya - R5 Classroom and laboratory management: validation and business rules.

The database guarantees: unique room code and capacity > 0. This service adds:
  * codes are stored UPPER CASE (MySQL compares them case-insensitively, SQLite does not),
  * capacity 1-2000; `lab_type` only for laboratories,
  * a room that timetable entries reference cannot be deleted, its type is locked, and its capacity cannot drop
    below the largest batch already scheduled in it,
  * marking such a room unavailable IS allowed (rooms must be able to go out of service); the response says how many
    entries are affected and validation will report them.
Equipment (R23, optional) is not part of this module yet.
"""
import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.common import fields
from app.common.errors import AppError
from app.extensions import db
from app.models import Batch, Room, RoomType, TimetableEntry

MAX_CAPACITY = 2000
FIELDS = {"code", "name", "location", "capacity", "room_type", "lab_type", "is_available"}
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")
TYPE_LABEL = {"classroom": "Classroom", "lab": "Laboratory", "seminar_hall": "Seminar hall", "auditorium": "Auditorium"}


# ---------- reading ----------
def usage_counts(room_ids: list[int]) -> dict[int, dict]:
    usage = {r: {"timetable_entries": 0, "largest_batch": 0} for r in room_ids}
    if not room_ids:
        return usage
    rows = db.session.execute(
        db.select(TimetableEntry.room_id, func.count(TimetableEntry.id), func.max(Batch.strength))
        .join(Batch, Batch.id == TimetableEntry.batch_id)
        .where(TimetableEntry.room_id.in_(room_ids))
        .group_by(TimetableEntry.room_id)
    ).all()
    for room_id, entries, largest in rows:
        usage[room_id] = {"timetable_entries": entries, "largest_batch": largest or 0}
    return usage


def serialize(room: Room, usage: dict) -> dict:
    return {
        "id": room.id,
        "code": room.code,
        "name": room.name,
        "location": room.location,
        "capacity": room.capacity,
        "room_type": room.room_type.value,
        "lab_type": room.lab_type,
        "is_available": bool(room.is_available),
        "usage": {"timetable_entries": usage["timetable_entries"]},
        "min_capacity": usage["largest_batch"],  # the capacity cannot be reduced below this while the room is scheduled
        "in_use": usage["timetable_entries"] > 0,
    }


def serialize_many(rooms: list[Room]) -> list[dict]:
    usage = usage_counts([r.id for r in rooms])
    return [serialize(r, usage[r.id]) for r in rooms]


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_statement(room_type=None, available=None, min_capacity=None, q=None):
    stmt = db.select(Room).order_by(Room.code)
    if room_type is not None:
        stmt = stmt.where(Room.room_type == room_type)
    if available is not None:
        stmt = stmt.where(Room.is_available == available)
    if min_capacity is not None:
        stmt = stmt.where(Room.capacity >= min_capacity)
    if q and q.strip():
        like = _like(q)
        stmt = stmt.where(or_(*(func.lower(c).like(like, escape="\\") for c in (Room.code, Room.name, Room.location))))
    return stmt


def get_or_404(room_id: int) -> Room:
    room = db.session.get(Room, room_id)
    if room is None:
        raise AppError("not_found", "Room not found.", 404)
    return room


# ---------- validation ----------
def clean(data: dict, room: Room | None = None) -> dict:
    fields.reject_unknown(data, FIELDS, AppError)
    if room is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)
    current = {}
    if room is not None:
        current = {"code": room.code, "name": room.name, "location": room.location, "capacity": room.capacity,
                   "room_type": room.room_type.value, "lab_type": room.lab_type, "is_available": bool(room.is_available)}
    merged = {**current, **data}
    errors: dict = {}
    out: dict = {}

    for f in ("code", "name", "capacity", "room_type"):
        if merged.get(f) in (None, ""):
            errors[f] = "This field is required."

    if "code" not in errors:
        code = merged["code"].strip().upper() if isinstance(merged["code"], str) else None
        if not code or len(code) > 30 or not _CODE_RE.match(code):
            errors["code"] = "Use up to 30 letters, digits or . _ / - (e.g. R101)."
        out["code"] = code
    if "name" not in errors:
        out["name"] = fields.text(merged["name"], "name", errors, 2, 100, "Name")
    out["location"] = fields.optional_text(merged.get("location"), "location", errors, 120)
    if "capacity" not in errors:
        out["capacity"] = fields.whole_number(merged["capacity"], "capacity", errors, 1, MAX_CAPACITY)
    room_type = None
    if "room_type" not in errors:
        try:
            room_type = RoomType(merged["room_type"])
        except (ValueError, TypeError):
            errors["room_type"] = "Choose classroom, lab, seminar hall or auditorium."
        out["room_type"] = room_type
    lab_type = fields.optional_text(merged.get("lab_type"), "lab_type", errors, 60)
    if lab_type is not None and room_type is not None and room_type != RoomType.LAB:
        errors["lab_type"] = "Only laboratories have a lab type."
    out["lab_type"] = lab_type
    is_available = merged.get("is_available", True)
    if not isinstance(is_available, bool):
        errors["is_available"] = "Must be true or false."
    out["is_available"] = is_available

    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)
    return out


def _check_unique(code: str, exclude_id: int | None) -> None:
    stmt = db.select(Room.id).where(func.upper(Room.code) == code)
    if exclude_id is not None:
        stmt = stmt.where(Room.id != exclude_id)
    if db.session.scalar(stmt) is not None:
        raise AppError("duplicate_room", f"A room with code {code} already exists.", 409, {"code": "This room code is already used."})


# ---------- commands ----------
def create_room(data: dict) -> Room:
    values = clean(data)
    _check_unique(values["code"], None)
    room = Room(**values)
    db.session.add(room)
    _commit()
    return room


def update_room(room: Room, data: dict) -> tuple[Room, str | None]:
    """Returns the room and an optional warning message (set when an in-use room is taken out of service)."""
    values = clean(data, room)
    _check_unique(values["code"], room.id)
    usage = usage_counts([room.id])[room.id]
    warning = None
    if usage["timetable_entries"]:
        if values["room_type"] != room.room_type:
            raise AppError("room_in_use", f"This room is used by {usage['timetable_entries']} timetable entries, so its type cannot be changed.", 409,
                           {"room_type": "Locked while a timetable uses this room."})
        if values["capacity"] < usage["largest_batch"]:
            raise AppError("room_in_use", f"A batch of {usage['largest_batch']} students is scheduled in this room, so its capacity cannot be less than {usage['largest_batch']}.", 409,
                           {"capacity": f"Cannot be less than {usage['largest_batch']} while it is scheduled."})
        if room.is_available and not values["is_available"]:
            warning = f"The room is now out of service but is still used by {usage['timetable_entries']} timetable entries. Validation will report them."
    for field, value in values.items():
        setattr(room, field, value)
    _commit()
    return room, warning


def delete_room(room: Room) -> None:
    usage = usage_counts([room.id])[room.id]
    if usage["timetable_entries"]:
        n = usage["timetable_entries"]
        raise AppError("room_in_use", f"This room is used by {n} timetable entr{'y' if n == 1 else 'ies'} and cannot be deleted. Mark it unavailable instead.", 409, usage)
    db.session.delete(room)  # its equipment links (if any) are removed by the database cascade
    _commit()


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AppError("duplicate_room", "A room with that code already exists.", 409, {"code": "This room code is already used."}) from None
