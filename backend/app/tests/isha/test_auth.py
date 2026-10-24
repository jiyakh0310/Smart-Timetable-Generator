"""Isha - R1 Login and Role-Based Access (test cases ISH-TC01 .. ISH-TC04 plus extras)."""
from app.models import Role, User
from app.tests.conftest import auth_header, login, make_user


def test_ISH_TC01_login_with_valid_credentials(client, app):
    make_user("ok@timetable.test", Role.ADMIN)
    response = login(client, "ok@timetable.test", "Password123")
    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["token"]
    assert body["data"]["user"]["role"] == "admin"
    assert "password" not in str(body).lower().replace("password_hash", "")  # no hash/password leaked
    assert "password_hash" not in body["data"]["user"]


def test_ISH_TC02_login_with_wrong_password(client, app):
    make_user("ok@timetable.test")
    response = login(client, "ok@timetable.test", "WrongPassword")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_gets_same_error_as_wrong_password(client, app):
    make_user("ok@timetable.test")
    wrong_pw = login(client, "ok@timetable.test", "nope").get_json()
    unknown = login(client, "nobody@timetable.test", "nope").get_json()
    assert wrong_pw == unknown


def test_ISH_TC03_login_with_empty_fields(client, app):
    response = client.post("/api/v1/auth/login", json={"email": "", "password": ""})
    body = response.get_json()
    assert response.status_code == 400
    assert body["error"]["code"] == "validation_error"
    assert set(body["error"]["details"]) == {"email", "password"}


def test_login_without_json_body(client, app):
    response = client.post("/api/v1/auth/login", data="not json")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_json"


def test_ISH_TC04_student_cannot_access_admin_endpoint(client, student_headers):
    response = client.get("/api/v1/admin/summary", headers=student_headers)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_faculty_cannot_access_admin_endpoint(client, faculty_headers):
    assert client.get("/api/v1/admin/summary", headers=faculty_headers).status_code == 403


def test_admin_can_access_admin_endpoint(client, admin_headers):
    response = client.get("/api/v1/admin/summary", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["counts"]["faculty"] == 6
    assert data["timetables"]["total"] == 0


def test_protected_route_without_token_is_401(client, app):
    response = client.get("/api/v1/admin/summary")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_garbage_token_is_401(client, app):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401


def test_disabled_account_cannot_login(client, app):
    make_user("off@timetable.test", active=False)
    assert login(client, "off@timetable.test", "Password123").status_code == 401


def test_token_stops_working_when_account_is_disabled(client, app):
    user = make_user("soon@timetable.test", Role.ADMIN)
    token = login(client, "soon@timetable.test", "Password123").get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    user.is_active = False
    from app.extensions import db

    db.session.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_email_login_is_case_insensitive(client, app):
    make_user("mixed@timetable.test")
    assert login(client, "  MIXED@Timetable.test ", "Password123").status_code == 200


def test_me_returns_role_specific_profile(client, seeded, faculty_headers, student_headers):
    faculty = client.get("/api/v1/auth/me", headers=faculty_headers).get_json()["data"]
    assert faculty["role"] == "faculty"
    assert faculty["faculty"]["employee_code"] == "F001"

    student = client.get("/api/v1/auth/me", headers=student_headers).get_json()["data"]
    assert student["role"] == "student"
    assert student["student"]["batch"] == "CSE Sem 3 - A"
    assert student["student"]["batch_strength"] == 58


def test_change_password_flow(client, app):
    make_user("pw@timetable.test")
    token = login(client, "pw@timetable.test", "Password123").get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    wrong = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "bad", "new_password": "NewPassword9"})
    assert wrong.status_code == 400

    short = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "Password123", "new_password": "short"})
    assert short.status_code == 400

    same = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "Password123", "new_password": "Password123"})
    assert same.status_code == 400

    ok = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "Password123", "new_password": "NewPassword9"})
    assert ok.status_code == 200
    assert login(client, "pw@timetable.test", "Password123").status_code == 401
    assert login(client, "pw@timetable.test", "NewPassword9").status_code == 200


def test_passwords_are_hashed_not_stored_in_plain_text(app):
    user = make_user("hash@timetable.test", password="Password123")
    stored = User.query.get(user.id).password_hash
    assert "Password123" not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))
    assert user.check_password("Password123") and not user.check_password("password123")


def test_unknown_route_uses_json_error_envelope(client, app):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["success"] is False
