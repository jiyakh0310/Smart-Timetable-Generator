"""Shared test helpers for Pragya's room and clash tests (they build timetable rows directly)."""
from datetime import time

from app.extensions import db
from app.models import Batch, Faculty, Room, SlotType, Subject, TeachingAssignment, TimeSlot, Timetable, TimetableEntry, User


def slot(day, period):
    return db.session.scalar(db.select(TimeSlot).where(TimeSlot.day_of_week == day, TimeSlot.period_no == period))


def sid(day, period):
    return slot(day, period).id


def room(code):
    return db.session.scalar(db.select(Room).where(Room.code == code))


def batch(section="A"):
    return db.session.scalar(db.select(Batch).where(Batch.section == section))


def faculty(code="F001"):
    return db.session.scalar(db.select(Faculty).where(Faculty.employee_code == code))


def subject(code):
    return db.session.scalar(db.select(Subject).where(Subject.code == code))


def assignment(batch_section, subject_code):
    return db.session.scalar(
        db.select(TeachingAssignment).join(Batch, Batch.id == TeachingAssignment.batch_id).join(Subject, Subject.id == TeachingAssignment.subject_id)
        .where(Batch.section == batch_section, Subject.code == subject_code)
    )


def new_timetable():
    admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
    t = Timetable(term_id=db.session.scalar(db.select(TeachingAssignment.term_id)), name="Test", version=1 + Timetable.query.count(), generated_by=admin.id)
    db.session.add(t)
    db.session.commit()
    return t


def place(timetable, assignment_obj, room_code, day, period, faculty_id=None, batch_id=None, slot_id=None):
    """Insert one timetable entry (one period). Overrides let a test create deliberate clashes."""
    entry = TimetableEntry(
        timetable_id=timetable.id, assignment_id=assignment_obj.id, faculty_id=faculty_id or assignment_obj.faculty_id,
        batch_id=batch_id or assignment_obj.batch_id, room_id=room(room_code).id, time_slot_id=slot_id or sid(day, period),
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def odd_slot(day, period_no, start, end, **over):
    """A slot that OVERLAPS others in time, inserted directly (the time-slot API would refuse it). Mimics misconfigured/legacy data."""
    s = TimeSlot(day_of_week=day, period_no=period_no, start_time=time(*start), end_time=time(*end), slot_type=SlotType.CLASS, is_active=True, **over)
    db.session.add(s)
    db.session.commit()
    return s
