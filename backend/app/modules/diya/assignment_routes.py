"""Teaching assignment endpoints: /api/v1/teaching-assignments (+ read-only /api/v1/terms lookup).

Admin only for now. Faculty and students will see "my subjects" through their own portal endpoints later.
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.errors import AppError
from app.common.pagination import int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import ClassType, Role
from app.modules.diya import assignment_service as service

bp = Blueprint("teaching_assignments", __name__, url_prefix="/api/v1/teaching-assignments")
terms_bp = Blueprint("terms", __name__, url_prefix="/api/v1/terms")


@bp.get("")
@role_required(Role.ADMIN)
def list_assignments():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    raw_type = request.args.get("class_type")
    class_type = None
    if raw_type:
        try:
            class_type = ClassType(raw_type)
        except ValueError:
            raise AppError("validation_error", "'class_type' must be theory or lab.", 400, {"class_type": "Choose theory or lab."}) from None
    stmt = service.list_statement(
        term_id=int_arg("term_id", minimum=1),
        batch_id=int_arg("batch_id", minimum=1),
        subject_id=int_arg("subject_id", minimum=1),
        faculty_id=int_arg("faculty_id", minimum=1),
        semester_no=int_arg("semester_no", minimum=1, maximum=12),
        class_type=class_type,
        q=request.args.get("q"),
    )
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/<int:assignment_id>")
@role_required(Role.ADMIN)
def get_assignment(assignment_id):
    return success(service.serialize_many([service.get_or_404(assignment_id)])[0])


@bp.post("")
@role_required(Role.ADMIN)
def create_assignment():
    assignment = service.create_assignment(json_body())
    return success(service.serialize_many([assignment])[0], status=201, message="Teaching assignment created.")


@bp.patch("/<int:assignment_id>")
@role_required(Role.ADMIN)
def update_assignment(assignment_id):
    assignment = service.update_assignment(service.get_or_404(assignment_id), json_body())
    return success(service.serialize_many([assignment])[0], message="Teaching assignment updated.")


@bp.delete("/<int:assignment_id>")
@role_required(Role.ADMIN)
def delete_assignment(assignment_id):
    service.delete_assignment(service.get_or_404(assignment_id))
    return success(message="Teaching assignment deleted.")


@terms_bp.get("")
@role_required()
def list_terms():
    """Read-only lookup for form dropdowns (terms are not managed from the UI yet)."""
    return success({"items": service.list_terms()})
