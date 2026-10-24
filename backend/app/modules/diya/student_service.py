"""Diya - R3 Student management: validation and business rules.

Student records are personal data, so every endpoint is Admin-only (see student_routes.py).
  * enrollment numbers are stored UPPER CASE and are unique regardless of case,
  * emails (optional) are stored lower case and must not be shared by two students,
  * a student can only be added to / moved into a batch that still has room (batch.strength is the capacity),
  * deleting a student also DISABLES their linked login account, so no orphaned login can remain active.
    (The students table has no is_active column; deletion is the only way to remove a record.)
"""
import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common import fields
from app.common.errors import AppError
from app.extensions import db
from app.models import Batch, Role, Student

FIELDS = {"enrollment_no", "name", "email", "batch_id"}
_ENROLLMENT_RE = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")


# ---------- reading ----------
def serialize(student: Student) -> dict:
    b = student.batch
    return {
        "id": student.id,
        "enrollment_no": student.enrollment_no,
        "name": student.name,
        "email": student.email,
        "has_login": student.user_id is not None,
        "batch": {"id": b.id, "name": b.name, "semester_no": b.semester_no, "section": b.section, "department_code": b.department.code},
    }


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_statement(batch_id=None, semester_no=None, department_id=None, q=None):
    stmt = (
        db.select(Student).join(Batch, Student.batch_id == Batch.id)
        .options(joinedload(Student.batch).joinedload(Batch.department))
        .order_by(Student.enrollment_no)
    )
    if batch_id is not None:
        stmt = stmt.where(Student.batch_id == batch_id)
    if semester_no is not None:
        stmt = stmt.where(Batch.semester_no == semester_no)
    if department_id is not None:
        stmt = stmt.where(Batch.department_id == department_id)
    if q and q.strip():
        like = _like(q)
        stmt = stmt.where(or_(*(func.lower(col).like(like, escape="\\") for col in (Student.enrollment_no, Student.name, Student.email))))
    return stmt


def get_or_404(student_id: int) -> Student:
    student = db.session.get(Student, student_id)
    if student is None:
        raise AppError("not_found", "Student not found.", 404)
    return student


# ---------- validation ----------
def clean(data: dict, student: Student | None = None) -> dict:
    fields.reject_unknown(data, FIELDS, AppError)
    if student is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)
    current = {} if student is None else {"enrollment_no": student.enrollment_no, "name": student.name, "email": student.email, "batch_id": student.batch_id}
    merged = {**current, **data}
    errors: dict = {}
    out: dict = {}

    for f in ("enrollment_no", "name", "batch_id"):
        if merged.get(f) in (None, ""):
            errors[f] = "This field is required."

    if "enrollment_no" not in errors:
        number = merged["enrollment_no"].strip().upper() if isinstance(merged["enrollment_no"], str) else None
        if not number or len(number) > 30 or not _ENROLLMENT_RE.match(number):
            errors["enrollment_no"] = "Use up to 30 letters, digits or . _ / - (e.g. CSE23001)."
        out["enrollment_no"] = number
    if "name" not in errors:
        out["name"] = fields.text(merged["name"], "name", errors, 2, 120, "Name")
    out["email"] = fields.email(merged.get("email"), "email", errors)
    if "batch_id" not in errors:
        batch_id = fields.whole_number(merged["batch_id"], "batch_id", errors, 1, 2**31 - 1)
        if batch_id is not None and db.session.get(Batch, batch_id) is None:
            errors["batch_id"] = "Choose an existing batch."
        out["batch_id"] = batch_id

    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)
    return out


def _check_unique(values: dict, exclude_id: int | None) -> None:
    number = db.select(Student.id).where(func.upper(Student.enrollment_no) == values["enrollment_no"])
    if exclude_id is not None:
        number = number.where(Student.id != exclude_id)
    if db.session.scalar(number) is not None:
        raise AppError("duplicate_student", f"A student with enrollment number {values['enrollment_no']} already exists.", 409,
                       {"enrollment_no": "This enrollment number is already used."})
    if values["email"]:
        mail = db.select(Student.id).where(func.lower(Student.email) == values["email"])
        if exclude_id is not None:
            mail = mail.where(Student.id != exclude_id)
        if db.session.scalar(mail) is not None:
            raise AppError("duplicate_student", "Another student already uses this email address.", 409, {"email": "This email is already used by another student."})


def _check_capacity(batch_id: int, exclude_id: int | None) -> None:
    batch = db.session.get(Batch, batch_id)
    stmt = db.select(func.count()).select_from(Student).where(Student.batch_id == batch_id)
    if exclude_id is not None:
        stmt = stmt.where(Student.id != exclude_id)
    enrolled = db.session.scalar(stmt)
    if enrolled >= batch.strength:
        raise AppError(
            "batch_full",
            f"{batch.name} is full ({enrolled} of {batch.strength} places). Increase the batch strength first, or choose another batch.",
            409,
            {"batch_id": "This batch is full."},
        )


# ---------- commands ----------
def create_student(data: dict) -> Student:
    values = clean(data)
    _check_unique(values, None)
    _check_capacity(values["batch_id"], None)
    student = Student(**values)
    db.session.add(student)
    _commit()
    return student


def update_student(student: Student, data: dict) -> Student:
    values = clean(data, student)
    _check_unique(values, student.id)
    if values["batch_id"] != student.batch_id:  # an unchanged batch is never re-checked, so old data stays editable
        _check_capacity(values["batch_id"], student.id)
    for field, value in values.items():
        setattr(student, field, value)
    _commit()
    return student


def delete_student(student: Student) -> bool:
    """Delete the record; also disable the linked student login. Returns True if a login was disabled."""
    disabled = False
    if student.user is not None and student.user.role == Role.STUDENT and student.user.is_active:
        student.user.is_active = False
        disabled = True
    db.session.delete(student)
    _commit()
    return disabled


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AppError("duplicate_student", "A student with that enrollment number already exists.", 409, {"enrollment_no": "This enrollment number is already used."}) from None
