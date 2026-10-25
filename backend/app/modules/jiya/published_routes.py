"""Jiya / Diya - R11 / R12 read-only published timetable views: /api/v1/faculty/timetable and /api/v1/student/timetable.

Each endpoint is for exactly one role and answers only about the signed-in person. They are GET-only (other methods are 405).
"""
from flask import Blueprint, g, request

from app.common.auth import role_required
from app.common.responses import success
from app.models import Role
from app.modules.jiya import export_service, published_service as service

faculty_bp = Blueprint("faculty_timetable", __name__, url_prefix="/api/v1/faculty/timetable")
student_bp = Blueprint("student_timetable", __name__, url_prefix="/api/v1/student/timetable")


@faculty_bp.get("")
@role_required(Role.FACULTY)
def my_teaching_timetable():
    return success(service.faculty_view(g.current_user, request.args))


@student_bp.get("")
@role_required(Role.STUDENT)
def my_batch_timetable():
    return success(service.student_view(g.current_user, request.args))


@faculty_bp.get("/export")
@role_required(Role.FACULTY)
def export_my_teaching_timetable():
    """R18: PDF / Excel of the same data as the view above (?format=pdf|xlsx[&term_id=])."""
    return export_service.faculty_export(g.current_user, request.args)


@student_bp.get("/export")
@role_required(Role.STUDENT)
def export_my_batch_timetable():
    return export_service.student_export(g.current_user, request.args)
