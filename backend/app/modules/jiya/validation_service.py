"""Jiya - R10 timetable validation: re-checks the SAVED database state and records the outcome (admin only).

TWO SEPARATE QUESTIONS
  * workload    - `workload_service.overload_conflicts` (R14): a faculty member scheduled for more hours than their weekly maximum
  * hard rules  - `clash_service.validate_timetable` (faculty / batch / room overlap, capacity, room suitability and
                  service, invalid / break / disabled slots, lab runs, hard faculty unavailability). Not re-implemented here.
  * completeness - every session the term's teaching assignments require must be scheduled. Computed here from the
                  saved entries and the stored unscheduled items. A partial timetable is never reported as complete.
Faculty preferences are advisory: they appear under `warnings` and can never fail validation.

OUTCOME
  `validation_passed` is true only when there is no hard error AND the timetable is complete; otherwise false.
  Status moves draft -> validated on a pass and validated -> draft when a later validation fails. Any other status
  (approved, published, ...) is never changed by validation: it neither approves nor publishes anything.
  Validation changes no entries and no unscheduled items.
"""
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.common.errors import AppError
from app.extensions import db
from app.models import ClassType, TeachingAssignment, Timetable, TimetableEntry, TimetableStatus, UnscheduledItem
from app.modules.isha import workload_service
from app.modules.jiya.timetable_service import get_or_404
from app.modules.pragya import clash_service as clash


def _length(assignment: TeachingAssignment) -> int:
    return assignment.subject.lab_block_periods if assignment.subject.class_type == ClassType.LAB else 1


def _completeness(timetable: Timetable) -> dict:
    assignments = db.session.scalars(
        db.select(TeachingAssignment).where(TeachingAssignment.term_id == timetable.term_id).options(
            joinedload(TeachingAssignment.batch), joinedload(TeachingAssignment.subject), joinedload(TeachingAssignment.faculty)
        ).order_by(TeachingAssignment.id)
    ).unique().all()
    by_id = {a.id: a for a in assignments}
    periods = defaultdict(int)
    foreign = set()
    for (assignment_id,) in db.session.execute(db.select(TimetableEntry.assignment_id).where(TimetableEntry.timetable_id == timetable.id)):
        if assignment_id in by_id:
            periods[assignment_id] += 1
        else:
            foreign.add(assignment_id)
    stored = defaultdict(list)
    for item in db.session.scalars(db.select(UnscheduledItem).where(UnscheduledItem.timetable_id == timetable.id).order_by(UnscheduledItem.assignment_id, UnscheduledItem.session_no)):
        stored[item.assignment_id].append(item)

    unscheduled, problems, warnings = [], [], []
    required = scheduled = 0
    for a in assignments:
        length = _length(a)
        done = periods[a.id] // length          # whole sessions only; a partial lab run is a hard error from the clash rules
        required += a.sessions_per_week
        scheduled += min(done, a.sessions_per_week)
        missing = max(a.sessions_per_week - done, 0)
        who = {"assignment_id": a.id, "batch": {"id": a.batch.id, "name": a.batch.name}, "subject": {"id": a.subject.id, "code": a.subject.code, "name": a.subject.name},
               "faculty": {"id": a.faculty.id, "name": a.faculty.user.full_name}}
        recorded = stored.get(a.id, [])
        for item in recorded[:missing]:
            unscheduled.append({**who, "session_no": item.session_no, "reason_code": item.reason_code, "reason_text": item.reason_text})
        for n in range(len(recorded[:missing]), missing):  # missing, and no generation attempt recorded for it
            unscheduled.append({**who, "session_no": None, "reason_code": "not_scheduled",
                                "reason_text": f"No class is scheduled for {a.subject.code} for {a.batch.name} and no reason was recorded (the assignment may have been added after this timetable was generated)."})
        if done > a.sessions_per_week:
            problems.append({"code": "too_many_sessions", "severity": clash.HARD,
                             "message": f"{a.subject.code} for {a.batch.name} has {done} sessions scheduled but only {a.sessions_per_week} are required.",
                             "details": {"assignment_id": a.id, "required": a.sessions_per_week, "scheduled": done}})
        if len(recorded) > missing:
            warnings.append({"code": "stale_unscheduled_item", "severity": clash.ADVISORY,
                             "message": f"{a.subject.code} for {a.batch.name} is listed as unscheduled {len(recorded)} time(s) but only {missing} session(s) are missing.",
                             "details": {"assignment_id": a.id}})
    for assignment_id in sorted(foreign):
        problems.append({"code": "assignment_outside_term", "severity": clash.HARD, "message": "An entry belongs to a teaching assignment that is not part of this timetable's term.",
                         "details": {"assignment_id": assignment_id}})
    return {"required": required, "scheduled": scheduled, "unscheduled": unscheduled, "problems": problems, "warnings": warnings}


def validate(timetable_id: int) -> dict:
    """Validate and record the result. Reads current database state only; nothing from the client is trusted."""
    try:
        db.session.execute(db.select(Timetable.id).where(Timetable.id == timetable_id).with_for_update())  # one validation of a timetable at a time
        timetable = get_or_404(timetable_id)
        report = clash.validate_timetable(timetable.id)
        completeness = _completeness(timetable)
        periods = db.session.scalar(db.select(db.func.count()).select_from(TimetableEntry).where(TimetableEntry.timetable_id == timetable.id))

        hard = [c.to_dict() for c in report.hard] + completeness["problems"] + [c.to_dict() for c in workload_service.overload_conflicts(timetable)]
        warnings = [c.to_dict() for c in report.advisory] + completeness["warnings"]
        unscheduled = completeness["unscheduled"]
        is_complete = not unscheduled and completeness["scheduled"] == completeness["required"] and completeness["required"] > 0
        passed = not hard and is_complete

        timetable.validation_passed = passed
        timetable.validated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if passed and timetable.status == TimetableStatus.DRAFT:
            timetable.status = TimetableStatus.VALIDATED
        elif not passed and timetable.status == TimetableStatus.VALIDATED:
            timetable.status = TimetableStatus.DRAFT
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "timetable_id": timetable_id,
        "status": timetable.status.value,
        "validation_passed": passed,
        "is_valid": not hard,
        "is_complete": is_complete,
        "validated_at": timetable.validated_at.isoformat(),
        "counts": {
            "required_sessions": completeness["required"],
            "scheduled_sessions": completeness["scheduled"],
            "unscheduled_sessions": len(unscheduled),
            "scheduled_periods": periods,
            "hard_errors": len(hard),
            "warnings": len(warnings),
        },
        "hard_errors": hard,
        "warnings": warnings,
        "unscheduled": unscheduled,
    }
