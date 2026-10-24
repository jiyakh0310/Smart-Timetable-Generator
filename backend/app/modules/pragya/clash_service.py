"""Pragya - R8 clash detection and R9 room allocation checks: reusable, side-effect free.

The generator (R7), manual editor (R15) and validator (R10) call these functions; nothing here writes to the database.

DEFINITIONS
  * A *period* is one TimeSlot (a weekday plus start and end time). A *session* is the one or more periods one class
    occupies: a theory class is one period, a lab is `lab_block_periods` CONSECUTIVE periods.
  * Two periods OVERLAP when they are on the same weekday and  a.start < b.end  and  b.start < a.end  (half-open
    intervals). Classes that merely touch (10:00 end / 10:00 start) do NOT overlap. This compares real times, so it is
    correct even if two slots with different ids were ever configured to cover the same time.
  * Periods are CONSECUTIVE when they are on the same weekday and their period numbers differ by exactly 1. A break has
    its own period number, so two periods either side of a break are not consecutive.

SEVERITY
  * "hard"     - the placement is invalid and must not be used.
  * "advisory" - information only (a soft preference was not honoured); NEVER a prohibition.
Faculty availability: status "unavailable" is HARD; "preferred" is soft and can only ever produce an advisory note.
"""
from dataclasses import dataclass, field

from app.common.errors import AppError
from app.extensions import db
from app.models import (
    AvailabilityStatus,
    Batch,
    ClassType,
    Faculty,
    FacultyAvailability,
    Room,
    RoomType,
    SlotType,
    Subject,
    TeachingAssignment,
    TimeSlot,
    Timetable,
    TimetableEntry,
)

HARD, ADVISORY = "hard", "advisory"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class Conflict:
    code: str
    severity: str
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class Placement:
    """One proposed class: who, for which batch, where, and in which period(s)."""

    faculty_id: int
    batch_id: int
    room_id: int
    time_slot_ids: tuple[int, ...]
    subject_id: int | None = None  # when known, room type and session length are checked too


@dataclass(frozen=True)
class ScheduledPeriod:
    """One period already placed in a timetable (a row of timetable_entries)."""

    entry_id: int | None
    faculty_id: int
    batch_id: int
    room_id: int
    time_slot_id: int


@dataclass
class ValidationReport:
    timetable_id: int
    conflicts: list[Conflict]

    @property
    def hard(self) -> list[Conflict]:
        return [c for c in self.conflicts if c.severity == HARD]

    @property
    def advisory(self) -> list[Conflict]:
        return [c for c in self.conflicts if c.severity == ADVISORY]

    @property
    def is_valid(self) -> bool:
        """Only true when NO hard conflict exists. Advisory notes never make a timetable invalid."""
        return not self.hard

    def to_dict(self) -> dict:
        return {
            "timetable_id": self.timetable_id,
            "is_valid": self.is_valid,
            "hard_count": len(self.hard),
            "advisory_count": len(self.advisory),
            "conflicts": [c.to_dict() for c in sorted(self.conflicts, key=lambda c: c.severity != HARD)],
        }


# ---------- pure helpers ----------
def slots_overlap(a: TimeSlot, b: TimeSlot) -> bool:
    return a.day_of_week == b.day_of_week and a.start_time < b.end_time and b.start_time < a.end_time


def are_consecutive(ordered: list[TimeSlot]) -> bool:
    return all(a.day_of_week == b.day_of_week and b.period_no == a.period_no + 1 for a, b in zip(ordered, ordered[1:]))


def session_length(subject: Subject | None) -> int | None:
    if subject is None:
        return None
    return subject.lab_block_periods if subject.class_type == ClassType.LAB else 1


def describe(slot: TimeSlot) -> str:
    return f"{DAY_NAMES[slot.day_of_week]} period {slot.period_no} ({slot.start_time:%H:%M}-{slot.end_time:%H:%M})"


# ---------- loading ----------
def _need(model, pk, label):
    obj = db.session.get(model, pk)
    if obj is None:
        raise AppError("validation_error", f"Unknown {label}.", 400, {f"{label}_id": f"Choose an existing {label}."})
    return obj


def load_periods(timetable_id: int) -> list[ScheduledPeriod]:
    rows = db.session.scalars(db.select(TimetableEntry).where(TimetableEntry.timetable_id == timetable_id)).all()
    return [ScheduledPeriod(r.id, r.faculty_id, r.batch_id, r.room_id, r.time_slot_id) for r in rows]


class PlanningContext:
    """Optional read-through cache for callers that run thousands of checks (the generator).

    It only avoids repeated queries for slots, availability and rooms; every rule still lives in this module. Build one per
    planning run and discard it: it is a snapshot and never sees later changes."""

    def __init__(self):
        self._slots = {s.id: s for s in db.session.scalars(db.select(TimeSlot)).all()}
        self._rooms = db.session.scalars(db.select(Room).order_by(Room.capacity, Room.code)).all()
        self._availability: dict[int, dict[int, AvailabilityStatus]] = {}

    def slot_map(self, ids) -> dict[int, TimeSlot]:
        return {i: self._slots[i] for i in set(ids) if i in self._slots}

    def rooms(self) -> list[Room]:
        return self._rooms

    def availability(self, faculty_id: int) -> dict[int, AvailabilityStatus]:
        if faculty_id not in self._availability:
            rows = db.session.scalars(db.select(FacultyAvailability).where(FacultyAvailability.faculty_id == faculty_id))
            self._availability[faculty_id] = {r.time_slot_id: r.status for r in rows}
        return self._availability[faculty_id]


def _slot_map(ids, context: "PlanningContext | None" = None) -> dict[int, TimeSlot]:
    if context is not None:
        return context.slot_map(ids)
    ids = set(ids)
    if not ids:
        return {}
    return {s.id: s for s in db.session.scalars(db.select(TimeSlot).where(TimeSlot.id.in_(ids))).all()}


# ---------- individual checks ----------
def _slot_conflicts(requested: list[int], slots: dict[int, TimeSlot]) -> list[Conflict]:
    out = []
    for slot_id in requested:
        slot = slots.get(slot_id)
        if slot is None:
            out.append(Conflict("slot_unknown", HARD, f"Time slot {slot_id} does not exist.", {"time_slot_id": slot_id}))
        elif slot.slot_type == SlotType.BREAK:
            out.append(Conflict("slot_is_break", HARD, f"{describe(slot)} is a break; no class can be scheduled in it.", {"time_slot_id": slot_id}))
        elif not slot.is_active:
            out.append(Conflict("slot_inactive", HARD, f"{describe(slot)} is disabled and cannot be used.", {"time_slot_id": slot_id}))
    return out


def _shape_conflicts(requested: list[int], slots: dict[int, TimeSlot], subject: Subject | None) -> list[Conflict]:
    out = []
    if len(set(requested)) != len(requested):
        out.append(Conflict("duplicate_slot", HARD, "The same time slot was listed more than once.", {"time_slot_ids": requested}))
    known = sorted((slots[i] for i in set(requested) if i in slots), key=lambda s: (s.day_of_week, s.period_no))
    expected = session_length(subject)
    if expected is not None and len(set(requested)) != expected:
        kind = "lab session" if subject.class_type == ClassType.LAB else "class"
        out.append(Conflict("wrong_session_length", HARD, f"A {kind} for {subject.code} needs {expected} period{'' if expected == 1 else 's'}, not {len(set(requested))}.",
                            {"expected": expected, "given": len(set(requested))}))
    if len(known) > 1 and not are_consecutive(known):
        out.append(Conflict("not_consecutive", HARD, "A multi-period session needs consecutive periods on the same day (a break between periods breaks the run).",
                            {"time_slot_ids": [s.id for s in known]}))
    return out


def _room_conflicts(room: Room, batch: Batch, subject: Subject | None) -> list[Conflict]:
    out = []
    if not room.is_available:
        out.append(Conflict("room_unavailable", HARD, f"{room.code} is out of service.", {"room_id": room.id}))
    if room.capacity < batch.strength:
        out.append(Conflict("room_too_small", HARD, f"{room.code} seats {room.capacity} but {batch.name} has {batch.strength} students.",
                            {"room_id": room.id, "capacity": room.capacity, "strength": batch.strength}))
    if subject is not None:
        if subject.class_type == ClassType.LAB and room.room_type != RoomType.LAB:
            out.append(Conflict("room_type_mismatch", HARD, f"{subject.code} is a lab subject and needs a laboratory, but {room.code} is a {room.room_type.value.replace('_', ' ')}.",
                                {"room_id": room.id, "required": "lab", "actual": room.room_type.value}))
        elif subject.class_type == ClassType.THEORY and room.room_type == RoomType.LAB:
            out.append(Conflict("room_type_mismatch", HARD, f"{subject.code} is a theory subject, so it cannot use the laboratory {room.code}.",
                                {"room_id": room.id, "actual": "lab"}))
        elif subject.required_room_type and subject.class_type == ClassType.THEORY and subject.required_room_type != room.room_type:
            out.append(Conflict("room_type_mismatch", HARD, f"{subject.code} requires a {subject.required_room_type.value.replace('_', ' ')}, but {room.code} is a {room.room_type.value.replace('_', ' ')}.",
                                {"room_id": room.id, "required": subject.required_room_type.value, "actual": room.room_type.value}))
    return out


def _availability_conflicts(faculty: Faculty, slots: list[TimeSlot], context: "PlanningContext | None" = None) -> list[Conflict]:
    if context is not None:
        rows = context.availability(faculty.id)
    else:
        rows = {r.time_slot_id: r.status for r in db.session.scalars(db.select(FacultyAvailability).where(FacultyAvailability.faculty_id == faculty.id))}
    name = faculty.user.full_name
    out = []
    blocked = [s for s in slots if rows.get(s.id) == AvailabilityStatus.UNAVAILABLE]  # HARD
    for s in blocked:
        out.append(Conflict("faculty_unavailable", HARD, f"{name} is marked unavailable in {describe(s)}.", {"faculty_id": faculty.id, "time_slot_id": s.id}))
    has_preferences = any(st == AvailabilityStatus.PREFERRED for st in rows.values())
    outside = [s for s in slots if rows.get(s.id) != AvailabilityStatus.PREFERRED and s not in blocked]
    if has_preferences and outside:  # SOFT: informational only
        out.append(Conflict("outside_preferred_slots", ADVISORY, f"{name} has preferred time slots and {describe(outside[0])} is not one of them. This is a preference, not a rule.",
                            {"faculty_id": faculty.id, "time_slot_ids": [s.id for s in outside]}))
    return out


def _clash_conflicts(placement: Placement, slots: dict[int, TimeSlot], scheduled: list[ScheduledPeriod], ignore: set[int], context: "PlanningContext | None" = None) -> list[Conflict]:
    out = []
    mine = [slots[i] for i in set(placement.time_slot_ids) if i in slots]
    if not mine:
        return out
    cache = _slot_map({sp.time_slot_id for sp in scheduled} - set(slots), context)
    cache.update(slots)
    for sp in scheduled:
        if sp.entry_id is not None and sp.entry_id in ignore:
            continue
        other = cache.get(sp.time_slot_id)
        if other is None:
            continue
        hit = next((s for s in mine if slots_overlap(s, other)), None)
        if hit is None:
            continue
        for resource, code, label in (("faculty_id", "faculty_clash", "faculty member"), ("batch_id", "batch_clash", "batch"), ("room_id", "room_clash", "room")):
            if getattr(sp, resource) == getattr(placement, resource):
                out.append(Conflict(code, HARD, f"The same {label} is already scheduled in {describe(other)}, which overlaps {describe(hit)}.",
                                    {resource: getattr(sp, resource), "entry_id": sp.entry_id, "time_slot_id": sp.time_slot_id}))
    return out


# ---------- public API ----------
def slot_problems(time_slot_ids) -> list[Conflict]:
    """Slots that can never hold a class (unknown, break, disabled). Used by the room finder as well as check_session."""
    ids = list(time_slot_ids)
    return _slot_conflicts(ids, _slot_map(ids))


def check_session(placement: Placement, scheduled: list[ScheduledPeriod] | None = None, timetable_id: int | None = None, ignore_entry_ids=(), context: PlanningContext | None = None) -> list[Conflict]:
    """Every conflict a proposed class would cause. `scheduled` (or the entries of `timetable_id`) is what is already placed."""
    faculty = _need(Faculty, placement.faculty_id, "faculty")
    batch = _need(Batch, placement.batch_id, "batch")
    room = _need(Room, placement.room_id, "room")
    subject = _need(Subject, placement.subject_id, "subject") if placement.subject_id is not None else None
    if scheduled is None:
        scheduled = load_periods(timetable_id) if timetable_id is not None else []

    requested = list(placement.time_slot_ids)
    slots = _slot_map(requested, context)
    conflicts = _slot_conflicts(requested, slots)
    conflicts += _shape_conflicts(requested, slots, subject)
    conflicts += _room_conflicts(room, batch, subject)
    conflicts += _availability_conflicts(faculty, [slots[i] for i in dict.fromkeys(requested) if i in slots], context)
    conflicts += _clash_conflicts(placement, slots, scheduled, set(ignore_entry_ids), context)
    return conflicts


def has_hard_conflict(conflicts: list[Conflict]) -> bool:
    return any(c.severity == HARD for c in conflicts)


def validate_timetable(timetable_id: int) -> ValidationReport:
    """Re-check every entry of a saved timetable (R8/R9 rules). Completeness (all required classes scheduled) is R10's job."""
    if db.session.get(Timetable, timetable_id) is None:
        raise AppError("not_found", "Timetable not found.", 404)
    entries = db.session.scalars(db.select(TimetableEntry).where(TimetableEntry.timetable_id == timetable_id)).all()
    scheduled = [ScheduledPeriod(e.id, e.faculty_id, e.batch_id, e.room_id, e.time_slot_id) for e in entries]
    all_slots = _slot_map({e.time_slot_id for e in entries})

    conflicts: list[Conflict] = []
    seen_pairs: set = set()
    for e in entries:
        subject = e.assignment.subject
        placement = Placement(e.faculty_id, e.batch_id, e.room_id, (e.time_slot_id,), subject.id)
        slots = {e.time_slot_id: all_slots[e.time_slot_id]}
        own = _slot_conflicts([e.time_slot_id], slots) + _room_conflicts(e.room, e.batch, subject) + _availability_conflicts(e.faculty, list(slots.values()))
        conflicts += [Conflict(c.code, c.severity, c.message, {**c.details, "entry_id": e.id}) for c in own]
        for c in _clash_conflicts(placement, slots, scheduled, {e.id}):
            other_id = c.details["entry_id"]
            key = (c.code, frozenset({e.id, other_id}))
            if key in seen_pairs:  # a clash between entries A and B is one problem, not two
                continue
            seen_pairs.add(key)
            conflicts.append(Conflict(c.code, c.severity, c.message, {**c.details, "entry_id": e.id, "other_entry_id": other_id}))
    conflicts += _lab_run_conflicts(entries, all_slots)
    return ValidationReport(timetable_id, conflicts)


def _lab_run_conflicts(entries: list[TimetableEntry], slots: dict[int, TimeSlot]) -> list[Conflict]:
    """Each lab assignment's periods on a day must form runs of consecutive periods whose length is a whole number of sessions."""
    out = []
    by_assignment: dict[int, list[TimetableEntry]] = {}
    for e in entries:
        if e.assignment.subject.class_type == ClassType.LAB:
            by_assignment.setdefault(e.assignment_id, []).append(e)
    for assignment_id, rows in by_assignment.items():
        subject = rows[0].assignment.subject
        block = subject.lab_block_periods
        by_day: dict[int, list[int]] = {}
        for e in rows:
            s = slots[e.time_slot_id]
            by_day.setdefault(s.day_of_week, []).append(s.period_no)
        for day, periods in by_day.items():
            periods.sort()
            runs, run = [], [periods[0]]
            for p in periods[1:]:
                if p == run[-1] + 1:
                    run.append(p)
                else:
                    runs.append(run)
                    run = [p]
            runs.append(run)
            for r in runs:
                if len(r) % block != 0:
                    out.append(Conflict("lab_not_consecutive", HARD,
                                        f"{subject.code} on {DAY_NAMES[day]}: periods {', '.join(map(str, r))} do not form whole {block}-period lab sessions.",
                                        {"assignment_id": assignment_id, "day_of_week": day, "periods": r, "required_block": block}))
    return out


@dataclass
class RoomVerdict:
    room: Room
    reasons: list[Conflict]

    @property
    def suitable(self) -> bool:
        return not self.reasons


def explain_rooms(subject: Subject, batch: Batch, time_slot_ids, scheduled: list[ScheduledPeriod] | None = None, timetable_id: int | None = None, ignore_entry_ids=(), context: PlanningContext | None = None) -> list[RoomVerdict]:
    """Every room with the reasons it is NOT suitable (empty reasons = suitable). Smallest capacity first."""
    if scheduled is None:
        scheduled = load_periods(timetable_id) if timetable_id is not None else []
    slots = _slot_map(time_slot_ids, context)
    rooms = context.rooms() if context is not None else db.session.scalars(db.select(Room).order_by(Room.capacity, Room.code)).all()
    verdicts = []
    for room in rooms:
        reasons = _room_conflicts(room, batch, subject)
        probe = Placement(faculty_id=-1, batch_id=-1, room_id=room.id, time_slot_ids=tuple(time_slot_ids))  # only the room dimension matters here
        reasons += [c for c in _clash_conflicts(probe, slots, scheduled, set(ignore_entry_ids), context) if c.code == "room_clash"]
        verdicts.append(RoomVerdict(room, reasons))
    return verdicts


def rank_rooms(subject: Subject, batch: Batch, time_slot_ids, scheduled: list[ScheduledPeriod] | None = None, timetable_id: int | None = None, ignore_entry_ids=(), context: PlanningContext | None = None) -> list[Room]:
    """Suitable rooms, smallest suitable capacity first (R9: efficient use of rooms)."""
    return [v.room for v in explain_rooms(subject, batch, time_slot_ids, scheduled, timetable_id, ignore_entry_ids, context) if v.suitable]


def placement_for_assignment(assignment: TeachingAssignment, room_id: int, time_slot_ids) -> Placement:
    return Placement(assignment.faculty_id, assignment.batch_id, room_id, tuple(time_slot_ids), assignment.subject_id)
