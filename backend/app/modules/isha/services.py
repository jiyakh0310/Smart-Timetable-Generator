"""Isha - User & Faculty Management: authentication logic (R1)."""
from datetime import datetime, timezone

from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from app.common.errors import AppError
from app.extensions import db
from app.models import Faculty, Role, Student, User

MIN_PASSWORD_LENGTH = 8

# Checked when the email is unknown so response time doesn't reveal which emails exist.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def authenticate(email: str, password: str) -> User:
    user = db.session.scalar(db.select(User).where(func.lower(User.email) == email.strip().lower()))
    password_ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if user is None or not password_ok or not user.is_active:
        # One generic message for wrong email, wrong password and disabled account.
        raise AppError("invalid_credentials", "Invalid email or password.", 401)
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return user


def change_password(user: User, current_password: str, new_password: str) -> None:
    if not user.check_password(current_password):
        raise AppError("invalid_credentials", "Current password is incorrect.", 400, {"current_password": "Incorrect password."})
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise AppError(
            "validation_error",
            f"New password must be at least {MIN_PASSWORD_LENGTH} characters.",
            400,
            {"new_password": f"Use at least {MIN_PASSWORD_LENGTH} characters."},
        )
    if new_password == current_password:
        raise AppError("validation_error", "New password must be different.", 400, {"new_password": "Choose a different password."})
    user.set_password(new_password)
    db.session.commit()


def profile_for(user: User) -> dict:
    """User details plus the role-specific profile (faculty record or student batch)."""
    data = user.to_dict()
    if user.role == Role.FACULTY:
        faculty = db.session.scalar(db.select(Faculty).where(Faculty.user_id == user.id))
        data["faculty"] = (
            {
                "employee_code": faculty.employee_code,
                "department": faculty.department.name,
                "designation": faculty.designation,
                "max_weekly_hours": faculty.max_weekly_hours,
            }
            if faculty
            else None
        )
    elif user.role == Role.STUDENT:
        student = db.session.scalar(db.select(Student).where(Student.user_id == user.id))
        data["student"] = (
            {
                "enrollment_no": student.enrollment_no,
                "batch": student.batch.name,
                "batch_strength": student.batch.strength,
                "semester_no": student.batch.semester_no,
                "program": student.batch.program.name,
                "department": student.batch.department.name,
            }
            if student
            else None
        )
    return data
