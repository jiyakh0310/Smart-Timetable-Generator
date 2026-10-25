"""Jiya / Diya - R11 / R12 read-only views of the CURRENT PUBLISHED timetable for Faculty and Students.

SECURITY MODEL
  * Identity comes only from the signed-in account: Faculty -> the `faculty` row with `user_id = me`; Student -> the `students`
    row with `user_id = me` and its `batch_id`. The endpoints accept no faculty / batch / student / timetable identifier at all
    (any such query parameter is a 400), so nobody can ask for another person's or batch's timetable.
  * Only timetables whose status is `published` are ever read. draft, validated, pending_approval, approved, rejected and
    archived rows are never queried for content. At most one timetable per term is published (R16): the current version.
  * The answer is a deliberately small projection: sessions (subject, room, time and either the batch or the teacher), the
    periods of the week, and the term / version / publication date. No ids of timetables, no validation fields, no other
    teachers' or batches' rows, no capacities.
TERMS
  * The relevant term is the ACTIVE term (`academic_terms.is_active`). `terms` lists every term that has a current published
    timetable, and `?term_id=` selects one of them. A term without a published timetable simply returns an empty view.
SESSIONS
  * A lab's consecutive periods are returned as ONE session (`periods` = 2, `end_time` of the last period).
"""
from collections import defaultdict

from app.common.errors import AppError
from app.common.pagination import int_arg
from app.extensions import db
from app.models import AcademicTerm, ClassType, Faculty, Student, TimeSlot, Timetable, TimetableEntry, TimetableStatus
from app.modules.pragya.clash_service import DAY_NAMES

ALLOWED_PARAMS = {"term_id"}


def reject_identity_params(args, extra_allowed=()) -> None:
    extra = sorted(set(args) - ALLOWED_PARAMS - set(extra_allowed))
    if extra:
        raise AppError("validation_error", "This view only shows your own timetable; it does not accept " + ", ".join(extra) + ".", 400, {k: "Not allowed." for k in extra})


def _term_dict(t: AcademicTerm) -> dict:
    return {"id": t.id, "name": t.name, "academic_year": t.academic_year, "is_active": bool(t.is_active)}


def published_terms() -> list[AcademicTerm]:
    return db.session.scalars(
        db.select(AcademicTerm).where(AcademicTerm.id.in_(db.select(Timetable.term_id).where(Timetable.status == TimetableStatus.PUBLISHED))).order_by(AcademicTerm.id.desc())
    ).all()


def current_published(term_id: int) -> Timetable | None:
    return db.session.scalars(
        db.select(Timetable).where(Timetable.term_id == term_id, Timetable.status == TimetableStatus.PUBLISHED).order_by(Timetable.published_at.desc(), Timetable.version.desc()).limit(1)
    ).first()


def _choose_term(term_id: int | None, available: list[AcademicTerm]) -> AcademicTerm | None:
    if term_id is not None:
        return next((t for t in available if t.id == term_id), None) or db.session.get(AcademicTerm, term_id)
    return db.session.scalars(db.select(AcademicTerm).where(AcademicTerm.is_active.is_(True)).order_by(AcademicTerm.id.desc()).limit(1)).first()


def week_slots() -> list[dict]:
    rows = db.session.scalars(db.select(TimeSlot).where(TimeSlot.is_active.is_(True)).order_by(TimeSlot.day_of_week, TimeSlot.period_no)).all()
    return [{"day_of_week": s.day_of_week, "day_name": DAY_NAMES[s.day_of_week], "period_no": s.period_no, "start_time": s.start_time.strftime("%H:%M"),
             "end_time": s.end_time.strftime("%H:%M"), "slot_type": s.slot_type.value} for s in rows]


def _sessions(entries: list[TimetableEntry], who: str) -> list[dict]:
    """Merge a lab's consecutive periods into one session. `who` is 'faculty' (show the batch) or 'student' (show the teacher)."""
    by_assignment = defaultdict(list)
    for e in entries:
        by_assignment[e.assignment_id].append(e)
    out = []
    for rows in by_assignment.values():
        subject = rows[0].assignment.subject
        block = subject.lab_block_periods if subject.class_type == ClassType.LAB else 1
        rows.sort(key=lambda e: (e.time_slot.day_of_week, e.time_slot.period_no))
        runs, run = [], []
        for e in rows:
            if run and not (e.time_slot.day_of_week == run[-1].time_slot.day_of_week and e.time_slot.period_no == run[-1].time_slot.period_no + 1 and len(run) < block):
                runs.append(run)
                run = []
            run.append(e)
        if run:
            runs.append(run)
        for r in runs:
            first, last = r[0], r[-1]
            item = {
                "day_of_week": first.time_slot.day_of_week,
                "day_name": DAY_NAMES[first.time_slot.day_of_week],
                "period_no": first.time_slot.period_no,
                "periods": len(r),
                "start_time": first.time_slot.start_time.strftime("%H:%M"),
                "end_time": last.time_slot.end_time.strftime("%H:%M"),
                "subject": {"code": subject.code, "name": subject.name, "class_type": subject.class_type.value},
                "room": {"code": first.room.code, "name": first.room.name},
            }
            if who == "faculty":
                item["batch"] = {"name": first.batch.name}
            else:
                item["faculty"] = {"name": first.faculty.user.full_name}
            out.append(item)
    out.sort(key=lambda s: (s["day_of_week"], s["period_no"], s["subject"]["code"]))
    return out


def _view(term_arg, who: str, owner: dict, entry_filter) -> dict:
    available = published_terms()
    term = _choose_term(term_arg, available)
    timetable = current_published(term.id) if term else None
    data = {
        "owner": owner,
        "term": _term_dict(term) if term else None,
        "terms": [_term_dict(t) for t in available],
        "timetable": None,
        "slots": [],
        "sessions": [],
    }
    if timetable is None:
        return data
    entries = db.session.scalars(
        db.select(TimetableEntry).where(TimetableEntry.timetable_id == timetable.id, entry_filter)
    ).unique().all()
    data["timetable"] = {"name": timetable.name, "version": timetable.version, "published_at": timetable.published_at.isoformat() if timetable.published_at else None}
    data["slots"] = week_slots()
    data["sessions"] = _sessions(entries, who)
    return data


def faculty_view(user, args, extra_allowed=()) -> dict:
    reject_identity_params(args, extra_allowed)
    term_id = int_arg("term_id", minimum=1)
    me = db.session.scalar(db.select(Faculty).where(Faculty.user_id == user.id))
    if me is None:
        raise AppError("no_profile", "Your account is not linked to a faculty record. Please contact the administrator.", 409)
    return _view(term_id, "faculty", {"name": user.full_name, "employee_code": me.employee_code}, TimetableEntry.faculty_id == me.id)


def student_view(user, args, extra_allowed=()) -> dict:
    reject_identity_params(args, extra_allowed)
    term_id = int_arg("term_id", minimum=1)
    me = db.session.scalar(db.select(Student).where(Student.user_id == user.id))
    if me is None:
        raise AppError("no_profile", "Your account is not linked to a student record. Please contact the administrator.", 409)
    return _view(term_id, "student", {"name": user.full_name, "batch": me.batch.name}, TimetableEntry.batch_id == me.batch_id)
