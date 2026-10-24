"""Diya - R3 Student endpoints: /api/v1/students

Student records are personal data: ALL operations (including reads) are Admin-only.
A student sees their own profile through /auth/me; faculty have no documented need for the student list.
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.pagination import int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import Role
from app.modules.diya import student_service as service

bp = Blueprint("students", __name__, url_prefix="/api/v1/students")


@bp.get("")
@role_required(Role.ADMIN)
def list_students():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    stmt = service.list_statement(
        batch_id=int_arg("batch_id", minimum=1),
        semester_no=int_arg("semester_no", minimum=1, maximum=12),
        department_id=int_arg("department_id", minimum=1),
        q=request.args.get("q"),
    )
    return success(paginate(stmt, page, per_page, lambda rows: [service.serialize(s) for s in rows]))


@bp.get("/<int:student_id>")
@role_required(Role.ADMIN)
def get_student(student_id):
    return success(service.serialize(service.get_or_404(student_id)))


@bp.post("")
@role_required(Role.ADMIN)
def create_student():
    return success(service.serialize(service.create_student(json_body())), status=201, message="Student created.")


@bp.patch("/<int:student_id>")
@role_required(Role.ADMIN)
def update_student(student_id):
    student = service.update_student(service.get_or_404(student_id), json_body())
    return success(service.serialize(student), message="Student updated.")


@bp.delete("/<int:student_id>")
@role_required(Role.ADMIN)
def delete_student(student_id):
    login_disabled = service.delete_student(service.get_or_404(student_id))
    message = "Student deleted. Their login account was disabled." if login_disabled else "Student deleted."
    return success({"login_disabled": login_disabled}, message=message)
