"""DEVELOPMENT-ONLY demo data. Safe to run repeatedly (get-or-create by unique keys).

Demo accounts (all share DEMO_PASSWORD from .env, default below):
  admin@timetable.test      Admin
  faculty1..6@timetable.test Faculty
  student1..4@timetable.test Student
"""
import os
from datetime import time

from app.extensions import db
from app.models import (
    AcademicTerm,
    Batch,
    ClassType,
    Department,
    Faculty,
    Program,
    Role,
    Room,
    RoomType,
    SlotType,
    Student,
    Subject,
    SystemSetting,
    TeachingAssignment,
    TermType,
    TimeSlot,
    User,
)

DEFAULT_DEMO_PASSWORD = "Demo@12345"  # development only; override with DEMO_PASSWORD in .env


def demo_password() -> str:
    return os.getenv("DEMO_PASSWORD") or DEFAULT_DEMO_PASSWORD


def _get_or_create(model, lookup: dict, defaults: dict | None = None):
    instance = db.session.scalar(db.select(model).filter_by(**lookup))
    if instance is None:
        instance = model(**lookup, **(defaults or {}))
        db.session.add(instance)
        db.session.flush()
    return instance


def _user(email: str, name: str, role: Role) -> User:
    user = db.session.scalar(db.select(User).filter_by(email=email))
    if user is None:
        user = User(email=email, full_name=name, role=role)
        user.set_password(demo_password())
        db.session.add(user)
        db.session.flush()
    return user


def seed_demo_data() -> dict:
    # --- accounts --------------------------------------------------------
    _user("admin@timetable.test", "Dr. Anita Verma (Admin)", Role.ADMIN)

    # --- academic structure ---------------------------------------------
    cse = _get_or_create(Department, {"code": "CSE"}, {"name": "Computer Science & Engineering"})
    btech_cse = _get_or_create(Program, {"department_id": cse.id, "name": "B.Tech CSE"}, {"duration_semesters": 8})
    term = _get_or_create(
        AcademicTerm,
        {"name": "2026-27 Odd"},
        {"academic_year": "2026-27", "term_type": TermType.ODD, "is_active": True},
    )

    # --- faculty ---------------------------------------------------------
    faculty_rows = [
        ("faculty1", "Dr. Rakesh Sharma", "F001", "Professor"),
        ("faculty2", "Dr. Meera Iyer", "F002", "Associate Professor"),
        ("faculty3", "Prof. Sanjay Gupta", "F003", "Assistant Professor"),
        ("faculty4", "Dr. Neha Kapoor", "F004", "Associate Professor"),
        ("faculty5", "Prof. Arjun Mehta", "F005", "Assistant Professor"),
        ("faculty6", "Dr. Kavita Rao", "F006", "Professor"),
    ]
    faculty = []
    for login, name, code, designation in faculty_rows:
        user = _user(f"{login}@timetable.test", name, Role.FACULTY)
        faculty.append(
            _get_or_create(
                Faculty,
                {"user_id": user.id},
                {"employee_code": code, "department_id": cse.id, "designation": designation, "max_weekly_hours": 18},
            )
        )

    # --- batches and students -------------------------------------------
    batch_a = _get_or_create(
        Batch,
        {"program_id": btech_cse.id, "semester_no": 3, "section": "A"},
        {"department_id": cse.id, "name": "CSE Sem 3 - A", "strength": 58},
    )
    batch_b = _get_or_create(
        Batch,
        {"program_id": btech_cse.id, "semester_no": 3, "section": "B"},
        {"department_id": cse.id, "name": "CSE Sem 3 - B", "strength": 42},
    )
    student_rows = [
        ("student1", "Aarav Singh", "CSE23001", batch_a),
        ("student2", "Diya Patel", "CSE23002", batch_a),
        ("student3", "Rohan Das", "CSE23041", batch_b),
        ("student4", "Isha Nair", "CSE23042", batch_b),
    ]
    for login, name, enrollment, batch in student_rows:
        email = f"{login}@timetable.test"
        user = _user(email, name, Role.STUDENT)
        _get_or_create(Student, {"enrollment_no": enrollment}, {"user_id": user.id, "name": name, "email": email, "batch_id": batch.id})

    # --- subjects (weekly_hours = hours across the week) ----------------
    subject_rows = [
        # code, name, credits, weekly_hours, type, room type
        ("CS301", "Data Structures", 4, 4, ClassType.THEORY, RoomType.CLASSROOM),
        ("CS302", "Database Management Systems", 4, 4, ClassType.THEORY, RoomType.CLASSROOM),
        ("CS303", "Operating Systems", 3, 3, ClassType.THEORY, RoomType.CLASSROOM),
        ("MA301", "Discrete Mathematics", 3, 3, ClassType.THEORY, RoomType.CLASSROOM),
        ("CS351", "Data Structures Lab", 2, 2, ClassType.LAB, RoomType.LAB),
        ("CS352", "DBMS Lab", 2, 2, ClassType.LAB, RoomType.LAB),
    ]
    subjects = {}
    for code, name, credits, hours, class_type, room_type in subject_rows:
        subjects[code] = _get_or_create(
            Subject,
            {"code": code},
            {
                "name": name,
                "department_id": cse.id,
                "semester_no": 3,
                "credits": credits,
                "weekly_hours": hours,
                "class_type": class_type,
                "lab_block_periods": 2,
                "required_room_type": room_type,
            },
        )

    # --- teaching assignments (sessions_per_week: lab = hours / block) --
    plan = [  # subject, faculty index for batch A, for batch B
        ("CS301", 0, 0),
        ("CS302", 1, 3),
        ("CS303", 2, 4),
        ("MA301", 5, 5),
        ("CS351", 0, 2),
        ("CS352", 1, 3),
    ]
    for code, fac_a, fac_b in plan:
        subject = subjects[code]
        sessions = subject.weekly_hours // subject.lab_block_periods if subject.class_type == ClassType.LAB else subject.weekly_hours
        for batch, fac_index in ((batch_a, fac_a), (batch_b, fac_b)):
            _get_or_create(
                TeachingAssignment,
                {"term_id": term.id, "batch_id": batch.id, "subject_id": subject.id},
                {"faculty_id": faculty[fac_index].id, "sessions_per_week": sessions},
            )

    # --- rooms -----------------------------------------------------------
    room_rows = [
        ("R101", "Room 101", "Main Block, Floor 1", 40, RoomType.CLASSROOM, None),
        ("R102", "Room 102", "Main Block, Floor 1", 45, RoomType.CLASSROOM, None),
        ("R201", "Room 201", "Main Block, Floor 2", 60, RoomType.CLASSROOM, None),
        ("R202", "Room 202", "Main Block, Floor 2", 70, RoomType.CLASSROOM, None),
        ("LAB1", "Computer Lab 1", "IT Block, Floor 1", 60, RoomType.LAB, "Computer"),
        ("LAB2", "Computer Lab 2", "IT Block, Floor 1", 45, RoomType.LAB, "Computer"),
        ("SEM1", "Seminar Hall", "Admin Block", 120, RoomType.SEMINAR_HALL, None),
    ]
    for code, name, location, capacity, room_type, lab_type in room_rows:
        _get_or_create(
            Room,
            {"code": code},
            {"name": name, "location": location, "capacity": capacity, "room_type": room_type, "lab_type": lab_type},
        )

    # --- time slots: Mon-Fri, 6 periods + lunch break -------------------
    periods = [
        (1, time(9, 0), time(10, 0), SlotType.CLASS),
        (2, time(10, 0), time(11, 0), SlotType.CLASS),
        (3, time(11, 0), time(12, 0), SlotType.CLASS),
        (4, time(12, 0), time(13, 0), SlotType.BREAK),
        (5, time(13, 0), time(14, 0), SlotType.CLASS),
        (6, time(14, 0), time(15, 0), SlotType.CLASS),
        (7, time(15, 0), time(16, 0), SlotType.CLASS),
    ]
    for day in range(5):
        for period_no, start, end, slot_type in periods:
            _get_or_create(
                TimeSlot,
                {"day_of_week": day, "period_no": period_no},
                {"start_time": start, "end_time": end, "slot_type": slot_type},
            )

    # --- settings --------------------------------------------------------
    _get_or_create(SystemSetting, {"key": "max_classes_per_day"}, {"value": "6", "description": "Maximum classes per batch per day"})
    _get_or_create(SystemSetting, {"key": "max_faculty_hours_per_week"}, {"value": "18", "description": "Default weekly teaching hour limit"})

    db.session.commit()
    return {
        "users": db.session.scalar(db.select(db.func.count()).select_from(User)),
        "faculty": len(faculty),
        "batches": 2,
        "subjects": len(subjects),
        "rooms": len(room_rows),
        "time_slots": 5 * len(periods),
    }
