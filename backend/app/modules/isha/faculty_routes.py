"""Isha - R2 Faculty endpoints: /api/v1/faculty  (+ R13 availability under /api/v1/faculty/:id/availability)

ALL operations are Admin-only. A faculty member sees their own profile through /auth/me; they cannot list
colleagues or edit anyone's availability (the Planning document makes self-service "if enabled by the
administrator", and there is no such switch yet).
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.pagination import bool_arg, int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import Role
from app.modules.isha import availability_service, faculty_service as service

bp = Blueprint("faculty", __name__, url_prefix="/api/v1/faculty")


@bp.get("")
@role_required(Role.ADMIN)
def list_faculty():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    stmt = service.list_statement(department_id=int_arg("department_id", minimum=1), active=bool_arg("active"), q=request.args.get("q"))
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/<int:faculty_id>")
@role_required(Role.ADMIN)
def get_faculty(faculty_id):
    return success(service.serialize_many([service.get_or_404(faculty_id)])[0])


@bp.post("")
@role_required(Role.ADMIN)
def create_faculty():
    faculty = service.create_faculty(json_body())
    return success(service.serialize_many([faculty])[0], status=201, message="Faculty member created.")


@bp.patch("/<int:faculty_id>")
@role_required(Role.ADMIN)
def update_faculty(faculty_id):
    faculty = service.update_faculty(service.get_or_404(faculty_id), json_body())
    return success(service.serialize_many([faculty])[0], message="Faculty member updated.")


@bp.post("/<int:faculty_id>/reset-password")
@role_required(Role.ADMIN)
def reset_password(faculty_id):
    service.reset_password(service.get_or_404(faculty_id), json_body())
    return success(message="Password reset. Share it with the faculty member securely.")


@bp.delete("/<int:faculty_id>")
@role_required(Role.ADMIN)
def delete_faculty(faculty_id):
    service.delete_faculty(service.get_or_404(faculty_id))
    return success(message="Faculty member deleted.")


@bp.get("/<int:faculty_id>/availability")
@role_required(Role.ADMIN)
def get_availability(faculty_id):
    return success(availability_service.view(service.get_or_404(faculty_id)))


@bp.put("/<int:faculty_id>/availability")
@role_required(Role.ADMIN)
def put_availability(faculty_id):
    data = availability_service.replace(service.get_or_404(faculty_id), json_body())
    return success(data, message="Availability saved.")
