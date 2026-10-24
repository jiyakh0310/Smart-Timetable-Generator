"""Faculty profile and availability (owner: Isha - R2, R13)."""
import enum

from app.extensions import db
from app.models.base import TimestampMixin, enum_column


class AvailabilityStatus(str, enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PREFERRED = "preferred"


class Faculty(TimestampMixin, db.Model):
    __tablename__ = "faculty"
    __table_args__ = (db.CheckConstraint("max_weekly_hours > 0", name="max_hours_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    employee_code = db.Column(db.String(30), nullable=False, unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    designation = db.Column(db.String(80))
    max_weekly_hours = db.Column(db.SmallInteger, nullable=False, default=18)

    user = db.relationship("User")
    department = db.relationship("Department")


class FacultyAvailability(db.Model):
    """No row for a slot means 'available by default'."""

    __tablename__ = "faculty_availability"
    __table_args__ = (db.UniqueConstraint("faculty_id", "time_slot_id", name="uq_availability_faculty_slot"),)

    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey("time_slots.id", ondelete="CASCADE"), nullable=False)
    status = enum_column(AvailabilityStatus, nullable=False)

    faculty = db.relationship("Faculty", backref=db.backref("availability", cascade="all, delete-orphan"))
    time_slot = db.relationship("TimeSlot")
