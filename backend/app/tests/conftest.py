import pytest

from app import create_app
from app.extensions import db
from app.models import Role, User
from app.seed import demo_password, seed_demo_data


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seeded(app):
    """Demo data loaded (admin, 6 faculty, 4 students, rooms, slots...)."""
    seed_demo_data()


def login(client, email, password=None):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password or demo_password()})


def auth_header(client, email):
    token = login(client, email).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, seeded):
    return auth_header(client, "admin@timetable.test")


@pytest.fixture()
def faculty_headers(client, seeded):
    return auth_header(client, "faculty1@timetable.test")


@pytest.fixture()
def student_headers(client, seeded):
    return auth_header(client, "student1@timetable.test")


def make_user(email, role=Role.STUDENT, password="Password123", active=True):
    user = User(email=email, full_name="Test User", role=role, is_active=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user
