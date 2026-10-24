"""Diya - R4 Subject/Course Management: validation and business rules.

The database guarantees: unique code, credits >= 0, weekly_hours > 0, lab_block_periods >= 1,
and that the department exists. This service adds what it cannot express:
  * codes are normalised to UPPER CASE (MySQL compares codes case-insensitively, SQLite does not),
  * lab subjects need a laboratory and weekly hours that fit whole lab sessions,
  * a subject with teaching assignments cannot be deleted, and the fields that decide how many
    sessions it needs (department, semester, type, hours, lab length) are locked, because
    teaching_assignments.sessions_per_week was computed from them.
"""
import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common.errors import AppError
from app.extensions import db
from app.models import ClassType, Department, RoomType, Subject, TeachingAssignment, TimetableEntry

MAX_SEMESTER, MAX_CREDITS, MAX_WEEKLY_HOURS, MAX_LAB_BLOCK = 12, 20, 40, 6
FIELDS = {"code", "name", "department_id", "semester_no", "credits", "weekly_hours", "class_type", "lab_block_periods", "required_room_type"}
# Changing these on a subject that is already assigned would leave sessions_per_week out of date.
LOCKED_WHEN_IN_USE = ("department_id", "semester_no", "class_type", "weekly_hours", "lab_block_periods")
LABEL = {"department_id": "department", "semester_no": "semester", "class_type": "type", "weekly_hours": "weekly hours", "lab_block_periods": "lab session length"}
THEORY_ROOMS = (RoomType.CLASSROOM, RoomType.SEMINAR_HALL, RoomType.AUDITORIUM)
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")


# ---------- reading ----------
def sessions_per_week(subject: Subject) -> int:
    return subject.weekly_hours // subject.lab_block_periods if subject.class_type == ClassType.LAB else subject.weekly_hours


def usage_counts(subject_ids: list[int]) -> dict[int, dict]:
    usage = {sid: {"teaching_assignments": 0, "timetable_entries": 0} for sid in subject_ids}
    if not subject_ids:
        return usage
    rows = db.session.execute(
        db.select(TeachingAssignment.subject_id, func.count()).where(TeachingAssignment.subject_id.in_(subject_ids)).group_by(TeachingAssignment.subject_id)
    ).all()
    for sid, n in rows:
        usage[sid]["teaching_assignments"] = n
    rows = db.session.execute(
        db.select(TeachingAssignment.subject_id, func.count(TimetableEntry.id))
        .join(TimetableEntry, TimetableEntry.assignment_id == TeachingAssignment.id)
        .where(TeachingAssignment.subject_id.in_(subject_ids))
        .group_by(TeachingAssignment.subject_id)
    ).all()
    for sid, n in rows:
        usage[sid]["timetable_entries"] = n
    return usage


def serialize(subject: Subject, usage: dict) -> dict:
    return {
        "id": subject.id,
        "code": subject.code,
        "name": subject.name,
        "department": {"id": subject.department.id, "code": subject.department.code, "name": subject.department.name},
        "semester_no": subject.semester_no,
        "credits": subject.credits,
        "weekly_hours": subject.weekly_hours,
        "class_type": subject.class_type.value,
        "lab_block_periods": subject.lab_block_periods,
        "required_room_type": subject.required_room_type.value if subject.required_room_type else None,
        "sessions_per_week": sessions_per_week(subject),
        "usage": usage,
        "in_use": usage["teaching_assignments"] > 0,
    }


def serialize_many(subjects: list[Subject]) -> list[dict]:
    usage = usage_counts([s.id for s in subjects])
    return [serialize(s, usage[s.id]) for s in subjects]


def _like_term(term: str) -> str:
    escaped = term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_statement(department_id=None, semester_no=None, class_type=None, q=None):
    stmt = db.select(Subject).options(joinedload(Subject.department)).order_by(Subject.code)
    if department_id is not None:
        stmt = stmt.where(Subject.department_id == department_id)
    if semester_no is not None:
        stmt = stmt.where(Subject.semester_no == semester_no)
    if class_type is not None:
        stmt = stmt.where(Subject.class_type == class_type)
    if q and q.strip():
        like = _like_term(q)
        stmt = stmt.where(or_(func.lower(Subject.code).like(like, escape="\\"), func.lower(Subject.name).like(like, escape="\\")))
    return stmt


def get_or_404(subject_id: int) -> Subject:
    subject = db.session.get(Subject, subject_id)
    if subject is None:
        raise AppError("not_found", "Subject not found.", 404)
    return subject


def list_departments() -> list[dict]:
    rows = db.session.scalars(db.select(Department).order_by(Department.code)).all()
    return [{"id": d.id, "code": d.code, "name": d.name} for d in rows]


# ---------- validation ----------
def _int(value, field, errors, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = "Must be a whole number."
        return None
    if not lo <= value <= hi:
        errors[field] = f"Must be between {lo} and {hi}."
        return None
    return value


def _enum(enum_cls, value, field, errors, message):
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        errors[field] = message
        return None


def _current(subject: Subject | None) -> dict:
    if subject is None:
        return {}
    return {
        "code": subject.code, "name": subject.name, "department_id": subject.department_id, "semester_no": subject.semester_no,
        "credits": subject.credits, "weekly_hours": subject.weekly_hours, "class_type": subject.class_type.value,
        "lab_block_periods": subject.lab_block_periods,
        "required_room_type": subject.required_room_type.value if subject.required_room_type else None,
    }


def clean(data: dict, subject: Subject | None = None) -> dict:
    """Validate `data` merged over the existing subject (if any); return typed values or raise 400."""
    unknown = sorted(set(data) - FIELDS)
    if unknown:
        raise AppError("validation_error", f"Unknown field(s): {', '.join(unknown)}.", 400, {u: "Not allowed." for u in unknown})
    if subject is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)

    cur = _current(subject)
    merged = {**cur, **data}
    errors: dict = {}
    out: dict = {}

    required = ("code", "name", "department_id", "semester_no", "credits", "weekly_hours", "class_type")
    for f in required:
        if merged.get(f) in (None, ""):
            errors[f] = "This field is required."

    code = merged.get("code")
    if "code" not in errors:
        code = code.strip().upper() if isinstance(code, str) else None
        if not code or len(code) > 20 or not _CODE_RE.match(code):
            errors["code"] = "Use up to 20 letters, digits or . _ / - (e.g. CS301)."
        out["code"] = code

    name = merged.get("name")
    if "name" not in errors:
        name = " ".join(name.split()) if isinstance(name, str) else None
        if not name or not 2 <= len(name) <= 150:
            errors["name"] = "Enter a name of 2 to 150 characters."
        out["name"] = name

    if "department_id" not in errors:
        dep_id = _int(merged["department_id"], "department_id", errors, 1, 2**31 - 1)
        if dep_id is not None and db.session.get(Department, dep_id) is None:
            errors["department_id"] = "Choose an existing department."
        out["department_id"] = dep_id
    if "semester_no" not in errors:
        out["semester_no"] = _int(merged["semester_no"], "semester_no", errors, 1, MAX_SEMESTER)
    if "credits" not in errors:
        out["credits"] = _int(merged["credits"], "credits", errors, 0, MAX_CREDITS)
    if "weekly_hours" not in errors:
        out["weekly_hours"] = _int(merged["weekly_hours"], "weekly_hours", errors, 1, MAX_WEEKLY_HOURS)
    class_type = None
    if "class_type" not in errors:
        class_type = _enum(ClassType, merged["class_type"], "class_type", errors, "Choose theory or lab.")
        out["class_type"] = class_type

    # ---- type-dependent rules ----
    if class_type is not None:
        was_lab = cur.get("class_type") == "lab"
        if class_type == ClassType.LAB:
            block = data.get("lab_block_periods", cur.get("lab_block_periods") if was_lab else 2)
            out["lab_block_periods"] = _int(block, "lab_block_periods", errors, 1, MAX_LAB_BLOCK)
        else:
            if data.get("lab_block_periods") not in (None, 1) and "lab_block_periods" in data:
                errors["lab_block_periods"] = "Only lab subjects have a lab session length."
            # Not applicable to theory; keep whatever is stored (seed data uses 2) unless the type just changed.
            out["lab_block_periods"] = cur.get("lab_block_periods", 1) if cur and not was_lab else 1

        type_changed = bool(cur) and cur.get("class_type") != class_type.value
        if "required_room_type" in data and data["required_room_type"] not in (None, ""):
            room = _enum(RoomType, data["required_room_type"], "required_room_type", errors, "Choose a valid room type.")
        elif cur and not type_changed and cur.get("required_room_type"):
            room = RoomType(cur["required_room_type"])
        else:
            room = RoomType.LAB if class_type == ClassType.LAB else RoomType.CLASSROOM
        if room is not None:
            if class_type == ClassType.LAB and room != RoomType.LAB:
                errors["required_room_type"] = "A lab subject must use a laboratory."
            elif class_type == ClassType.THEORY and room not in THEORY_ROOMS:
                errors["required_room_type"] = "A theory subject cannot require a laboratory. Choose a classroom, seminar hall or auditorium."
        out["required_room_type"] = room

        hours, block = out.get("weekly_hours"), out.get("lab_block_periods")
        if class_type == ClassType.LAB and hours and block and "weekly_hours" not in errors and "lab_block_periods" not in errors and hours % block != 0:
            errors["weekly_hours"] = f"Lab hours must be a multiple of the session length ({block})."

    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)
    return out


def _check_code_free(code: str, exclude_id: int | None) -> None:
    stmt = db.select(Subject.id).where(func.upper(Subject.code) == code)
    if exclude_id is not None:
        stmt = stmt.where(Subject.id != exclude_id)
    if db.session.scalar(stmt) is not None:
        raise AppError("duplicate_subject", f"A subject with code {code} already exists.", 409, {"code": "This code is already used."})


# ---------- commands ----------
def create_subject(data: dict) -> Subject:
    values = clean(data)
    _check_code_free(values["code"], None)
    subject = Subject(**values)
    db.session.add(subject)
    _commit()
    return subject


def update_subject(subject: Subject, data: dict) -> Subject:
    values = clean(data, subject)
    _check_code_free(values["code"], subject.id)

    usage = usage_counts([subject.id])[subject.id]
    if usage["teaching_assignments"]:
        current = _current(subject)
        locked = [f for f in LOCKED_WHEN_IN_USE if values[f] != current[f] and not (hasattr(values[f], "value") and values[f].value == current[f])]
        if locked:
            names = ", ".join(LABEL[f] for f in locked)
            raise AppError(
                "subject_in_use",
                f"This subject is assigned to {usage['teaching_assignments']} batch(es), so its {names} cannot be changed. Remove those teaching assignments first. Name, code, credits and room type can still be edited.",
                409,
                {f: "Locked while the subject has teaching assignments." for f in locked},
            )
    for field, value in values.items():
        setattr(subject, field, value)
    _commit()
    return subject


def delete_subject(subject: Subject) -> None:
    usage = usage_counts([subject.id])[subject.id]
    if usage["teaching_assignments"]:
        n = usage["teaching_assignments"]
        extra = f" and {usage['timetable_entries']} timetable entr{'y' if usage['timetable_entries'] == 1 else 'ies'}" if usage["timetable_entries"] else ""
        raise AppError(
            "subject_in_use",
            f"This subject is used by {n} teaching assignment{'' if n == 1 else 's'}{extra} and cannot be deleted. Remove those assignments first.",
            409,
            usage,
        )
    db.session.delete(subject)
    _commit()


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # two admins saving the same code at once: the unique key is the last defence
        raise AppError("duplicate_subject", "A subject with that code already exists.", 409, {"code": "This code is already used."}) from None
