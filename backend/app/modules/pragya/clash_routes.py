"""Pragya - R8/R9 conflict-check endpoints: /api/v1/conflicts  (Admin only; the same functions are called in-process by the generator and editor)."""
from flask import Blueprint

from app.common.auth import role_required
from app.common.errors import AppError
from app.common.pagination import int_arg
from app.common.responses import success
from app.common.validation import json_body
from app.extensions import db
from app.models import Role, TeachingAssignment, Timetable
from app.modules.pragya import clash_service

bp = Blueprint("conflicts", __name__, url_prefix="/api/v1/conflicts")

CHECK_FIELDS = {"timetable_id", "assignment_id", "faculty_id", "batch_id", "subject_id", "room_id", "time_slot_ids", "ignore_entry_ids"}


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _id(data: dict, key: str, errors: dict, required: bool = True):
    value = data.get(key)
    if value is None:
        if required:
            errors[key] = "This field is required."
        return None
    if not _positive_int(value):
        errors[key] = "Must be a positive whole number."
        return None
    return value


def _id_list(data: dict, key: str, errors: dict, required: bool):
    value = data.get(key)
    if value is None:
        if required:
            errors[key] = "This field is required."
        return []
    if not isinstance(value, list) or (required and not value) or not all(_positive_int(v) for v in value):
        errors[key] = "Send a list of positive whole numbers."
        return []
    return value


@bp.post("/check")
@role_required(Role.ADMIN)
def check():
    """Would this class cause conflicts?
    Body: {room_id, time_slot_ids, (assignment_id | faculty_id + batch_id [+ subject_id]), timetable_id?, ignore_entry_ids?}"""
    data = json_body()
    unknown = sorted(set(data) - CHECK_FIELDS)
    if unknown:
        raise AppError("validation_error", f"Unknown field(s): {', '.join(unknown)}.", 400, {u: "Not allowed." for u in unknown})
    errors: dict = {}
    room_id = _id(data, "room_id", errors)
    slot_ids = _id_list(data, "time_slot_ids", errors, required=True)
    ignore = _id_list(data, "ignore_entry_ids", errors, required=False)
    timetable_id = _id(data, "timetable_id", errors, required=False)

    if data.get("assignment_id") is not None:
        assignment_id = _id(data, "assignment_id", errors)
        assignment = db.session.get(TeachingAssignment, assignment_id) if assignment_id else None
        if assignment_id and assignment is None:
            errors["assignment_id"] = "Choose an existing teaching assignment."
        faculty_id = batch_id = subject_id = None
        if assignment is not None:
            actual = {"faculty_id": assignment.faculty_id, "batch_id": assignment.batch_id, "subject_id": assignment.subject_id}
            for key, value in actual.items():
                if data.get(key) is not None and data[key] != value:
                    errors[key] = "Does not match the teaching assignment."
            faculty_id, batch_id, subject_id = actual["faculty_id"], actual["batch_id"], actual["subject_id"]
    else:
        faculty_id = _id(data, "faculty_id", errors)
        batch_id = _id(data, "batch_id", errors)
        subject_id = _id(data, "subject_id", errors, required=False)
    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)

    if timetable_id is not None and db.session.get(Timetable, timetable_id) is None:
        raise AppError("not_found", "Timetable not found.", 404)
    placement = clash_service.Placement(faculty_id, batch_id, room_id, tuple(slot_ids), subject_id)
    conflicts = clash_service.check_session(placement, timetable_id=timetable_id, ignore_entry_ids=ignore)
    hard = [c for c in conflicts if c.severity == clash_service.HARD]
    return success({
        "ok": not hard,  # advisory notes never make a placement invalid
        "hard_count": len(hard),
        "advisory_count": len(conflicts) - len(hard),
        "conflicts": [c.to_dict() for c in sorted(conflicts, key=lambda c: c.severity != clash_service.HARD)],
    })


@bp.get("/validate")
@role_required(Role.ADMIN)
def validate():
    """Re-check every entry of a saved timetable: ?timetable_id=N"""
    timetable_id = int_arg("timetable_id", minimum=1)
    if timetable_id is None:
        raise AppError("validation_error", "'timetable_id' is required.", 400, {"timetable_id": "This field is required."})
    return success(clash_service.validate_timetable(timetable_id).to_dict())
