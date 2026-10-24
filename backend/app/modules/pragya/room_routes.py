"""Pragya - R5 Room endpoints: /api/v1/rooms  (+ R9 /rooms/suggest)

ALL operations are Admin-only for now. Room and timetable details reach faculty and students through their own
timetable views later.
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.errors import AppError
from app.common.pagination import bool_arg, int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.extensions import db
from app.models import Batch, Role, RoomType, Subject, Timetable
from app.modules.pragya import clash_service, room_service as service

bp = Blueprint("rooms", __name__, url_prefix="/api/v1/rooms")


def parse_id_list(raw: str | None, name: str) -> list[int]:
    try:
        values = [int(x) for x in (raw or "").split(",") if x.strip()]
    except ValueError:
        raise AppError("validation_error", f"'{name}' must be a comma-separated list of numbers.", 400, {name: "Use numbers such as 3,4."}) from None
    if not values:
        raise AppError("validation_error", f"'{name}' is required.", 400, {name: "This field is required."})
    return values


@bp.get("")
@role_required(Role.ADMIN)
def list_rooms():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    raw_type = request.args.get("room_type")
    room_type = None
    if raw_type:
        try:
            room_type = RoomType(raw_type)
        except ValueError:
            raise AppError("validation_error", "'room_type' must be classroom, lab, seminar_hall or auditorium.", 400, {"room_type": "Choose a valid room type."}) from None
    stmt = service.list_statement(room_type=room_type, available=bool_arg("available"), min_capacity=int_arg("min_capacity", minimum=1), q=request.args.get("q"))
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/suggest")
@role_required(Role.ADMIN)
def suggest_rooms():
    """Which rooms fit this class in these periods? Smallest suitable first; every other room with the reasons it is excluded."""
    subject = db.session.get(Subject, int_arg("subject_id", minimum=1) or 0)
    batch = db.session.get(Batch, int_arg("batch_id", minimum=1) or 0)
    if subject is None or batch is None:
        raise AppError("validation_error", "Choose an existing batch and subject.", 400, {"batch_id": "Required.", "subject_id": "Required."})
    slot_ids = parse_id_list(request.args.get("time_slot_ids"), "time_slot_ids")
    timetable_id = int_arg("timetable_id", minimum=1)
    if timetable_id is not None and db.session.get(Timetable, timetable_id) is None:
        raise AppError("not_found", "Timetable not found.", 404)
    verdicts = clash_service.explain_rooms(subject, batch, slot_ids, timetable_id=timetable_id)
    slot_problems = [c.to_dict() for c in clash_service.slot_problems(slot_ids)]
    brief = lambda r: {"id": r.id, "code": r.code, "name": r.name, "capacity": r.capacity, "room_type": r.room_type.value, "spare_seats": r.capacity - batch.strength}
    return success({
        "batch": {"id": batch.id, "name": batch.name, "strength": batch.strength},
        "subject": {"id": subject.id, "code": subject.code, "class_type": subject.class_type.value},
        "slot_problems": slot_problems,
        "suitable": [brief(v.room) for v in verdicts if v.suitable and not slot_problems],
        "excluded": [{**brief(v.room), "reasons": [{"code": c.code, "message": c.message} for c in v.reasons]} for v in verdicts if not v.suitable],
    })


@bp.get("/<int:room_id>")
@role_required(Role.ADMIN)
def get_room(room_id):
    return success(service.serialize_many([service.get_or_404(room_id)])[0])


@bp.post("")
@role_required(Role.ADMIN)
def create_room():
    return success(service.serialize_many([service.create_room(json_body())])[0], status=201, message="Room created.")


@bp.patch("/<int:room_id>")
@role_required(Role.ADMIN)
def update_room(room_id):
    room, warning = service.update_room(service.get_or_404(room_id), json_body())
    return success(service.serialize_many([room])[0], message=warning or "Room updated.")


@bp.delete("/<int:room_id>")
@role_required(Role.ADMIN)
def delete_room(room_id):
    service.delete_room(service.get_or_404(room_id))
    return success(message="Room deleted.")
