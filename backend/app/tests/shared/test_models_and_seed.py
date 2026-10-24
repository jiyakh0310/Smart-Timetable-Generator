"""Shared database design: constraints, seed data, config safety."""
from datetime import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import load_config
from app.extensions import db
from app.models import (
    Faculty,
    Room,
    RoomType,
    TeachingAssignment,
    TimeSlot,
    Timetable,
    TimetableEntry,
    User,
)
from app.seed import seed_demo_data


def test_health_endpoint_reports_database_ok(client, app):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "ok"


def test_seed_is_idempotent(app):
    first = seed_demo_data()
    second = seed_demo_data()
    assert first == second
    assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 11  # 1 admin + 6 faculty + 4 students
    assert db.session.scalar(db.select(db.func.count()).select_from(TeachingAssignment)) == 12
    assert db.session.scalar(db.select(db.func.count()).select_from(TimeSlot)) == 35


def test_user_email_must_be_unique(app):
    from app.tests.conftest import make_user

    make_user("dup@timetable.test")
    with pytest.raises(IntegrityError):
        make_user("dup@timetable.test")


def test_room_capacity_must_be_positive(app):
    db.session.add(Room(code="BAD", name="Bad", capacity=0, room_type=RoomType.CLASSROOM))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_time_slot_end_must_be_after_start(app):
    db.session.add(TimeSlot(day_of_week=0, period_no=1, start_time=time(11), end_time=time(10)))
    with pytest.raises(IntegrityError):
        db.session.commit()


def _timetable_with_entry(seeded_app):
    admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
    assignment = db.session.scalars(db.select(TeachingAssignment)).first()
    slots = db.session.scalars(db.select(TimeSlot).order_by(TimeSlot.id).limit(2)).all()
    rooms = db.session.scalars(db.select(Room).order_by(Room.id).limit(2)).all()
    timetable = Timetable(term_id=assignment.term_id, name="T1", version=1, generated_by=admin.id)
    db.session.add(timetable)
    db.session.flush()
    return timetable, assignment, slots, rooms


def _entry(timetable, assignment, room, slot, faculty_id=None, batch_id=None):
    return TimetableEntry(
        timetable_id=timetable.id,
        assignment_id=assignment.id,
        faculty_id=faculty_id or assignment.faculty_id,
        batch_id=batch_id or assignment.batch_id,
        room_id=room.id,
        time_slot_id=slot.id,
    )


def test_database_blocks_faculty_double_booking(app, seeded):
    timetable, assignment, slots, rooms = _timetable_with_entry(app)
    db.session.add(_entry(timetable, assignment, rooms[0], slots[0]))
    db.session.flush()
    other_batch = db.session.scalars(db.select(TeachingAssignment).where(TeachingAssignment.batch_id != assignment.batch_id)).first()
    # same faculty, same slot, different batch and room -> only the faculty rule is violated
    db.session.add(_entry(timetable, assignment, rooms[1], slots[0], batch_id=other_batch.batch_id))
    with pytest.raises(IntegrityError):
        db.session.flush()


def test_database_blocks_room_double_booking(app, seeded):
    timetable, assignment, slots, rooms = _timetable_with_entry(app)
    db.session.add(_entry(timetable, assignment, rooms[0], slots[0]))
    db.session.flush()
    other = db.session.scalars(
        db.select(TeachingAssignment).where(
            TeachingAssignment.batch_id != assignment.batch_id, TeachingAssignment.faculty_id != assignment.faculty_id
        )
    ).first()
    db.session.add(_entry(timetable, other, rooms[0], slots[0], faculty_id=other.faculty_id, batch_id=other.batch_id))
    with pytest.raises(IntegrityError):
        db.session.flush()


def test_database_blocks_batch_double_booking(app, seeded):
    timetable, assignment, slots, rooms = _timetable_with_entry(app)
    db.session.add(_entry(timetable, assignment, rooms[0], slots[0]))
    db.session.flush()
    other_faculty = db.session.scalars(db.select(Faculty).where(Faculty.id != assignment.faculty_id)).first()
    db.session.add(_entry(timetable, assignment, rooms[1], slots[0], faculty_id=other_faculty.id))
    with pytest.raises(IntegrityError):
        db.session.flush()


def test_same_resources_in_different_slots_are_allowed(app, seeded):
    timetable, assignment, slots, rooms = _timetable_with_entry(app)
    db.session.add_all([_entry(timetable, assignment, rooms[0], slots[0]), _entry(timetable, assignment, rooms[0], slots[1])])
    db.session.flush()


def test_production_config_rejects_placeholder_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "replace-with-a-long-random-value")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_config("development")


def test_config_rejects_short_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_config("production")


def test_database_settings_must_not_be_placeholders(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_USER", "replace-with-your-mysql-app-user")
    monkeypatch.setenv("DB_PASSWORD", "pw")
    monkeypatch.setenv("DB_NAME", "smart_timetable")
    with pytest.raises(RuntimeError, match="DB_USER"):
        load_config("development")


def test_mysql_url_is_built_from_parts_with_special_characters(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_USER", "app")
    monkeypatch.setenv("DB_PASSWORD", "p@ss:w/rd#1")
    monkeypatch.setenv("DB_NAME", "smart_timetable")
    uri = load_config("development")["SQLALCHEMY_DATABASE_URI"]
    assert uri.startswith("mysql+pymysql://app:")
    assert "p%40ss%3Aw%2Frd%231" in uri
    assert uri.endswith("/smart_timetable?charset=utf8mb4")


def test_real_configs_never_weaken_password_hashing(monkeypatch):
    """Only the testing config may override the hash method; development/production use scrypt."""
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    for env in ("development", "production"):
        assert "PASSWORD_HASH_METHOD" not in load_config(env)
    assert load_config("testing")["PASSWORD_HASH_METHOD"].startswith("pbkdf2")


def test_production_hashes_use_scrypt(monkeypatch, app):
    from app.tests.conftest import make_user

    app.config.pop("PASSWORD_HASH_METHOD")  # behave like a real config
    assert make_user("prod@timetable.test").password_hash.startswith("scrypt:")
