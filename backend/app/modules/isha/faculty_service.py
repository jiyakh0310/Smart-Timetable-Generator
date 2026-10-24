"""Isha - R2 Faculty management: validation and business rules.

A faculty member is two linked rows: a `users` row (login: email, name, password, active flag, role = faculty)
and a `faculty` row (employee code, department, designation, weekly-hour limit). The schema makes the link
mandatory (faculty.user_id is NOT NULL), so creating a faculty member always creates their login too.

Safety rules:
  * the role is always `faculty` and can never be sent by a client,
  * the Admin sets the initial password; it is hashed immediately and never returned or logged,
  * employee codes are stored UPPER CASE; emails lower case; both unique regardless of case,
  * a faculty member with teaching assignments or timetable entries cannot be deleted - deactivate instead
    (deactivating disables the login immediately and keeps every record).
"""
import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common import fields
from app.common.errors import AppError
from app.extensions import db
from app.models import (
    AvailabilityStatus,
    Department,
    Faculty,
    FacultyAvailability,
    Role,
    TeachingAssignment,
    TimetableEntry,
    User,
)
from app.modules.isha.services import MIN_PASSWORD_LENGTH

MAX_WEEKLY_HOURS = 40
DEFAULT_WEEKLY_HOURS = 18
MAX_PASSWORD_LENGTH = 128
CREATE_FIELDS = {"name", "email", "employee_code", "department_id", "designation", "max_weekly_hours", "password"}
UPDATE_FIELDS = {"name", "email", "employee_code", "department_id", "designation", "max_weekly_hours", "is_active"}
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")


# ---------- reading ----------
def usage_counts(faculty_ids: list[int]) -> dict[int, dict]:
    usage = {f: {"teaching_assignments": 0, "timetable_entries": 0} for f in faculty_ids}
    if not faculty_ids:
        return usage
    for model, key in ((TeachingAssignment, "teaching_assignments"), (TimetableEntry, "timetable_entries")):
        for fid, n in db.session.execute(db.select(model.faculty_id, func.count()).where(model.faculty_id.in_(faculty_ids)).group_by(model.faculty_id)).all():
            usage[fid][key] = n
    return usage


def availability_counts(faculty_ids: list[int]) -> dict[int, dict]:
    counts = {f: {"unavailable": 0, "preferred": 0} for f in faculty_ids}
    if not faculty_ids:
        return counts
    rows = db.session.execute(
        db.select(FacultyAvailability.faculty_id, FacultyAvailability.status, func.count())
        .where(FacultyAvailability.faculty_id.in_(faculty_ids))
        .group_by(FacultyAvailability.faculty_id, FacultyAvailability.status)
    ).all()
    for fid, status, n in rows:
        if status.value in counts[fid]:
            counts[fid][status.value] = n
    return counts


def serialize(faculty: Faculty, usage: dict, availability: dict) -> dict:
    """Public shape. Never includes password_hash or the internal user_id."""
    return {
        "id": faculty.id,
        "employee_code": faculty.employee_code,
        "name": faculty.user.full_name,
        "email": faculty.user.email,
        "department": {"id": faculty.department.id, "code": faculty.department.code, "name": faculty.department.name},
        "designation": faculty.designation,
        "max_weekly_hours": faculty.max_weekly_hours,
        "is_active": bool(faculty.user.is_active),
        "last_login": faculty.user.last_login.isoformat() if faculty.user.last_login else None,
        "usage": usage,
        "in_use": usage["teaching_assignments"] > 0 or usage["timetable_entries"] > 0,
        "availability": availability,
    }


def serialize_many(rows: list[Faculty]) -> list[dict]:
    ids = [f.id for f in rows]
    usage, availability = usage_counts(ids), availability_counts(ids)
    return [serialize(f, usage[f.id], availability[f.id]) for f in rows]


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_statement(department_id=None, active=None, q=None):
    stmt = (
        db.select(Faculty).join(User, Faculty.user_id == User.id)
        .options(joinedload(Faculty.user), joinedload(Faculty.department))
        .order_by(Faculty.employee_code)
    )
    if department_id is not None:
        stmt = stmt.where(Faculty.department_id == department_id)
    if active is not None:
        stmt = stmt.where(User.is_active == active)
    if q and q.strip():
        like = _like(q)
        stmt = stmt.where(or_(*(func.lower(col).like(like, escape="\\") for col in (Faculty.employee_code, User.full_name, User.email))))
    return stmt


def get_or_404(faculty_id: int) -> Faculty:
    faculty = db.session.get(Faculty, faculty_id)
    if faculty is None:
        raise AppError("not_found", "Faculty member not found.", 404)
    return faculty


# ---------- validation ----------
def clean_password(password, errors: dict, field: str = "password", forbid: tuple = ()):
    """Initial / reset password policy. Stricter than self-service because the Admin usually shares it."""
    if not isinstance(password, str) or not password:
        errors[field] = "This field is required."
        return None
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        errors[field] = f"Use {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters."
    elif not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errors[field] = "Include at least one letter and one number."
    elif password.strip().lower() in {f.strip().lower() for f in forbid if f}:
        errors[field] = "The password must not be the same as the email, employee code or name."
    else:
        return password
    return None


def clean(data: dict, faculty: Faculty | None = None) -> dict:
    allowed = CREATE_FIELDS if faculty is None else UPDATE_FIELDS
    unknown = sorted(set(data) - allowed)
    if unknown:
        hint = " Faculty accounts always have the faculty role." if "role" in unknown else ""
        raise AppError("validation_error", f"Unknown field(s): {', '.join(unknown)}.{hint}", 400, {u: "Not allowed." for u in unknown})
    if faculty is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)

    current = {}
    if faculty is not None:
        current = {
            "name": faculty.user.full_name, "email": faculty.user.email, "employee_code": faculty.employee_code, "department_id": faculty.department_id,
            "designation": faculty.designation, "max_weekly_hours": faculty.max_weekly_hours, "is_active": bool(faculty.user.is_active),
        }
    merged = {**current, **data}
    errors: dict = {}
    out: dict = {}

    for f in ("name", "email", "employee_code", "department_id"):
        if merged.get(f) in (None, ""):
            errors[f] = "This field is required."

    if "name" not in errors:
        out["name"] = fields.text(merged["name"], "name", errors, 2, 120, "Name")
    if "email" not in errors:
        out["email"] = fields.email(merged["email"], "email", errors)
    if "employee_code" not in errors:
        code = merged["employee_code"].strip().upper() if isinstance(merged["employee_code"], str) else None
        if not code or len(code) > 30 or not _CODE_RE.match(code):
            errors["employee_code"] = "Use up to 30 letters, digits or . _ / - (e.g. F001)."
        out["employee_code"] = code
    if "department_id" not in errors:
        dep_id = fields.whole_number(merged["department_id"], "department_id", errors, 1, 2**31 - 1)
        if dep_id is not None and db.session.get(Department, dep_id) is None:
            errors["department_id"] = "Choose an existing department."
        out["department_id"] = dep_id

    out["designation"] = fields.optional_text(merged.get("designation"), "designation", errors, 80)

    hours = merged.get("max_weekly_hours")
    out["max_weekly_hours"] = fields.whole_number(DEFAULT_WEEKLY_HOURS if hours in (None, "") else hours, "max_weekly_hours", errors, 1, MAX_WEEKLY_HOURS)

    if faculty is not None:
        is_active = merged.get("is_active", True)
        if not isinstance(is_active, bool):
            errors["is_active"] = "Must be true or false."
        out["is_active"] = is_active
    else:
        out["password"] = clean_password(
            data.get("password"), errors, forbid=(out.get("email"), out.get("employee_code"), out.get("name"), data.get("email"), data.get("employee_code"), data.get("name"))
        )

    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)
    return out


def _check_unique(values: dict, faculty: Faculty | None) -> None:
    mail = db.select(User.id).where(func.lower(User.email) == values["email"])
    code = db.select(Faculty.id).where(func.upper(Faculty.employee_code) == values["employee_code"])
    if faculty is not None:
        mail, code = mail.where(User.id != faculty.user_id), code.where(Faculty.id != faculty.id)
    if db.session.scalar(mail) is not None:
        raise AppError("duplicate_faculty", "Another account already uses this email address.", 409, {"email": "This email is already used by another account."})
    if db.session.scalar(code) is not None:
        raise AppError("duplicate_faculty", f"A faculty member with employee code {values['employee_code']} already exists.", 409,
                       {"employee_code": "This employee code is already used."})


# ---------- commands ----------
def create_faculty(data: dict) -> Faculty:
    values = clean(data)
    _check_unique(values, None)
    user = User(email=values["email"], full_name=values["name"], role=Role.FACULTY, is_active=True)  # role is fixed, never client-supplied
    user.set_password(values["password"])
    db.session.add(user)
    db.session.flush()
    faculty = Faculty(
        user_id=user.id, employee_code=values["employee_code"], department_id=values["department_id"],
        designation=values["designation"], max_weekly_hours=values["max_weekly_hours"],
    )
    db.session.add(faculty)
    _commit()
    return faculty


def update_faculty(faculty: Faculty, data: dict) -> Faculty:
    values = clean(data, faculty)
    _check_unique(values, faculty)
    faculty.user.full_name = values["name"]
    faculty.user.email = values["email"]
    faculty.user.is_active = values["is_active"]
    faculty.employee_code = values["employee_code"]
    faculty.department_id = values["department_id"]
    faculty.designation = values["designation"]
    faculty.max_weekly_hours = values["max_weekly_hours"]
    _commit()
    return faculty


def reset_password(faculty: Faculty, data: dict) -> None:
    unknown = sorted(set(data) - {"password"})
    if unknown:
        raise AppError("validation_error", f"Unknown field(s): {', '.join(unknown)}.", 400, {u: "Not allowed." for u in unknown})
    errors: dict = {}
    password = clean_password(data.get("password"), errors, forbid=(faculty.user.email, faculty.employee_code, faculty.user.full_name))
    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)
    faculty.user.set_password(password)
    db.session.commit()


def delete_faculty(faculty: Faculty) -> None:
    usage = usage_counts([faculty.id])[faculty.id]
    if usage["teaching_assignments"] or usage["timetable_entries"]:
        parts = []
        if usage["teaching_assignments"]:
            n = usage["teaching_assignments"]
            parts.append(f"{n} teaching assignment{'' if n == 1 else 's'}")
        if usage["timetable_entries"]:
            n = usage["timetable_entries"]
            parts.append(f"{n} timetable entr{'y' if n == 1 else 'ies'}")
        raise AppError(
            "faculty_in_use",
            f"This faculty member has {' and '.join(parts)} and cannot be deleted. Deactivate them instead: their login is disabled and all records are kept.",
            409,
            usage,
        )
    user = faculty.user
    db.session.delete(faculty)  # also removes their availability rows
    db.session.delete(user)  # the login exists only for this faculty record
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AppError("faculty_in_use", "This faculty member's account is referenced by other records and cannot be deleted. Deactivate them instead.", 409) from None


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # concurrent save of the same email/code: the unique keys are the last defence
        raise AppError("duplicate_faculty", "That email address or employee code is already used.", 409) from None
