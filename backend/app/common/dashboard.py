"""Shared admin-dashboard summary: real counts straight from the database."""
from flask import Blueprint
from sqlalchemy import func

from app.common.auth import role_required
from app.common.responses import success
from app.extensions import db
from app.models import (
    Batch,
    Faculty,
    Role,
    Room,
    Student,
    Subject,
    TeachingAssignment,
    TimeSlot,
    Timetable,
    TimetableStatus,
)

bp = Blueprint("dashboard", __name__, url_prefix="/api/v1/admin")


def _count(model) -> int:
    return db.session.scalar(db.select(func.count()).select_from(model))


@bp.get("/summary")
@role_required(Role.ADMIN)
def summary():
    status_rows = db.session.execute(
        db.select(Timetable.status, func.count()).group_by(Timetable.status)
    ).all()
    by_status = {status.value: 0 for status in TimetableStatus}
    for status, count in status_rows:
        by_status[status.value] = count

    return success(
        {
            "counts": {
                "faculty": _count(Faculty),
                "students": _count(Student),
                "batches": _count(Batch),
                "subjects": _count(Subject),
                "rooms": _count(Room),
                "time_slots": _count(TimeSlot),
                "teaching_assignments": _count(TeachingAssignment),
            },
            "timetables": {"total": sum(by_status.values()), "by_status": by_status},
        }
    )
