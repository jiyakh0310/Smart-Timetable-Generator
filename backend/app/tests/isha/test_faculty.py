"""Isha - R2 Faculty management API (ISH-TC05 .. ISH-TC08 plus login linkage, role safety, deactivation, deletion)."""
import pytest

from app.extensions import db
from app.models import Department, Faculty, Role, TeachingAssignment, Timetable, TimetableEntry, User, Room, TimeSlot
from app.tests.conftest import login

URL = "/api/v1/faculty"
GOOD_PASSWORD = "Secure#Pass42"


def dept_id():
    return db.session.scalar(db.select(Department.id).where(Department.code == "CSE"))


def body(**over):
    data = {"name": "Dr. Priya Menon", "email": "priya.menon@college.test", "employee_code": "F100", "department_id": dept_id(),
            "designation": "Assistant Professor", "max_weekly_hours": 16, "password": GOOD_PASSWORD}
    data.update(over)
    return data


def post(client, headers, **over):
    return client.post(URL, json=body(**over), headers=headers)


def by_code(code):
    return db.session.scalar(db.select(Faculty).where(Faculty.employee_code == code))


def user_by_email(email):
    return db.session.scalar(db.select(User).filter_by(email=email))


# ---------------------------------------------------------------- permissions
class TestPermissions:
    def test_requires_login(self, client, seeded):
        for call in (lambda: client.get(URL), lambda: client.post(URL, json=body()), lambda: client.get(f"{URL}/1/availability")):
            assert call().status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_everything_is_admin_only_even_reading(self, client, request, who):
        headers = request.getfixturevalue(who)
        fid = by_code("F002").id
        assert client.get(URL, headers=headers).status_code == 403
        assert client.get(f"{URL}/{fid}", headers=headers).status_code == 403
        assert client.post(URL, json=body(), headers=headers).status_code == 403
        assert client.patch(f"{URL}/{fid}", json={"name": "Hacked"}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{fid}", headers=headers).status_code == 403
        assert client.post(f"{URL}/{fid}/reset-password", json={"password": GOOD_PASSWORD}, headers=headers).status_code == 403
        assert client.put(f"{URL}/{fid}/availability", json={"entries": []}, headers=headers).status_code == 403
        assert by_code("F002").user.full_name == "Dr. Meera Iyer"

    def test_a_faculty_member_cannot_edit_their_own_record_either(self, client, faculty_headers):
        own = by_code("F001").id
        assert client.patch(f"{URL}/{own}", json={"max_weekly_hours": 40}, headers=faculty_headers).status_code == 403
        assert by_code("F001").max_weekly_hours == 18


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_seed_faculty_with_usage_and_no_secrets(self, client, admin_headers):
        data = client.get(URL, headers=admin_headers).get_json()["data"]
        assert data["total"] == 6
        first = data["items"][0]
        assert (first["employee_code"], first["name"], first["email"], first["is_active"]) == ("F001", "Dr. Rakesh Sharma", "faculty1@timetable.test", True)
        assert first["department"]["code"] == "CSE" and first["max_weekly_hours"] == 18
        assert first["usage"] == {"teaching_assignments": 3, "timetable_entries": 0} and first["in_use"] is True
        assert first["availability"] == {"unavailable": 0, "preferred": 0}
        text = str(data)
        assert "password" not in text and "user_id" not in text

    def test_pagination_ordering_filters_and_search(self, client, admin_headers):
        p2 = client.get(f"{URL}?per_page=4&page=2", headers=admin_headers).get_json()["data"]
        assert [f["employee_code"] for f in p2["items"]] == ["F005", "F006"] and p2["pages"] == 2
        get = lambda qs: client.get(f"{URL}?{qs}", headers=admin_headers).get_json()["data"]["total"]
        assert get(f"department_id={dept_id()}") == 6 and get("department_id=999") == 0
        assert get("active=true") == 6 and get("active=false") == 0
        assert get("q=meera") == 1 and get("q=F00") == 6 and get("q=FACULTY3@") == 1 and get("q=nobody") == 0 and get("q=%25") == 0

    def test_active_filter_follows_deactivation(self, client, admin_headers):
        fid = by_code("F003").id
        client.patch(f"{URL}/{fid}", json={"is_active": False}, headers=admin_headers)
        get = lambda qs: client.get(f"{URL}?{qs}", headers=admin_headers).get_json()["data"]["total"]
        assert get("active=false") == 1 and get("active=true") == 5

    @pytest.mark.parametrize("qs", ["page=0", "per_page=101", "department_id=0", "department_id=x", "active=maybe"])
    def test_bad_query_values_are_400(self, client, admin_headers, qs):
        assert client.get(f"{URL}?{qs}", headers=admin_headers).status_code == 400

    def test_get_one_and_404(self, client, admin_headers):
        fid = by_code("F004").id
        assert client.get(f"{URL}/{fid}", headers=admin_headers).get_json()["data"]["name"] == "Dr. Neha Kapoor"
        assert client.get(f"{URL}/9999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create + login linkage
class TestCreate:
    def test_ISH_TC05_add_a_faculty_member_creates_a_linked_faculty_login(self, client, admin_headers):
        response = post(client, admin_headers)
        assert response.status_code == 201
        item = response.get_json()["data"]
        assert (item["employee_code"], item["name"], item["email"], item["designation"], item["max_weekly_hours"]) == ("F100", "Dr. Priya Menon", "priya.menon@college.test", "Assistant Professor", 16)
        assert item["is_active"] is True and item["in_use"] is False
        assert GOOD_PASSWORD not in response.get_data(as_text=True) and "password" not in str(item)
        user = user_by_email("priya.menon@college.test")
        assert user.role == Role.FACULTY and user.is_active is True
        assert by_code("F100").user_id == user.id  # linked 1:1

    def test_the_password_is_hashed_and_the_new_account_can_sign_in(self, client, admin_headers):
        post(client, admin_headers)
        user = user_by_email("priya.menon@college.test")
        assert GOOD_PASSWORD not in user.password_hash and user.check_password(GOOD_PASSWORD)
        response = login(client, "priya.menon@college.test", GOOD_PASSWORD)
        assert response.status_code == 200
        me = response.get_json()["data"]["user"]
        assert me["role"] == "faculty" and me["faculty"]["employee_code"] == "F100"

    def test_a_new_faculty_account_cannot_reach_admin_or_student_data(self, client, admin_headers):
        post(client, admin_headers)
        token = login(client, "priya.menon@college.test", GOOD_PASSWORD).get_json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/admin/summary", headers=headers).status_code == 403
        assert client.get("/api/v1/students", headers=headers).status_code == 403
        assert client.get(URL, headers=headers).status_code == 403

    def test_a_client_cannot_choose_the_role_or_link_an_existing_user(self, client, admin_headers):
        for extra in ({"role": "admin"}, {"role": "faculty"}, {"user_id": 1}, {"is_active": False}):
            response = post(client, admin_headers, **extra)
            assert response.status_code == 400, extra
            assert list(extra)[0] in response.get_json()["error"]["details"]
        assert user_by_email("priya.menon@college.test") is None  # nothing half-created
        assert User.query.filter_by(role=Role.ADMIN).count() == 1

    def test_values_are_normalised(self, client, admin_headers):
        item = post(client, admin_headers, name="  Dr.   Priya  Menon ", email=" Priya.Menon@College.TEST ", employee_code=" f-100 ", designation="").get_json()["data"]
        assert (item["name"], item["email"], item["employee_code"], item["designation"]) == ("Dr. Priya Menon", "priya.menon@college.test", "F-100", None)

    def test_weekly_hours_default_to_18(self, client, admin_headers):
        data = body()
        del data["max_weekly_hours"]
        assert client.post(URL, json=data, headers=admin_headers).get_json()["data"]["max_weekly_hours"] == 18

    def test_ISH_TC08_missing_details_are_reported_and_nothing_saved(self, client, admin_headers):
        users_before, faculty_before = User.query.count(), Faculty.query.count()
        data = body()
        del data["employee_code"]
        response = client.post(URL, json=data, headers=admin_headers)
        assert response.status_code == 400 and response.get_json()["error"]["details"] == {"employee_code": "This field is required."}
        details = client.post(URL, json={}, headers=admin_headers).get_json()["error"]["details"]
        assert set(details) == {"name", "email", "employee_code", "department_id", "password"}
        assert (User.query.count(), Faculty.query.count()) == (users_before, faculty_before)

    @pytest.mark.parametrize(
        "field, value",
        [("name", "x"), ("name", "n" * 121), ("email", "nope"), ("email", "a@b"), ("employee_code", "bad code!"), ("employee_code", "A" * 31),
         ("department_id", 9999), ("department_id", "x"), ("designation", "d" * 81), ("max_weekly_hours", 0), ("max_weekly_hours", 41),
         ("max_weekly_hours", "16"), ("max_weekly_hours", True)],
    )
    def test_invalid_values_are_400_with_the_offending_field(self, client, admin_headers, field, value):
        response = post(client, admin_headers, **{field: value})
        assert response.status_code == 400 and field in response.get_json()["error"]["details"]

    @pytest.mark.parametrize("password", ["short1", "alllettersonly", "1234567890", "a" * 129 + "1", "", None])
    def test_weak_or_missing_passwords_are_rejected(self, client, admin_headers, password):
        response = post(client, admin_headers, password=password)
        assert response.status_code == 400 and "password" in response.get_json()["error"]["details"]
        assert user_by_email("priya.menon@college.test") is None

    @pytest.mark.parametrize(
        "identity",
        [{"email": "priya2024@college.test"}, {"employee_code": "F100-STAFF-001"}, {"name": "Priya Menon 2024"}],
        ids=["email", "employee_code", "name"],
    )
    def test_password_may_not_equal_the_email_code_or_name(self, client, admin_headers, identity):
        """Each value below is long enough and has a letter and a digit, so only the 'same as identity' rule can reject it."""
        same_as_identity = next(iter(identity.values()))
        response = post(client, admin_headers, **identity, password=same_as_identity)
        assert response.status_code == 400
        assert "same as" in response.get_json()["error"]["details"]["password"]
        # control: the identical request with a different password is accepted
        assert post(client, admin_headers, **identity, password=GOOD_PASSWORD).status_code == 201

    def test_unknown_fields_and_non_json(self, client, admin_headers):
        assert post(client, admin_headers, colour="red").status_code == 400
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_duplicate_employee_code_is_409_even_with_different_case(self, client, admin_headers):
        for code in ("F001", " f001 "):
            response = post(client, admin_headers, employee_code=code)
            assert response.status_code == 409 and response.get_json()["error"]["code"] == "duplicate_faculty"
            assert "employee_code" in response.get_json()["error"]["details"]
        assert Faculty.query.count() == 6

    def test_duplicate_email_is_409_against_any_account_including_admin_and_students(self, client, admin_headers):
        for email in ("faculty1@timetable.test", "FACULTY1@timetable.test", "admin@timetable.test", "student1@timetable.test"):
            response = post(client, admin_headers, email=email)
            assert response.status_code == 409 and "email" in response.get_json()["error"]["details"], email
        assert User.query.count() == 11


# ---------------------------------------------------------------- update / deactivate / reset password
class TestUpdate:
    def test_ISH_TC06_update_email_and_details(self, client, admin_headers):
        fid = by_code("F002").id
        item = client.patch(f"{URL}/{fid}", json={"email": "meera.iyer@college.test", "designation": "Professor", "max_weekly_hours": 20}, headers=admin_headers).get_json()["data"]
        assert (item["email"], item["designation"], item["max_weekly_hours"]) == ("meera.iyer@college.test", "Professor", 20)
        assert login(client, "meera.iyer@college.test", "Demo@12345").status_code == 200  # same password, new email
        assert login(client, "faculty2@timetable.test", "Demo@12345").status_code == 401

    def test_keeping_your_own_email_and_code_is_not_a_duplicate(self, client, admin_headers):
        fid = by_code("F002").id
        assert client.patch(f"{URL}/{fid}", json={"email": "FACULTY2@timetable.test", "employee_code": "f002", "name": "Dr. Meera I."}, headers=admin_headers).status_code == 200

    def test_changing_to_another_accounts_email_or_code_is_409(self, client, admin_headers):
        fid = by_code("F002").id
        assert client.patch(f"{URL}/{fid}", json={"email": "admin@timetable.test"}, headers=admin_headers).status_code == 409
        assert client.patch(f"{URL}/{fid}", json={"email": "faculty3@timetable.test"}, headers=admin_headers).status_code == 409
        assert client.patch(f"{URL}/{fid}", json={"employee_code": "F003"}, headers=admin_headers).status_code == 409
        assert by_code("F002").user.email == "faculty2@timetable.test"

    def test_role_and_login_link_cannot_be_changed(self, client, admin_headers):
        fid = by_code("F002").id
        for extra in ({"role": "admin"}, {"user_id": 1}, {"password": GOOD_PASSWORD}):
            assert client.patch(f"{URL}/{fid}", json=extra, headers=admin_headers).status_code == 400, extra
        assert by_code("F002").user.role == Role.FACULTY

    def test_update_validation(self, client, admin_headers):
        fid = by_code("F002").id
        assert client.patch(f"{URL}/{fid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{fid}", json={"max_weekly_hours": 0}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{fid}", json={"department_id": 999}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{fid}", json={"is_active": "no"}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/9999", json={"name": "Valid Name"}, headers=admin_headers).status_code == 404

    def test_deactivating_blocks_login_and_existing_tokens_but_keeps_every_record(self, client, admin_headers, faculty_headers):
        fid = by_code("F001").id
        assert client.get("/api/v1/auth/me", headers=faculty_headers).status_code == 200
        item = client.patch(f"{URL}/{fid}", json={"is_active": False}, headers=admin_headers).get_json()["data"]
        assert item["is_active"] is False and item["usage"]["teaching_assignments"] == 3
        assert login(client, "faculty1@timetable.test").status_code == 401
        assert client.get("/api/v1/auth/me", headers=faculty_headers).status_code == 401
        assert TeachingAssignment.query.filter_by(faculty_id=fid).count() == 3
        client.patch(f"{URL}/{fid}", json={"is_active": True}, headers=admin_headers)
        assert login(client, "faculty1@timetable.test").status_code == 200

    def test_reset_password(self, client, admin_headers):
        fid = by_code("F002").id
        response = client.post(f"{URL}/{fid}/reset-password", json={"password": GOOD_PASSWORD}, headers=admin_headers)
        assert response.status_code == 200 and GOOD_PASSWORD not in response.get_data(as_text=True)
        assert login(client, "faculty2@timetable.test", GOOD_PASSWORD).status_code == 200
        assert login(client, "faculty2@timetable.test", "Demo@12345").status_code == 401
        assert user_by_email("faculty2@timetable.test").password_hash.startswith(("scrypt:", "pbkdf2:"))

    @pytest.mark.parametrize("payload", [{}, {"password": "short1"}, {"password": "onlyletters"}, {"password": "faculty2@timetable.test"}, {"password": GOOD_PASSWORD, "role": "admin"}])
    def test_reset_password_validation(self, client, admin_headers, payload):
        fid = by_code("F002").id
        assert client.post(f"{URL}/{fid}/reset-password", json=payload, headers=admin_headers).status_code == 400
        assert login(client, "faculty2@timetable.test", "Demo@12345").status_code == 200  # unchanged

    def test_reset_password_404(self, client, admin_headers):
        assert client.post(f"{URL}/9999/reset-password", json={"password": GOOD_PASSWORD}, headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- delete
class TestDelete:
    def test_delete_an_unused_faculty_member_also_removes_their_login(self, client, admin_headers):
        fid = post(client, admin_headers).get_json()["data"]["id"]
        assert client.delete(f"{URL}/{fid}", headers=admin_headers).status_code == 200
        assert db.session.get(Faculty, fid) is None
        assert user_by_email("priya.menon@college.test") is None
        assert login(client, "priya.menon@college.test", GOOD_PASSWORD).status_code == 401
        assert User.query.count() == 11  # nobody else touched
        assert post(client, admin_headers).status_code == 201  # code and email can be reused

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/9999", headers=admin_headers).status_code == 404

    def test_faculty_with_teaching_assignments_cannot_be_deleted(self, client, admin_headers):
        fid = by_code("F001").id
        response = client.delete(f"{URL}/{fid}", headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "faculty_in_use"
        assert "3 teaching assignments" in error["message"] and "Deactivate" in error["message"]
        assert by_code("F001") is not None and user_by_email("faculty1@timetable.test") is not None
        assert TeachingAssignment.query.filter_by(faculty_id=fid).count() == 3

    def test_faculty_in_a_timetable_cannot_be_deleted(self, client, admin_headers):
        fac = by_code("F005")
        assignment = db.session.scalar(db.select(TeachingAssignment).where(TeachingAssignment.faculty_id == fac.id))
        admin = user_by_email("admin@timetable.test")
        timetable = Timetable(term_id=assignment.term_id, name="T", version=1, generated_by=admin.id)
        db.session.add(timetable)
        db.session.flush()
        db.session.add(TimetableEntry(timetable_id=timetable.id, assignment_id=assignment.id, faculty_id=fac.id, batch_id=assignment.batch_id,
                                      room_id=db.session.scalar(db.select(Room.id)), time_slot_id=db.session.scalar(db.select(TimeSlot.id))))
        db.session.commit()
        message = client.delete(f"{URL}/{fac.id}", headers=admin_headers).get_json()["error"]["message"]
        assert "1 teaching assignment" in message and "1 timetable entry" in message


def test_a_whitespace_only_designation_is_treated_as_empty_not_as_an_error(client, admin_headers):
    """Regression: optional text fields share one helper (fields.optional_text)."""
    response = client.post(URL, json=body(designation="   "), headers=admin_headers)
    assert response.status_code == 201 and response.get_json()["data"]["designation"] is None
    fid = response.get_json()["data"]["id"]
    assert client.patch(f"{URL}/{fid}", json={"designation": "  Lecturer  "}, headers=admin_headers).get_json()["data"]["designation"] == "Lecturer"
    assert client.patch(f"{URL}/{fid}", json={"designation": "   "}, headers=admin_headers).get_json()["data"]["designation"] is None
