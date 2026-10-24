"""Diya - R3 Batch management: validation and business rules.

A batch is a group of students scheduled together. `strength` is an admin-entered, STORED number
(student records are a partial list, so it cannot be derived) and it drives room allocation. To keep it honest:
  * strength can never be set below the number of student records already in the batch,
  * the department is taken from the program (the table has both columns, so they could disagree),
  * the semester must fit the program's duration,
  * a batch referenced by students, teaching assignments, timetable entries or announcements cannot be deleted,
  * program and semester are locked once teaching assignments / timetable entries exist.
"""
import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common import fields
from app.common.errors import AppError
from app.extensions import db
from app.models import Announcement, Batch, Program, Student, TeachingAssignment, TimetableEntry

MAX_STRENGTH = 500
FIELDS = {"program_id", "semester_no", "section", "strength", "name"}
LOCKED_WHEN_SCHEDULED = ("program_id", "semester_no")
_SECTION_RE = re.compile(r"^[A-Z0-9]{1,10}$")


# ---------- reading ----------
def usage_counts(batch_ids: list[int]) -> dict[int, dict]:
    usage = {b: {"students": 0, "teaching_assignments": 0, "timetable_entries": 0, "announcements": 0} for b in batch_ids}
    if not batch_ids:
        return usage
    for model, column, key in (
        (Student, Student.batch_id, "students"),
        (TeachingAssignment, TeachingAssignment.batch_id, "teaching_assignments"),
        (TimetableEntry, TimetableEntry.batch_id, "timetable_entries"),
        (Announcement, Announcement.batch_id, "announcements"),
    ):
        for batch_id, n in db.session.execute(db.select(column, func.count()).where(column.in_(batch_ids)).group_by(column)).all():
            usage[batch_id][key] = n
    return usage


def serialize(batch: Batch, usage: dict) -> dict:
    return {
        "id": batch.id,
        "name": batch.name,
        "section": batch.section,
        "semester_no": batch.semester_no,
        "strength": batch.strength,
        "student_count": usage["students"],
        "seats_left": max(batch.strength - usage["students"], 0),
        "program": {"id": batch.program.id, "name": batch.program.name, "duration_semesters": batch.program.duration_semesters},
        "department": {"id": batch.department.id, "code": batch.department.code, "name": batch.department.name},
        "usage": usage,
        "in_use": any(usage.values()),
        "scheduled": usage["teaching_assignments"] > 0 or usage["timetable_entries"] > 0,
    }


def serialize_many(batches: list[Batch]) -> list[dict]:
    usage = usage_counts([b.id for b in batches])
    return [serialize(b, usage[b.id]) for b in batches]


def student_count(batch_id: int) -> int:
    return db.session.scalar(db.select(func.count()).select_from(Student).where(Student.batch_id == batch_id))


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_statement(department_id=None, program_id=None, semester_no=None, q=None):
    stmt = db.select(Batch).options(joinedload(Batch.program), joinedload(Batch.department)).order_by(Batch.department_id, Batch.semester_no, Batch.section)
    if department_id is not None:
        stmt = stmt.where(Batch.department_id == department_id)
    if program_id is not None:
        stmt = stmt.where(Batch.program_id == program_id)
    if semester_no is not None:
        stmt = stmt.where(Batch.semester_no == semester_no)
    if q and q.strip():
        like = _like(q)
        stmt = stmt.where(or_(func.lower(Batch.name).like(like, escape="\\"), func.lower(Batch.section).like(like, escape="\\")))
    return stmt


def get_or_404(batch_id: int) -> Batch:
    batch = db.session.get(Batch, batch_id)
    if batch is None:
        raise AppError("not_found", "Batch not found.", 404)
    return batch


def list_programs() -> list[dict]:
    rows = db.session.scalars(db.select(Program).options(joinedload(Program.department)).order_by(Program.department_id, Program.name)).all()
    return [
        {"id": p.id, "name": p.name, "duration_semesters": p.duration_semesters, "department": {"id": p.department.id, "code": p.department.code, "name": p.department.name}}
        for p in rows
    ]


# ---------- validation ----------
def clean(data: dict, batch: Batch | None = None) -> dict:
    fields.reject_unknown(data, FIELDS, AppError)
    if batch is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)
    current = {} if batch is None else {"program_id": batch.program_id, "semester_no": batch.semester_no, "section": batch.section, "strength": batch.strength}
    merged = {**current, **data}
    errors: dict = {}
    out: dict = {}

    for f in ("program_id", "semester_no", "section", "strength"):
        if merged.get(f) in (None, ""):
            errors[f] = "This field is required."

    program = None
    if "program_id" not in errors:
        pid = fields.whole_number(merged["program_id"], "program_id", errors, 1, 2**31 - 1)
        if pid is not None:
            program = db.session.get(Program, pid)
            if program is None:
                errors["program_id"] = "Choose an existing program."
        out["program_id"] = pid
    if "semester_no" not in errors:
        hi = program.duration_semesters if program else 12
        out["semester_no"] = fields.whole_number(merged["semester_no"], "semester_no", errors, 1, hi)
        if "semester_no" in errors and program:
            errors["semester_no"] = f"{program.name} has {hi} semesters. Enter a number from 1 to {hi}."
    if "section" not in errors:
        section = merged["section"].strip().upper() if isinstance(merged["section"], str) else None
        if not section or not _SECTION_RE.match(section):
            errors["section"] = "Use 1 to 10 letters or digits, e.g. A."
        out["section"] = section
    if "strength" not in errors:
        out["strength"] = fields.whole_number(merged["strength"], "strength", errors, 1, MAX_STRENGTH)

    name = data.get("name") if "name" in data else (batch.name if batch else None)
    if name not in (None, ""):
        out["name"] = fields.text(name, "name", errors, 2, 80, "Name")
    else:
        out["name"] = None  # generated below once the department is known

    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)

    out["department_id"] = program.department_id
    if out["name"] is None:
        out["name"] = f"{program.department.code} Sem {out['semester_no']} - {out['section']}"[:80]
    return out


def _check_unique(values: dict, exclude_id: int | None) -> None:
    same_key = db.select(Batch.id).where(Batch.program_id == values["program_id"], Batch.semester_no == values["semester_no"], func.upper(Batch.section) == values["section"])
    same_name = db.select(Batch.id).where(func.lower(Batch.name) == values["name"].lower())
    if exclude_id is not None:
        same_key, same_name = same_key.where(Batch.id != exclude_id), same_name.where(Batch.id != exclude_id)
    if db.session.scalar(same_key) is not None:
        raise AppError("duplicate_batch", f"Section {values['section']} of semester {values['semester_no']} already exists for this program.", 409,
                       {"section": "This section already exists for that program and semester."})
    if db.session.scalar(same_name) is not None:
        raise AppError("duplicate_batch", f"A batch named \"{values['name']}\" already exists.", 409, {"name": "This name is already used."})


# ---------- commands ----------
def create_batch(data: dict) -> Batch:
    values = clean(data)
    _check_unique(values, None)
    batch = Batch(**values)
    db.session.add(batch)
    _commit()
    return batch


def update_batch(batch: Batch, data: dict) -> Batch:
    values = clean(data, batch)
    _check_unique(values, batch.id)

    enrolled = student_count(batch.id)
    if values["strength"] < enrolled:
        raise AppError(
            "strength_too_low",
            f"This batch already has {enrolled} student record{'' if enrolled == 1 else 's'}, so its strength cannot be less than {enrolled}.",
            409,
            {"strength": f"Cannot be less than the {enrolled} students already in this batch."},
        )

    usage = usage_counts([batch.id])[batch.id]
    if usage["teaching_assignments"] or usage["timetable_entries"]:
        locked = [f for f in LOCKED_WHEN_SCHEDULED if values[f] != getattr(batch, f)]
        if locked:
            names = " and ".join("program" if f == "program_id" else "semester" for f in locked)
            raise AppError(
                "batch_in_use",
                f"This batch has teaching assignments or timetable entries, so its {names} cannot be changed. Its name, section and strength can still be edited.",
                409,
                {f: "Locked while the batch is scheduled." for f in locked},
            )
    for field, value in values.items():
        setattr(batch, field, value)
    _commit()
    return batch


def delete_batch(batch: Batch) -> None:
    usage = usage_counts([batch.id])[batch.id]
    labels = {"students": "student", "teaching_assignments": "teaching assignment", "timetable_entries": "timetable entry", "announcements": "announcement"}
    parts = []
    for key, label in labels.items():
        n = usage[key]
        if n:
            plural = label if n == 1 else ("timetable entries" if key == "timetable_entries" else label + "s")
            parts.append(f"{n} {plural}")
    if parts:
        raise AppError("batch_in_use", f"This batch is used by {', '.join(parts)} and cannot be deleted. Move or remove those first.", 409, usage)
    db.session.delete(batch)
    _commit()


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # concurrent save of the same section: the unique key is the last defence
        raise AppError("duplicate_batch", "That batch already exists.", 409) from None
