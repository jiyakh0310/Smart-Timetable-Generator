"""Jiya - R16 approval and publishing workflow (Admin only; the system has exactly three roles, so the Admin both reviews and approves).

STATUS TRANSITIONS (anything else is 409 `illegal_transition`)
    submit   draft | validated | rejected   ->  pending_approval     (re-submission after a rejection is the same action)
    approve  pending_approval               ->  approved
    reject   pending_approval | approved    ->  rejected             (a written reason is required; also withdraws an approval)
    publish  approved                       ->  published            (the previously published version of the term becomes archived)
  `archived` is only ever reached by being superseded. `published` and `archived` are final here. Editing (R15) is open to
  draft, validated and rejected; pending_approval, approved, published and archived are immutable. A change to approved or
  published data is made by generating a NEW draft version (R7) - published data is never modified in place.

SAFETY
  * submit, approve and publish re-run the full validation (R10: hard rules, completeness, workload limits) on the CURRENT
    saved rows inside the transaction; a stored `validation_passed` is never trusted. If it fails nothing moves, the honest
    result is stored and 409 `validation_failed` returns the report.
  * One transaction per action: the read snapshot is ended (twice: before the lookup and again before the locks, so the first
    statement of the locking transaction is itself a locking read), the term row (publish only) and then the timetable row are
    locked FOR UPDATE, the status is re-read under the lock, and the checks and the change commit together. Concurrent
    requests therefore queue up: the loser sees the new status and gets `illegal_transition`.
  * At most one timetable per term is `published` - the CURRENT published version. Older ones stay as `archived` history.
  * Every transition is written to the application log (there is no audit table in this project).
"""
from datetime import datetime, timezone

from flask import current_app

from app.common.errors import AppError
from app.extensions import db
from app.models import AcademicTerm, Timetable, TimetableStatus
from app.modules.jiya import timetable_service as service, validation_service

S = TimetableStatus
TRANSITIONS = service.TRANSITIONS
NEEDS_VALIDATION = {"submit", "approve", "publish"}
REASON_MIN, REASON_MAX = 5, 500


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clean_reason(raw) -> str:
    reason = " ".join(raw.split()) if isinstance(raw, str) else ""
    if not reason:
        raise AppError("validation_error", "Give the reason for rejecting this timetable.", 400, {"reason": "A reason is required."})
    if len(reason) < REASON_MIN or len(reason) > REASON_MAX:
        raise AppError("validation_error", f"The reason must be {REASON_MIN} to {REASON_MAX} characters.", 400, {"reason": f"Use {REASON_MIN} to {REASON_MAX} characters."})
    return reason


def transition(timetable_id: int, action: str, user_id: int, reason: str | None = None) -> dict:
    allowed_from, target = TRANSITIONS[action]
    try:
        db.session.commit()  # end any read snapshot so the reads below happen after the locks
        term_id = db.session.scalar(db.select(Timetable.term_id).where(Timetable.id == timetable_id))
        if term_id is None:
            raise AppError("not_found", "Timetable not found.", 404)
        # That plain read opened a MySQL repeatable-read snapshot; end it, or the status read after the lock would be stale
        # and two concurrent requests could both pass the status check. The first statement below must be a locking read.
        db.session.commit()
        if action == "publish":
            db.session.execute(db.select(AcademicTerm.id).where(AcademicTerm.id == term_id).with_for_update())  # one publication per term at a time
        db.session.execute(db.select(Timetable.id).where(Timetable.id == timetable_id).with_for_update())
        timetable = service.get_or_404(timetable_id)

        if timetable.status not in allowed_from:
            needs = " or ".join(s.value.replace("_", " ") for s in allowed_from)
            raise AppError("illegal_transition", f"A {timetable.status.value.replace('_', ' ')} timetable cannot be {_past(action)}; it must be {needs} first.", 409,
                           {"status": timetable.status.value, "allowed_from": [s.value for s in allowed_from]})
        clean = clean_reason(reason) if action == "reject" else None

        validation = None
        if action in NEEDS_VALIDATION:
            validation = validation_service.evaluate(timetable)
            if not validation["validation_passed"]:
                db.session.commit()  # keep the honest result (flag, timestamp) even though the transition is refused
                raise AppError("validation_failed", _why(validation, action), 409, {"validation": validation})

        previous, superseded = timetable.status, []
        now = _now()
        if action == "submit":
            timetable.rejection_reason = None
        elif action == "approve":
            timetable.approved_by, timetable.approved_at, timetable.rejection_reason = user_id, now, None
        elif action == "reject":
            timetable.approved_by, timetable.approved_at, timetable.rejection_reason = None, None, clean
        elif action == "publish":
            for other in db.session.scalars(db.select(Timetable).where(Timetable.term_id == term_id, Timetable.status == S.PUBLISHED, Timetable.id != timetable.id)):
                other.status = S.ARCHIVED
                superseded.append(other.id)
            timetable.published_at = now
        timetable.status = target
        current_app.logger.info("timetable_transition timetable=%s term=%s action=%s from=%s to=%s user=%s superseded=%s%s", timetable.id, term_id, action, previous.value, target.value, user_id,
                                superseded, f" reason={clean!r}" if clean else "")
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    timetable = service.get_or_404(timetable_id)
    return {"timetable": service.serialize(timetable), "validation": validation, "superseded": superseded}


def _past(action: str) -> str:
    return {"submit": "submitted for approval", "approve": "approved", "reject": "rejected", "publish": "published"}[action]


def _why(validation: dict, action: str) -> str:
    c = validation["counts"]
    parts = []
    if c["hard_errors"]:
        parts.append(f"{c['hard_errors']} hard error{'s' if c['hard_errors'] != 1 else ''}")
    if not validation["is_complete"]:
        parts.append(f"{c['unscheduled_sessions']} required session{'s' if c['unscheduled_sessions'] != 1 else ''} not scheduled")
    return f"This timetable cannot be {_past(action)}: the latest validation found {' and '.join(parts)}. Fix them (or generate a new version) and try again."
