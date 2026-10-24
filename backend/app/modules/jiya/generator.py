"""Jiya - R7 constraint-based timetable generator (pure planning: it reads data and returns a plan, it never writes).

HEURISTIC (deterministic: the same data always gives the same plan)
  1. Every session an assignment needs per week becomes one *session* (a theory class = 1 period, a lab = `lab_block_periods`
     consecutive periods).
  2. Sessions are placed MOST-CONSTRAINED FIRST: fewest feasible windows, then labs before theory, then larger batches,
     then by id.
  3. For one session every candidate window (a single class period, or a run of consecutive class periods for a lab) is
     tried best-score first. A window is accepted only when the existing Pragya services report no hard conflict:
     `check_session` (faculty / batch clashes by real clock time, unavailability, slot validity, session shape) and
     `rank_rooms` (capacity, room type, room clashes). No conflict rule is re-implemented here.
  4. The score is SOFT only: honour preferred periods, spread a subject over different days, balance the days of a batch.
     A preference can never make a window invalid.
  5. A session that cannot be placed is recorded with a reason; nothing is dropped silently.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from app.extensions import db
from app.models import AvailabilityStatus, ClassType, SlotType, TeachingAssignment, TimeSlot
from app.modules.isha import workload_service as workload
from app.modules.pragya import clash_service as clash
from app.modules.pragya.clash_service import Placement, PlanningContext, ScheduledPeriod

SPREAD_PENALTY = 6      # a second class of the same subject on a day the batch already has it
OUTSIDE_PREFERENCE_PENALTY = 10  # per period outside a faculty member's preferred periods
DAY_LOAD_PENALTY = 1    # per period the batch already has that day
FACULTY_DAY_PENALTY = 2  # per period the faculty member already teaches that day (balances a person's week across days)


@dataclass
class PlannedSession:
    assignment_id: int
    session_no: int
    faculty_id: int
    batch_id: int
    subject_id: int
    room_id: int
    time_slot_ids: tuple[int, ...]


@dataclass
class UnplacedSession:
    assignment_id: int
    session_no: int
    reason_code: str
    reason_text: str


@dataclass
class Plan:
    placed: list[PlannedSession] = field(default_factory=list)
    unplaced: list[UnplacedSession] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_sessions: int = 0
    workload: list[dict] = field(default_factory=list)

    @property
    def periods(self) -> list[ScheduledPeriod]:
        return [ScheduledPeriod(None, s.faculty_id, s.batch_id, s.room_id, t) for s in self.placed for t in s.time_slot_ids]


@dataclass
class _Session:
    assignment: TeachingAssignment
    session_no: int
    length: int
    windows: list[tuple[TimeSlot, ...]]


def class_slots() -> list[TimeSlot]:
    """Only active class periods; breaks and disabled slots can never hold a class."""
    return db.session.scalars(
        db.select(TimeSlot).where(TimeSlot.is_active.is_(True), TimeSlot.slot_type == SlotType.CLASS).order_by(TimeSlot.day_of_week, TimeSlot.period_no)
    ).all()


def windows_for(slots: list[TimeSlot], length: int) -> list[tuple[TimeSlot, ...]]:
    """Every run of `length` consecutive periods on one day (length 1 = each single period)."""
    by_day = defaultdict(list)
    for s in slots:
        by_day[s.day_of_week].append(s)
    out = []
    for day in sorted(by_day):
        day_slots = sorted(by_day[day], key=lambda s: s.period_no)
        for i in range(len(day_slots) - length + 1):
            run = tuple(day_slots[i:i + length])
            if clash.are_consecutive(list(run)):
                out.append(run)
    return out


def required_sessions(assignments: list[TeachingAssignment]) -> int:
    return sum(a.sessions_per_week for a in assignments)


def plan_term(assignments: list[TeachingAssignment]) -> Plan:
    plan = Plan(required_sessions=required_sessions(assignments))
    ctx = PlanningContext()
    slots = class_slots()
    usable_ids = {s.id for s in slots}

    sessions: list[_Session] = []
    for a in assignments:
        length = clash.session_length(a.subject)
        blocked = {sid for sid, st in ctx.availability(a.faculty_id).items() if st == AvailabilityStatus.UNAVAILABLE}
        free_slots = [s for s in slots if s.id not in blocked]
        windows = windows_for(free_slots, length)
        for n in range(1, a.sessions_per_week + 1):
            sessions.append(_Session(a, n, length, windows))
        if a.sessions_per_week != _expected(a):
            plan.warnings.append(f"{a.batch.name} / {a.subject.code}: the assignment lists {a.sessions_per_week} sessions but the subject now implies {_expected(a)}; the assignment value was used.")

    sessions.sort(key=lambda s: (len(s.windows), s.length == 1, -s.assignment.batch.strength, s.assignment.id, s.session_no))

    scheduled: list[ScheduledPeriod] = []
    batch_day_load = defaultdict(int)          # (batch, day) -> periods
    faculty_day_load = defaultdict(int)        # (faculty, day) -> periods
    used_minutes = defaultdict(int)            # faculty -> teaching minutes placed so far (R14)
    subject_days = defaultdict(set)            # (batch, subject) -> days used
    static_rooms: dict[tuple[int, int], list] = {}  # (batch, subject) -> rooms that fit regardless of time
    outside_preference = 0

    for sess in sessions:
        a = sess.assignment
        if not a.faculty.user.is_active:
            plan.unplaced.append(UnplacedSession(a.id, sess.session_no, "faculty_inactive", f"{a.faculty.user.full_name} is not an active faculty member, so no class can be scheduled for them."))
            continue
        if not usable_ids:
            plan.unplaced.append(UnplacedSession(a.id, sess.session_no, "no_class_slots", "There are no active class periods configured."))
            continue
        if not sess.windows:
            plan.unplaced.append(_no_window_reason(a, sess, ctx, slots))
            continue

        key = (a.batch_id, a.subject_id)
        if key not in static_rooms:  # rooms that fit this batch and subject at all (ignoring time)
            first = tuple(s.id for s in sess.windows[0])
            static_rooms[key] = [v.room for v in clash.explain_rooms(a.subject, a.batch, first, scheduled=[], context=ctx) if v.suitable]
        if not static_rooms[key]:
            plan.unplaced.append(UnplacedSession(a.id, sess.session_no, "no_suitable_room", _no_room_text(a, ctx)))
            continue

        prefs = ctx.availability(a.faculty_id)
        has_prefs = any(st == AvailabilityStatus.PREFERRED for st in prefs.values())

        def score(window):
            day = window[0].day_of_week
            s = DAY_LOAD_PENALTY * batch_day_load[(a.batch_id, day)] + FACULTY_DAY_PENALTY * faculty_day_load[(a.faculty_id, day)]
            if day in subject_days[key]:
                s += SPREAD_PENALTY
            if has_prefs:
                s += OUTSIDE_PREFERENCE_PENALTY * sum(1 for x in window if prefs.get(x.id) != AvailabilityStatus.PREFERRED)
            return (s, window[0].day_of_week, window[0].period_no)

        limit = workload.limit_minutes(a.faculty)  # hard weekly maximum; None = no limit configured
        length_min = lambda window: sum(workload.slot_minutes(x) for x in window)
        if limit is not None and used_minutes[a.faculty_id] + min(length_min(w) for w in sess.windows) > limit:
            plan.unplaced.append(_workload_reason(a, sess.session_no, used_minutes[a.faculty_id], limit, min(length_min(w) for w in sess.windows)))
            continue

        blocked_by = {"faculty": 0, "batch": 0, "room": 0, "other": 0, "workload": 0}
        chosen = None
        for window in sorted(sess.windows, key=score):
            if limit is not None and used_minutes[a.faculty_id] + length_min(window) > limit:
                blocked_by["workload"] += 1  # a longer window would exceed the weekly maximum; a shorter one may still fit
                continue
            ids = tuple(x.id for x in window)
            probe = Placement(a.faculty_id, a.batch_id, static_rooms[key][0].id, ids, a.subject_id)
            hard = {c.code for c in clash.check_session(probe, scheduled, context=ctx) if c.severity == clash.HARD}
            hard.discard("room_clash")  # the probe room may be busy; the real room is chosen below
            if "faculty_clash" in hard:
                blocked_by["faculty"] += 1
                continue
            if "batch_clash" in hard:
                blocked_by["batch"] += 1
                continue
            if hard:
                blocked_by["other"] += 1
                continue
            rooms = clash.rank_rooms(a.subject, a.batch, ids, scheduled, context=ctx)  # smallest suitable room first
            for room in rooms:
                final = Placement(a.faculty_id, a.batch_id, room.id, ids, a.subject_id)
                if not clash.has_hard_conflict(clash.check_session(final, scheduled, context=ctx)):
                    chosen = (window, room, final)
                    break
            if chosen:
                break
            blocked_by["room"] += 1

        if chosen is None:
            plan.unplaced.append(_blocked_reason(a, sess, blocked_by))
            continue

        window, room, placement = chosen
        plan.placed.append(PlannedSession(a.id, sess.session_no, a.faculty_id, a.batch_id, a.subject_id, room.id, placement.time_slot_ids))
        for x in window:
            scheduled.append(ScheduledPeriod(None, a.faculty_id, a.batch_id, room.id, x.id))
            batch_day_load[(a.batch_id, x.day_of_week)] += 1
            faculty_day_load[(a.faculty_id, x.day_of_week)] += 1
            used_minutes[a.faculty_id] += workload.slot_minutes(x)
        subject_days[key].add(window[0].day_of_week)
        if has_prefs and any(prefs.get(x.id) != AvailabilityStatus.PREFERRED for x in window):
            outside_preference += 1

    if outside_preference:
        plan.warnings.append(f"{outside_preference} session{'s' if outside_preference != 1 else ''} had to be placed outside a faculty member's preferred periods (a preference, not a rule).")
    seen_faculty = {a.faculty_id: a.faculty for a in assignments}
    assigned = workload.assigned_minutes(assignments[0].term_id) if assignments else {}
    plan.workload = workload.rows(list(seen_faculty.values()), dict(used_minutes), assigned)
    # the over-assignment warning describes the INPUT, so it is built from the unscheduled state, not from the result
    plan.warnings = workload.assignment_warnings(workload.rows(list(seen_faculty.values()), {}, assigned)) + plan.warnings
    plan.placed.sort(key=lambda p: (p.assignment_id, p.session_no))
    plan.unplaced.sort(key=lambda u: (u.assignment_id, u.session_no))
    return plan


def _expected(a: TeachingAssignment) -> int:
    from app.modules.diya.assignment_service import expected_sessions
    return expected_sessions(a.subject)


def _label(a: TeachingAssignment) -> str:
    return f"{a.subject.code} for {a.batch.name} ({a.faculty.user.full_name})"


def _no_window_reason(a, sess, ctx, slots) -> UnplacedSession:
    blocked = {sid for sid, st in ctx.availability(a.faculty_id).items() if st == AvailabilityStatus.UNAVAILABLE}
    if sess.length > 1 and windows_for(slots, sess.length):
        if blocked and windows_for([s for s in slots if s.id not in blocked], sess.length) == []:
            return UnplacedSession(a.id, sess.session_no, "faculty_unavailable", f"{a.faculty.user.full_name} is unavailable in every run of {sess.length} consecutive periods, so {_label(a)} lab cannot be placed.")
    if sess.length > 1 and not windows_for(slots, sess.length):
        return UnplacedSession(a.id, sess.session_no, "no_consecutive_window", f"No day has {sess.length} consecutive class periods (breaks split the day), so the lab session for {_label(a)} cannot be placed.")
    return UnplacedSession(a.id, sess.session_no, "faculty_unavailable", f"{a.faculty.user.full_name} is marked unavailable in every class period, so {_label(a)} cannot be placed.")


def _no_room_text(a, ctx) -> str:
    kind = "laboratory" if a.subject.class_type == ClassType.LAB else (a.subject.required_room_type.value.replace("_", " ") if a.subject.required_room_type else "classroom")
    return f"No room in service is a suitable {kind} with at least {a.batch.strength} seats for {_label(a)}."


def _blocked_reason(a, sess, blocked_by) -> UnplacedSession:
    total = sum(blocked_by.values())
    detail = f"{total} possible period{'s' if total != 1 else ''} checked: {blocked_by['faculty']} blocked by the faculty member's other classes, {blocked_by['batch']} by the batch's other classes, {blocked_by['room']} with no free suitable room, {blocked_by['workload']} over the faculty member's weekly hour limit."
    worst = max(("faculty", "batch", "room", "workload"), key=lambda k: (blocked_by[k], ("room", "batch", "faculty", "workload").index(k)))
    code = {"faculty": "faculty_busy", "batch": "batch_busy", "room": "rooms_busy", "workload": "workload_limit"}[worst]
    if blocked_by[worst] == 0:
        code = "no_free_slot"
    return UnplacedSession(a.id, sess.session_no, code, f"No free period remains for {_label(a)}. {detail}")


def _workload_reason(a, session_no, used, limit, needed) -> UnplacedSession:
    h = workload.hours
    return UnplacedSession(a.id, session_no, "workload_limit",
                           f"{_label(a)} would take {a.faculty.user.full_name} to {h(used + needed):g} h per week, over the maximum of {h(limit):g} h ({h(used):g} h are already scheduled).")
