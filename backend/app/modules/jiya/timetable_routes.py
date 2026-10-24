"""Jiya - R7 / R10 timetable endpoints: /api/v1/timetables  (Admin only, enforced on the server)."""
from flask import Blueprint, g, request

from app.common.auth import role_required
from app.common.errors import AppError
from app.common.fields import reject_unknown
from app.common.pagination import int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import Role, TimetableStatus
from app.modules.isha import workload_service
from app.modules.jiya import timetable_service as service, validation_service

bp = Blueprint("timetables", __name__, url_prefix="/api/v1/timetables")


@bp.get("")
@role_required(Role.ADMIN)
def list_timetables():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    raw_status = request.args.get("status")
    status = None
    if raw_status:
        try:
            status = TimetableStatus(raw_status)
        except ValueError:
            raise AppError("validation_error", "'status' is not a valid timetable status.", 400, {"status": "Choose a valid status."}) from None
    stmt = service.list_statement(term_id=int_arg("term_id", minimum=1), status=status)
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/workload-preview")
@role_required(Role.ADMIN)
def workload_preview():
    """R14: before generating, what each faculty member's assignments need against their weekly maximum (read-only)."""
    term_id = int_arg("term_id", minimum=1)
    if term_id is None:
        raise AppError("validation_error", "Choose a term.", 400, {"term_id": "Choose a term."})
    workload = workload_service.preview(term_id)
    return success({"term_id": term_id, "workload": workload, "warnings": workload_service.assignment_warnings(workload)})


@bp.get("/<int:timetable_id>")
@role_required(Role.ADMIN)
def get_timetable(timetable_id):
    return success(service.detail(service.get_or_404(timetable_id)))


@bp.post("/generate")
@role_required(Role.ADMIN)
def generate_timetable():
    data = json_body()
    reject_unknown(data, {"term_id"}, AppError)
    term_id = data.get("term_id")
    if not isinstance(term_id, int) or isinstance(term_id, bool) or term_id < 1:
        raise AppError("validation_error", "Choose a term to generate for.", 400, {"term_id": "Choose a term."})
    result = service.generate(term_id, g.current_user.id)
    return success(result, 201, "Draft timetable generated.")


@bp.post("/<int:timetable_id>/validate")
@role_required(Role.ADMIN)
def validate_timetable(timetable_id):
    """R10: re-check the saved timetable (hard rules + completeness) and record validation_passed. Never approves or publishes."""
    return success(validation_service.validate(timetable_id), message="Validation finished.")


@bp.delete("/<int:timetable_id>")
@role_required(Role.ADMIN)
def discard_timetable(timetable_id):
    service.discard(service.get_or_404(timetable_id))
    return success(message="Draft timetable discarded.")
