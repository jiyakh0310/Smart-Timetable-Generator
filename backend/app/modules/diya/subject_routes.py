"""Diya - R4 Subject/Course Management endpoints: /api/v1/subjects  (+ read-only /api/v1/departments lookup)

Read: any signed-in user.  Write: Admin only.
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.errors import AppError
from app.common.pagination import int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import ClassType, Role
from app.modules.diya import subject_service as service

bp = Blueprint("subjects", __name__, url_prefix="/api/v1/subjects")
departments_bp = Blueprint("departments", __name__, url_prefix="/api/v1/departments")


@bp.get("")
@role_required()
def list_subjects():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    department_id = int_arg("department_id", minimum=1)
    semester_no = int_arg("semester_no", minimum=1, maximum=service.MAX_SEMESTER)
    raw_type = request.args.get("class_type")
    class_type = None
    if raw_type:
        try:
            class_type = ClassType(raw_type)
        except ValueError:
            raise AppError("validation_error", "'class_type' must be theory or lab.", 400, {"class_type": "Choose theory or lab."}) from None
    stmt = service.list_statement(department_id, semester_no, class_type, request.args.get("q"))
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/<int:subject_id>")
@role_required()
def get_subject(subject_id):
    return success(service.serialize_many([service.get_or_404(subject_id)])[0])


@bp.post("")
@role_required(Role.ADMIN)
def create_subject():
    subject = service.create_subject(json_body())
    return success(service.serialize_many([subject])[0], status=201, message="Subject created.")


@bp.patch("/<int:subject_id>")
@role_required(Role.ADMIN)
def update_subject(subject_id):
    subject = service.update_subject(service.get_or_404(subject_id), json_body())
    return success(service.serialize_many([subject])[0], message="Subject updated.")


@bp.delete("/<int:subject_id>")
@role_required(Role.ADMIN)
def delete_subject(subject_id):
    service.delete_subject(service.get_or_404(subject_id))
    return success(message="Subject deleted.")


@departments_bp.get("")
@role_required()
def list_departments():
    """Small lookup list for form dropdowns (departments are not managed from the UI yet)."""
    return success({"items": service.list_departments()})
