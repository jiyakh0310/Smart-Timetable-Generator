"""Teaching assignments: which faculty member teaches which subject to which batch in a term.

Weekly requirement rules (the server computes them; clients can never send a session count):
  * theory: `sessions_per_week` = weekly hours, each session is ONE period;
  * lab:    `sessions_per_week` = weekly hours / lab session length, each session needs that many
            CONSECUTIVE periods (same day, period numbers differing by 1, so a lab cannot straddle a break).

Safety rules:
  * the subject and the batch must be in the same semester (hard error);
  * a department mismatch is allowed but flagged as "cross_department" (shared subjects are legitimate);
  * the faculty member must be active and the term active when an assignment is created or those fields change;
  * an assignment that timetable entries or unscheduled items point at is frozen: nothing about it can change
    and it cannot be deleted, so generated records are never silently invalidated;
  * availability NEVER blocks an assignment. It only produces warnings: HARD unavailability reduces the usable
    slots, a soft "preferred" never does.
"""
from collections import defaultdict

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common import fields
from app.common.errors import AppError
from app.extensions import db
from app.models import (
    AcademicTerm,
    AvailabilityStatus,
    Batch,
    ClassType,
    Faculty,
    FacultyAvailability,
    SlotType,
    Subject,
    TeachingAssignment,
    TimeSlot,
    TimetableEntry,
    UnscheduledItem,
    User,
)

FIELDS = {"term_id", "batch_id", "subject_id", "faculty_id"}


# ---------- weekly requirement ----------
def session_length(subject: Subject) -> int:
    return subject.lab_block_periods if subject.class_type == ClassType.LAB else 1


def expected_sessions(subject: Subject) -> int:
    return subject.weekly_hours // session_length(subject)


# ---------- reading ----------
def usage_counts(ids: list[int]) -> dict[int, dict]:
    usage = {i: {"timetable_entries": 0, "unscheduled_items": 0} for i in ids}
    if not ids:
        return usage
    for model, key in ((TimetableEntry, "timetable_entries"), (UnscheduledItem, "unscheduled_items")):
        for aid, n in db.session.execute(db.select(model.assignment_id, func.count()).where(model.assignment_id.in_(ids)).group_by(model.assignment_id)).all():
            usage[aid][key] = n
    return usage


def _warnings(rows: list[TeachingAssignment]) -> dict[int, list[dict]]:
    """Availability feasibility notes. Informational only - they never block an assignment."""
    result = {a.id: [] for a in rows}
    if not rows:
        return result
    faculty_ids = {a.faculty_id for a in rows}
    slots = db.session.scalars(db.select(TimeSlot).where(TimeSlot.is_active.is_(True), TimeSlot.slot_type == SlotType.CLASS)).all()
    hard = defaultdict(set)  # faculty_id -> slot ids marked UNAVAILABLE (hard). "preferred" is deliberately ignored here.
    for r in db.session.scalars(db.select(FacultyAvailability).where(FacultyAvailability.faculty_id.in_(faculty_ids), FacultyAvailability.status == AvailabilityStatus.UNAVAILABLE)):
        hard[r.faculty_id].add(r.time_slot_id)

    # total periods per week each faculty member needs in each term (from ALL their assignments, not just this page)
    needed = defaultdict(int)
    for fid, term_id, class_type, block, sessions in db.session.execute(
        db.select(TeachingAssignment.faculty_id, TeachingAssignment.term_id, Subject.class_type, Subject.lab_block_periods, TeachingAssignment.sessions_per_week)
        .join(Subject, Subject.id == TeachingAssignment.subject_id)
        .where(TeachingAssignment.faculty_id.in_(faculty_ids))
    ).all():
        needed[(fid, term_id)] += sessions * (block if class_type == ClassType.LAB else 1)

    for a in rows:
        usable = [s for s in slots if s.id not in hard[a.faculty_id]]
        name = a.faculty.user.full_name
        total = needed[(a.faculty_id, a.term_id)]
        if total > len(usable):
            result[a.id].append({
                "code": "availability_shortfall",
                "message": f"{name} is assigned {total} periods per week in this term but only {len(usable)} time slots are not marked unavailable.",
            })
        block = session_length(a.subject)
        if a.subject.class_type == ClassType.LAB:
            by_day = defaultdict(set)
            for s in usable:
                by_day[s.day_of_week].add(s.period_no)
            if not any(all(p + i in periods for i in range(block)) for periods in by_day.values() for p in periods):
                result[a.id].append({
                    "code": "no_lab_window",
                    "message": f"{name} has no day with {block} consecutive periods that are not marked unavailable, so this {block}-period lab session cannot be placed.",
                })
    return result


def serialize_many(rows: list[TeachingAssignment]) -> list[dict]:
    usage = usage_counts([a.id for a in rows])
    warnings = _warnings(rows)
    out = []
    for a in rows:
        length = session_length(a.subject)
        in_use = usage[a.id]["timetable_entries"] > 0 or usage[a.id]["unscheduled_items"] > 0
        out.append({
            "id": a.id,
            "term": {"id": a.term.id, "name": a.term.name, "is_active": bool(a.term.is_active)},
            "batch": {"id": a.batch.id, "name": a.batch.name, "semester_no": a.batch.semester_no, "strength": a.batch.strength, "department_code": a.batch.department.code},
            "subject": {
                "id": a.subject.id, "code": a.subject.code, "name": a.subject.name, "class_type": a.subject.class_type.value, "semester_no": a.subject.semester_no,
                "weekly_hours": a.subject.weekly_hours, "lab_block_periods": a.subject.lab_block_periods, "department_code": a.subject.department.code,
            },
            "faculty": {"id": a.faculty.id, "employee_code": a.faculty.employee_code, "name": a.faculty.user.full_name, "is_active": bool(a.faculty.user.is_active)},
            "sessions_per_week": a.sessions_per_week,
            "session_length": length,
            "periods_per_week": a.sessions_per_week * length,
            "cross_department": a.subject.department_id != a.batch.department_id,
            "session_mismatch": a.sessions_per_week != expected_sessions(a.subject),
            "warnings": warnings[a.id],
            "usage": usage[a.id],
            "in_use": in_use,
        })
    return out


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_statement(term_id=None, batch_id=None, subject_id=None, faculty_id=None, semester_no=None, class_type=None, q=None):
    stmt = (
        db.select(TeachingAssignment)
        .join(Subject, Subject.id == TeachingAssignment.subject_id)
        .join(Batch, Batch.id == TeachingAssignment.batch_id)
        .join(Faculty, Faculty.id == TeachingAssignment.faculty_id)
        .join(User, User.id == Faculty.user_id)
        .options(
            joinedload(TeachingAssignment.term),
            joinedload(TeachingAssignment.batch).joinedload(Batch.department),
            joinedload(TeachingAssignment.subject).joinedload(Subject.department),
            joinedload(TeachingAssignment.faculty).joinedload(Faculty.user),
        )
        .order_by(TeachingAssignment.term_id.desc(), Batch.department_id, Batch.semester_no, Batch.section, Subject.code)
    )
    if term_id is not None:
        stmt = stmt.where(TeachingAssignment.term_id == term_id)
    if batch_id is not None:
        stmt = stmt.where(TeachingAssignment.batch_id == batch_id)
    if subject_id is not None:
        stmt = stmt.where(TeachingAssignment.subject_id == subject_id)
    if faculty_id is not None:
        stmt = stmt.where(TeachingAssignment.faculty_id == faculty_id)
    if semester_no is not None:
        stmt = stmt.where(Batch.semester_no == semester_no)
    if class_type is not None:
        stmt = stmt.where(Subject.class_type == class_type)
    if q and q.strip():
        like = _like(q)
        stmt = stmt.where(or_(*(func.lower(col).like(like, escape="\\") for col in (Subject.code, Subject.name, Batch.name, Faculty.employee_code, User.full_name))))
    return stmt


def get_or_404(assignment_id: int) -> TeachingAssignment:
    assignment = db.session.get(TeachingAssignment, assignment_id)
    if assignment is None:
        raise AppError("not_found", "Teaching assignment not found.", 404)
    return assignment


def list_terms() -> list[dict]:
    rows = db.session.scalars(db.select(AcademicTerm).order_by(AcademicTerm.id.desc())).all()
    return [{"id": t.id, "name": t.name, "academic_year": t.academic_year, "is_active": bool(t.is_active)} for t in rows]


# ---------- validation ----------
def clean(data: dict, assignment: TeachingAssignment | None = None) -> dict:
    if "sessions_per_week" in data:
        raise AppError("validation_error", "The number of sessions is calculated from the subject's weekly hours and lab session length; it cannot be set.", 400,
                       {"sessions_per_week": "Calculated automatically."})
    fields.reject_unknown(data, FIELDS, AppError)
    if assignment is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)

    current = {} if assignment is None else {"term_id": assignment.term_id, "batch_id": assignment.batch_id, "subject_id": assignment.subject_id, "faculty_id": assignment.faculty_id}
    merged = {**current, **data}
    errors: dict = {}
    refs: dict = {}

    for field, model, label in (("term_id", AcademicTerm, "term"), ("batch_id", Batch, "batch"), ("subject_id", Subject, "subject"), ("faculty_id", Faculty, "faculty member")):
        if merged.get(field) in (None, ""):
            errors[field] = "This field is required."
            continue
        value = fields.whole_number(merged[field], field, errors, 1, 2**31 - 1)
        if value is None:
            continue
        obj = db.session.get(model, value)
        if obj is None:
            errors[field] = f"Choose an existing {label}."
        else:
            refs[field] = obj
    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)

    term, batch, subject, faculty = refs["term_id"], refs["batch_id"], refs["subject_id"], refs["faculty_id"]
    changed = lambda f: assignment is None or f in data and data[f] != current[f]
    if changed("term_id") and not term.is_active:
        errors["term_id"] = "This term is not active."
    if changed("faculty_id") and not faculty.user.is_active:
        errors["faculty_id"] = "This faculty member is inactive. Reactivate them first or choose someone else."
    if subject.semester_no != batch.semester_no:
        errors["subject_id"] = f"{subject.code} is a semester {subject.semester_no} subject but {batch.name} is in semester {batch.semester_no}."
    elif subject.class_type == ClassType.LAB and subject.weekly_hours % subject.lab_block_periods != 0:
        errors["subject_id"] = f"{subject.code} has {subject.weekly_hours} lab hours, which is not a whole number of {subject.lab_block_periods}-period sessions. Fix the subject first."
    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)

    return {"term_id": term.id, "batch_id": batch.id, "subject_id": subject.id, "faculty_id": faculty.id, "sessions_per_week": expected_sessions(subject)}


def _check_unique(values: dict, exclude_id: int | None) -> None:
    stmt = db.select(TeachingAssignment).where(
        TeachingAssignment.term_id == values["term_id"], TeachingAssignment.batch_id == values["batch_id"], TeachingAssignment.subject_id == values["subject_id"]
    )
    if exclude_id is not None:
        stmt = stmt.where(TeachingAssignment.id != exclude_id)
    existing = db.session.scalar(stmt)
    if existing is not None:
        raise AppError(
            "duplicate_assignment",
            f"{existing.batch.name} already has {existing.subject.code} assigned to {existing.faculty.user.full_name} in this term. A batch has one teacher per subject.",
            409,
            {"subject_id": "This subject is already assigned to that batch in this term."},
        )


# ---------- commands ----------
def create_assignment(data: dict) -> TeachingAssignment:
    values = clean(data)
    _check_unique(values, None)
    assignment = TeachingAssignment(**values)
    db.session.add(assignment)
    _commit()
    return assignment


def update_assignment(assignment: TeachingAssignment, data: dict) -> TeachingAssignment:
    values = clean(data, assignment)
    usage = usage_counts([assignment.id])[assignment.id]
    if usage["timetable_entries"] or usage["unscheduled_items"]:  # the lock is reported before any other conflict
        changed = [f for f in ("term_id", "batch_id", "subject_id", "faculty_id") if values[f] != getattr(assignment, f)]
        if changed:
            raise AppError(
                "assignment_in_use",
                "This assignment is part of a generated timetable, so it cannot be changed without invalidating that timetable. Remove or regenerate the timetable first.",
                409,
                {f: "Locked while a timetable uses this assignment." for f in changed},
            )
    _check_unique(values, assignment.id)
    for field, value in values.items():
        setattr(assignment, field, value)
    _commit()
    return assignment


def delete_assignment(assignment: TeachingAssignment) -> None:
    usage = usage_counts([assignment.id])[assignment.id]
    if usage["timetable_entries"] or usage["unscheduled_items"]:
        parts = []
        if usage["timetable_entries"]:
            n = usage["timetable_entries"]
            parts.append(f"{n} timetable entr{'y' if n == 1 else 'ies'}")
        if usage["unscheduled_items"]:
            n = usage["unscheduled_items"]
            parts.append(f"{n} unscheduled session{'' if n == 1 else 's'}")
        raise AppError("assignment_in_use", f"This assignment is used by {' and '.join(parts)} in a generated timetable and cannot be deleted. Remove or regenerate the timetable first.", 409, usage)
    db.session.delete(assignment)
    _commit()


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # two admins saving the same batch + subject at once: the unique key is the last defence
        raise AppError("duplicate_assignment", "That subject is already assigned to that batch in this term.", 409, {"subject_id": "Already assigned."}) from None
