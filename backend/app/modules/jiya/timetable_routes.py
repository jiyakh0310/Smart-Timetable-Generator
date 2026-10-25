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
from app.modules.jiya import approval_service, edit_service, export_service, timetable_service as service, validation_service

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


@bp.get("/<int:timetable_id>/entries/<int:entry_id>/edit-options")
@role_required(Role.ADMIN)
def edit_options(timetable_id, entry_id):
    """R15: the time slots and rooms a session could move to (advisory for the UI; the PATCH re-checks everything)."""
    return success(edit_service.options(timetable_id, entry_id))


@bp.patch("/<int:timetable_id>/entries/<int:entry_id>")
@role_required(Role.ADMIN)
def edit_entry(timetable_id, entry_id):
    """R15: move one session to another slot and/or room. Rejected (409) if it would create any hard conflict."""
    return success(edit_service.edit_entry(timetable_id, entry_id, json_body()), message="Session moved and the timetable re-validated.")


def _workflow(timetable_id, action, message, reason=None):
    return success(approval_service.transition(timetable_id, action, g.current_user.id, reason), message=message)


@bp.post("/<int:timetable_id>/submit")
@role_required(Role.ADMIN)
def submit_timetable(timetable_id):
    """R16: re-validate the saved timetable and send it for approval."""
    return _workflow(timetable_id, "submit", "Timetable submitted for approval.")


@bp.post("/<int:timetable_id>/approve")
@role_required(Role.ADMIN)
def approve_timetable(timetable_id):
    """R16: re-validate and approve. Does not publish."""
    return _workflow(timetable_id, "approve", "Timetable approved.")


@bp.post("/<int:timetable_id>/reject")
@role_required(Role.ADMIN)
def reject_timetable(timetable_id):
    """R16: send back (or withdraw an approval) with a written reason."""
    data = json_body()
    reject_unknown(data, {"reason"}, AppError)
    return _workflow(timetable_id, "reject", "Timetable rejected.", data.get("reason"))


@bp.post("/<int:timetable_id>/publish")
@role_required(Role.ADMIN)
def publish_timetable(timetable_id):
    """R16: re-validate and publish; the previously published version of the term becomes archived."""
    return _workflow(timetable_id, "publish", "Timetable published.")


@bp.get("/<int:timetable_id>/export")
@role_required(Role.ADMIN)
def export_timetable(timetable_id):
    """R18: PDF / Excel of a saved timetable, any status (?format=pdf|xlsx). Non-published documents are labelled as such."""
    return export_service.admin_export(timetable_id, request.args)


@bp.delete("/<int:timetable_id>")
@role_required(Role.ADMIN)
def discard_timetable(timetable_id):
    service.discard(service.get_or_404(timetable_id))
    return success(message="Draft timetable discarded.")
