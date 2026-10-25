"""Jiya - R7 timetable generation: persists a generator plan as a DRAFT timetable (admin only).

RULES
  * Scope is the whole term: a timetable has no batch column and faculty / rooms are shared by every batch, so clashes can
    only be prevented by planning all of a term's active teaching assignments together.
  * R17: every generation creates a NEW version number (max + 1 for the term) saved as `draft`. Older versions are left
    untouched. Nothing here approves, publishes, restores or compares.
  * All-or-nothing: one transaction. The saved entries are re-checked with `validate_timetable`; any hard conflict aborts
    and rolls everything back.
  * The term row is locked while a version is allocated, and the (term, version) unique key is the safety net: concurrent
    requests queue up and each gets its own version; a lost race is retried.
  * Only a draft (or validated, i.e. a draft that passed R10) can be discarded. Assignments, rooms, subjects, etc. are frozen while any timetable uses them, so a
    discard is the only way to free them again; approved / published timetables are never deletable here.
"""
from collections import Counter

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common.errors import AppError
from app.extensions import db
from app.models import AcademicTerm, Batch, Subject, TeachingAssignment, Timetable, TimetableEntry, TimetableStatus, UnscheduledItem
from app.modules.isha import workload_service
from app.modules.jiya import generator
from app.modules.pragya import clash_service

MAX_ATTEMPTS = 3
_S = TimetableStatus
EDITABLE = (_S.DRAFT, _S.VALIDATED, _S.REJECTED)  # R15 / R16: pending approval, approved, published and archived are immutable
DISCARDABLE = (_S.DRAFT, _S.VALIDATED, _S.REJECTED)  # nothing that is pending, approved, published or archived can be removed here
# R16: action -> (statuses it may start from, status it leads to). The single source of truth for the workflow.
TRANSITIONS = {
    "submit": ((_S.DRAFT, _S.VALIDATED, _S.REJECTED), _S.PENDING_APPROVAL),
    "approve": ((_S.PENDING_APPROVAL,), _S.APPROVED),
    "reject": ((_S.PENDING_APPROVAL, _S.APPROVED), _S.REJECTED),
    "publish": ((_S.APPROVED,), _S.PUBLISHED),
}


def get_or_404(timetable_id: int) -> Timetable:
    timetable = db.session.get(Timetable, timetable_id)
    if timetable is None:
        raise AppError("not_found", "Timetable not found.", 404)
    return timetable


def list_statement(term_id=None, status=None):
    stmt = db.select(Timetable).options(joinedload(Timetable.term)).order_by(Timetable.term_id.desc(), Timetable.version.desc())
    if term_id is not None:
        stmt = stmt.where(Timetable.term_id == term_id)
    if status is not None:
        stmt = stmt.where(Timetable.status == status)
    return stmt


def _counts(timetable_ids) -> dict[int, dict]:
    ids = list(timetable_ids)
    out = {i: {"periods": 0, "unscheduled_sessions": 0} for i in ids}
    if not ids:
        return out
    for tid, n in db.session.execute(db.select(TimetableEntry.timetable_id, db.func.count()).where(TimetableEntry.timetable_id.in_(ids)).group_by(TimetableEntry.timetable_id)):
        out[tid]["periods"] = n
    for tid, n in db.session.execute(db.select(UnscheduledItem.timetable_id, db.func.count()).where(UnscheduledItem.timetable_id.in_(ids)).group_by(UnscheduledItem.timetable_id)):
        out[tid]["unscheduled_sessions"] = n
    return out


def serialize_many(timetables) -> list[dict]:
    counts = _counts(t.id for t in timetables)
    return [serialize(t, counts[t.id]) for t in timetables]


def serialize(t: Timetable, counts: dict | None = None) -> dict:
    counts = counts or _counts([t.id])[t.id]
    return {
        "id": t.id,
        "term": {"id": t.term.id, "name": t.term.name, "academic_year": t.term.academic_year},
        "name": t.name,
        "version": t.version,
        "status": t.status.value,
        "validation_passed": bool(t.validation_passed),
        "generated_by": t.generated_by,
        "generated_at": t.generated_at.isoformat() if t.generated_at else None,
        "validated_at": t.validated_at.isoformat() if t.validated_at else None,
        "periods": counts["periods"],
        "unscheduled_sessions": counts["unscheduled_sessions"],
        "can_discard": t.status in DISCARDABLE,
        "can_edit": t.status in EDITABLE,
        "allowed_actions": [a for a, (start, _) in TRANSITIONS.items() if t.status in start],
        "is_current_published": t.status == TimetableStatus.PUBLISHED,
        "approved_by": t.approved_by,
        "approved_at": t.approved_at.isoformat() if t.approved_at else None,
        "published_at": t.published_at.isoformat() if t.published_at else None,
        "rejection_reason": t.rejection_reason,
    }


def detail(t: Timetable) -> dict:
    entries = db.session.scalars(
        db.select(TimetableEntry).where(TimetableEntry.timetable_id == t.id).options(
            joinedload(TimetableEntry.assignment).joinedload(TeachingAssignment.subject),
            joinedload(TimetableEntry.faculty),
            joinedload(TimetableEntry.batch),
            joinedload(TimetableEntry.room),
            joinedload(TimetableEntry.time_slot),
        ).order_by(TimetableEntry.batch_id, TimetableEntry.time_slot_id)
    ).unique().all()
    items = db.session.scalars(
        db.select(UnscheduledItem).where(UnscheduledItem.timetable_id == t.id).options(
            joinedload(UnscheduledItem.assignment).joinedload(TeachingAssignment.subject),
            joinedload(UnscheduledItem.assignment).joinedload(TeachingAssignment.batch),
            joinedload(UnscheduledItem.assignment).joinedload(TeachingAssignment.faculty),
        ).order_by(UnscheduledItem.assignment_id, UnscheduledItem.session_no)
    ).unique().all()
    data = serialize(t, {"periods": len(entries), "unscheduled_sessions": len(items)})
    data["workload"] = workload_service.timetable_rows(t)
    data["entries"] = [{
        "id": e.id,
        "assignment_id": e.assignment_id,
        "batch": {"id": e.batch.id, "name": e.batch.name},
        "subject": {"id": e.assignment.subject.id, "code": e.assignment.subject.code, "name": e.assignment.subject.name, "class_type": e.assignment.subject.class_type.value},
        "faculty": {"id": e.faculty.id, "name": e.faculty.user.full_name},
        "room": {"id": e.room.id, "code": e.room.code},
        "time_slot": {"id": e.time_slot.id, "day_of_week": e.time_slot.day_of_week, "period_no": e.time_slot.period_no,
                      "start_time": e.time_slot.start_time.strftime("%H:%M"), "end_time": e.time_slot.end_time.strftime("%H:%M")},
    } for e in entries]
    data["unscheduled"] = [{
        "id": i.id,
        "assignment_id": i.assignment_id,
        "session_no": i.session_no,
        "batch": {"id": i.assignment.batch.id, "name": i.assignment.batch.name},
        "subject": {"id": i.assignment.subject.id, "code": i.assignment.subject.code, "name": i.assignment.subject.name},
        "faculty": {"id": i.assignment.faculty.id, "name": i.assignment.faculty.user.full_name},
        "reason_code": i.reason_code,
        "reason_text": i.reason_text,
    } for i in items]
    return data


def _active_assignments(term_id: int) -> list[TeachingAssignment]:
    return db.session.scalars(
        db.select(TeachingAssignment).where(TeachingAssignment.term_id == term_id).options(
            joinedload(TeachingAssignment.batch), joinedload(TeachingAssignment.subject), joinedload(TeachingAssignment.faculty)
        ).order_by(TeachingAssignment.id)
    ).unique().all()


def _save(term: AcademicTerm, user_id: int, assignments, plan: generator.Plan) -> Timetable:
    last = db.session.scalar(db.select(db.func.max(Timetable.version)).where(Timetable.term_id == term.id)) or 0
    version = last + 1
    timetable = Timetable(term_id=term.id, name=f"{term.name} timetable v{version}", version=version, status=TimetableStatus.DRAFT, validation_passed=False, generated_by=user_id)
    db.session.add(timetable)
    db.session.flush()
    for s in plan.placed:
        for slot_id in s.time_slot_ids:
            db.session.add(TimetableEntry(timetable_id=timetable.id, assignment_id=s.assignment_id, faculty_id=s.faculty_id, batch_id=s.batch_id, room_id=s.room_id, time_slot_id=slot_id))
    for u in plan.unplaced:
        db.session.add(UnscheduledItem(timetable_id=timetable.id, assignment_id=u.assignment_id, session_no=u.session_no, reason_code=u.reason_code, reason_text=u.reason_text))
    db.session.flush()
    # Safety net: the saved timetable must satisfy every hard rule, checked by the same service everything else uses.
    report = clash_service.validate_timetable(timetable.id)
    if not report.is_valid:
        raise AppError("generation_invalid", "The generated timetable broke a hard rule, so nothing was saved.", 500, {"conflicts": [c.to_dict() for c in report.hard[:10]]})
    return timetable


def generate(term_id: int, user_id: int) -> dict:
    """Generate a new DRAFT version for the term. Raises AppError (and saves nothing) when it cannot."""
    term = db.session.get(AcademicTerm, term_id)
    if term is None:
        raise AppError("validation_error", "Unknown term.", 400, {"term_id": "Choose an existing term."})
    if not term.is_active:
        raise AppError("term_inactive", "Timetables can only be generated for an active term.", 409, {"term_id": "This term is not active."})

    for attempt in range(MAX_ATTEMPTS):
        try:
            db.session.commit()  # end any read snapshot so what is read after the lock is current (MySQL repeatable read)
            db.session.execute(db.select(AcademicTerm.id).where(AcademicTerm.id == term_id).with_for_update())  # serialise generations of one term
            assignments = _active_assignments(term_id)
            if not assignments:
                raise AppError("no_assignments", "This term has no teaching assignments, so there is nothing to schedule.", 409, {"term_id": "Add teaching assignments first."})
            plan = generator.plan_term(assignments)
            timetable = _save(term, user_id, assignments, plan)
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()  # lost a version race; try again with a fresh version number
            if attempt == MAX_ATTEMPTS - 1:
                raise AppError("generation_conflict", "Another generation was running at the same time. Please try again.", 409) from None
        except Exception:
            db.session.rollback()
            raise
    term = db.session.get(AcademicTerm, term_id)
    return summary(db.session.get(Timetable, timetable.id), plan)


def summary(timetable: Timetable, plan: generator.Plan) -> dict:
    placed, unplaced = len(plan.placed), len(plan.unplaced)
    status = "complete" if unplaced == 0 else ("none_scheduled" if placed == 0 else "partial")
    reasons = Counter(u.reason_code for u in plan.unplaced)
    data = serialize(timetable)
    data["generation"] = {
        "status": status,
        "required_sessions": plan.required_sessions,
        "scheduled_sessions": placed,
        "unscheduled_sessions": unplaced,
        "scheduled_periods": len(plan.periods),
        "unscheduled_reasons": dict(sorted(reasons.items())),
        "warnings": plan.warnings,
        "workload": plan.workload,
    }
    return data


def discard(timetable: Timetable) -> None:
    if timetable.status not in DISCARDABLE:
        raise AppError("timetable_not_draft", f"Only a draft, validated or rejected timetable can be discarded; this timetable is {timetable.status.value}.", 409)
    db.session.delete(timetable)  # entries and unscheduled items cascade
    db.session.commit()
