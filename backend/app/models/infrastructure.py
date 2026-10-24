"""Rooms, equipment and time slots (rooms: Pragya R5/R23, time slots: Diya R6)."""
import enum

from sqlalchemy import true

from app.extensions import db
from app.models.base import TimestampMixin, enum_column


class RoomType(str, enum.Enum):
    CLASSROOM = "classroom"
    LAB = "lab"
    SEMINAR_HALL = "seminar_hall"
    AUDITORIUM = "auditorium"


class SlotType(str, enum.Enum):
    CLASS = "class"
    BREAK = "break"


class Room(TimestampMixin, db.Model):
    __tablename__ = "rooms"
    __table_args__ = (db.CheckConstraint("capacity > 0", name="capacity_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(120))
    capacity = db.Column(db.Integer, nullable=False)
    room_type = enum_column(RoomType, nullable=False)
    lab_type = db.Column(db.String(60))  # e.g. "Computer", "Electronics"; only for labs
    is_available = db.Column(db.Boolean, nullable=False, server_default=true())


class Equipment(db.Model):
    __tablename__ = "equipment"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)


room_equipment = db.Table(
    "room_equipment",
    db.Column("room_id", db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
    db.Column("equipment_id", db.Integer, db.ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True),
)

subject_equipment = db.Table(
    "subject_equipment",
    db.Column("subject_id", db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
    db.Column("equipment_id", db.Integer, db.ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True),
)


class TimeSlot(TimestampMixin, db.Model):
    """One period on one weekday. day_of_week: 0=Monday ... 6=Sunday."""

    __tablename__ = "time_slots"
    __table_args__ = (
        db.UniqueConstraint("day_of_week", "period_no", name="uq_time_slots_day_period"),
        db.CheckConstraint("start_time < end_time", name="start_before_end"),
        db.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="day_in_week"),
    )

    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.SmallInteger, nullable=False)
    period_no = db.Column(db.SmallInteger, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    slot_type = enum_column(SlotType, nullable=False, default=SlotType.CLASS)
    is_active = db.Column(db.Boolean, nullable=False, server_default=true())
