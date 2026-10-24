"""Generated timetables, their entries and unscheduled sessions (owner: Jiya - R7, R10, R11, R16, R17)."""
import enum

from app.extensions import db
from app.models.base import TimestampMixin, enum_column


class TimetableStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Timetable(TimestampMixin, db.Model):
    __tablename__ = "timetables"
    __table_args__ = (db.UniqueConstraint("term_id", "version", name="uq_timetables_term_version"),)

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey("academic_terms.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    version = db.Column(db.Integer, nullable=False)  # R17: new number on every generation
    status = enum_column(TimetableStatus, nullable=False, default=TimetableStatus.DRAFT)
    # True only when validate_timetable() actually returned zero conflicts.
    validation_passed = db.Column(db.Boolean, nullable=False, default=False)
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    generated_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    validated_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    published_at = db.Column(db.DateTime)

    term = db.relationship("AcademicTerm")
    entries = db.relationship("TimetableEntry", backref="timetable", cascade="all, delete-orphan")
    unscheduled = db.relationship("UnscheduledItem", backref="timetable", cascade="all, delete-orphan")


class TimetableEntry(db.Model):
    """One class in one slot. The three unique constraints are a database-level
    safety net for the faculty / batch / room clash rules (the Python checks
    run first so users get a readable explanation)."""

    __tablename__ = "timetable_entries"
    __table_args__ = (
        db.UniqueConstraint("timetable_id", "faculty_id", "time_slot_id", name="uq_entry_faculty_slot"),
        db.UniqueConstraint("timetable_id", "batch_id", "time_slot_id", name="uq_entry_batch_slot"),
        db.UniqueConstraint("timetable_id", "room_id", "time_slot_id", name="uq_entry_room_slot"),
    )

    id = db.Column(db.Integer, primary_key=True)
    timetable_id = db.Column(db.Integer, db.ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("teaching_assignments.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey("time_slots.id"), nullable=False)

    assignment = db.relationship("TeachingAssignment")
    faculty = db.relationship("Faculty")
    batch = db.relationship("Batch")
    room = db.relationship("Room")
    time_slot = db.relationship("TimeSlot")


class UnscheduledItem(db.Model):
    """A required session the generator could not place, with the reason."""

    __tablename__ = "unscheduled_items"

    id = db.Column(db.Integer, primary_key=True)
    timetable_id = db.Column(db.Integer, db.ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("teaching_assignments.id"), nullable=False)
    session_no = db.Column(db.SmallInteger, nullable=False)
    reason_code = db.Column(db.String(40), nullable=False)
    reason_text = db.Column(db.Text, nullable=False)

    assignment = db.relationship("TeachingAssignment")
