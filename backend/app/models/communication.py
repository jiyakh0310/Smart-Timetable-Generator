"""Announcements (Isha - R19) and system settings."""
import enum

from app.extensions import db
from app.models.base import TimestampMixin, enum_column


class Audience(str, enum.Enum):
    ALL = "all"
    FACULTY = "faculty"
    STUDENTS = "students"
    BATCH = "batch"


class AnnouncementStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Announcement(TimestampMixin, db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    audience = enum_column(Audience, nullable=False, default=Audience.ALL)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"))  # only when audience == batch
    status = enum_column(AnnouncementStatus, nullable=False, default=AnnouncementStatus.DRAFT)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    published_at = db.Column(db.DateTime)


class SystemSetting(db.Model):
    """Small key/value store, e.g. max_classes_per_day, max_faculty_hours."""

    __tablename__ = "system_settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255))
