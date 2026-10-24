"""Departments, terms, batches, students, subjects and teaching assignments.

Owner: Diya (R3, R4) - shared structure used by every other module.
"""
import enum

from sqlalchemy import true

from app.extensions import db
from app.models.base import TimestampMixin, enum_column
from app.models.infrastructure import RoomType, subject_equipment


class TermType(str, enum.Enum):
    ODD = "odd"
    EVEN = "even"


class ClassType(str, enum.Enum):
    THEORY = "theory"
    LAB = "lab"


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)


class Program(db.Model):
    __tablename__ = "programs"
    __table_args__ = (db.UniqueConstraint("department_id", "name", name="uq_programs_department_name"),)

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    duration_semesters = db.Column(db.SmallInteger, nullable=False, default=8)

    department = db.relationship("Department")


class AcademicTerm(db.Model):
    __tablename__ = "academic_terms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False, unique=True)
    academic_year = db.Column(db.String(9), nullable=False)  # e.g. "2026-27"
    term_type = enum_column(TermType, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, nullable=False, server_default=true())


class Batch(TimestampMixin, db.Model):
    """A group of students scheduled together. `strength` drives room allocation."""

    __tablename__ = "batches"
    __table_args__ = (
        db.UniqueConstraint("program_id", "semester_no", "section", name="uq_batches_program_sem_section"),
        db.CheckConstraint("strength > 0", name="strength_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    semester_no = db.Column(db.SmallInteger, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    strength = db.Column(db.Integer, nullable=False)

    program = db.relationship("Program")
    department = db.relationship("Department")


class Student(TimestampMixin, db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)  # NULL until a login is created
    enrollment_no = db.Column(db.String(30), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255))
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"), nullable=False)

    user = db.relationship("User")
    batch = db.relationship("Batch", backref="students")


class Subject(TimestampMixin, db.Model):
    __tablename__ = "subjects"
    __table_args__ = (
        db.CheckConstraint("credits >= 0", name="credits_non_negative"),
        db.CheckConstraint("weekly_hours > 0", name="weekly_hours_positive"),
        db.CheckConstraint("lab_block_periods >= 1", name="lab_block_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(150), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    semester_no = db.Column(db.SmallInteger, nullable=False)
    credits = db.Column(db.SmallInteger, nullable=False)
    weekly_hours = db.Column(db.SmallInteger, nullable=False)
    class_type = enum_column(ClassType, nullable=False, default=ClassType.THEORY)
    # Consecutive periods one lab session occupies (default 2; ignored for theory).
    lab_block_periods = db.Column(db.SmallInteger, nullable=False, default=2)
    required_room_type = enum_column(RoomType, nullable=True)

    department = db.relationship("Department")
    required_equipment = db.relationship("Equipment", secondary=subject_equipment)


class TeachingAssignment(db.Model):
    """Faculty X teaches Subject Y to Batch Z in a term, N sessions per week.

    Extends the SRS SUBJECT->Faculty link, which cannot express per-batch teachers.
    """

    __tablename__ = "teaching_assignments"
    __table_args__ = (
        db.UniqueConstraint("term_id", "batch_id", "subject_id", name="uq_assignment_term_batch_subject"),
        db.CheckConstraint("sessions_per_week > 0", name="sessions_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey("academic_terms.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    sessions_per_week = db.Column(db.SmallInteger, nullable=False)

    term = db.relationship("AcademicTerm")
    batch = db.relationship("Batch")
    subject = db.relationship("Subject")
    faculty = db.relationship("Faculty")
