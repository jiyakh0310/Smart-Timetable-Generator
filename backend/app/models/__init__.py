"""Single, shared set of database models. Importing this package registers every table."""
from app.models.user import Role, User
from app.models.infrastructure import Equipment, Room, RoomType, SlotType, TimeSlot, room_equipment, subject_equipment
from app.models.academic import (
    AcademicTerm,
    Batch,
    ClassType,
    Department,
    Program,
    Student,
    Subject,
    TeachingAssignment,
    TermType,
)
from app.models.faculty import AvailabilityStatus, Faculty, FacultyAvailability
from app.models.timetable import Timetable, TimetableEntry, TimetableStatus, UnscheduledItem
from app.models.communication import Announcement, AnnouncementStatus, Audience, SystemSetting

__all__ = [name for name in dir() if not name.startswith("_")]
