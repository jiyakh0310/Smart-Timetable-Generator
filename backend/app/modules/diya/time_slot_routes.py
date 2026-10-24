"""Diya - R6 Time-Slot Management endpoints: /api/v1/time-slots

Read: any signed-in user (everyone needs the period structure to read a timetable).
Write: Admin only.
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.errors import AppError
from app.common.pagination import bool_arg, int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import Role, SlotType
from app.modules.diya import time_slot_service as service

bp = Blueprint("time_slots", __name__, url_prefix="/api/v1/time-slots")


@bp.get("")
@role_required()
def list_time_slots():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    day = int_arg("day", minimum=0, maximum=6)
    active = bool_arg("active")
    raw_type = request.args.get("slot_type")
    slot_type = None
    if raw_type:
        try:
            slot_type = SlotType(raw_type)
        except ValueError:
            raise AppError("validation_error", "'slot_type' must be class or break.", 400, {"slot_type": "Choose class or break."}) from None
    stmt = service.list_statement(day=day, slot_type=slot_type, active=active, q=request.args.get("q"))
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/<int:slot_id>")
@role_required()
def get_time_slot(slot_id):
    slot = service.get_or_404(slot_id)
    return success(service.serialize_many([slot])[0])


@bp.post("")
@role_required(Role.ADMIN)
def create_time_slots():
    slots = service.create_slots(json_body())
    return success({"items": service.serialize_many(slots)}, status=201, message=f"{len(slots)} time slot(s) created.")


@bp.patch("/<int:slot_id>")
@role_required(Role.ADMIN)
def update_time_slot(slot_id):
    slot = service.update_slot(service.get_or_404(slot_id), json_body())
    return success(service.serialize_many([slot])[0], message="Time slot updated.")


@bp.delete("/<int:slot_id>")
@role_required(Role.ADMIN)
def delete_time_slot(slot_id):
    service.delete_slot(service.get_or_404(slot_id))
    return success(message="Time slot deleted.")
