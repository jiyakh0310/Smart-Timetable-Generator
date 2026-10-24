"""Diya - R3 Student management API (DIY-TC01 .. DIY-TC03, batch assignment, capacity, privacy, safe deletion)."""
import pytest

from app.extensions import db
from app.models import Batch, Program, Student, User
from app.tests.conftest import auth_header, login

URL = "/api/v1/students"
BATCHES = "/api/v1/batches"


def batch_id(name="CSE Sem 3 - A"):
    return db.session.scalar(db.select(Batch.id).where(Batch.name == name))


def student_by(number):
    return db.session.scalar(db.select(Student).where(Student.enrollment_no == number))


def body(**over):
    data = {"enrollment_no": "CSE23100", "name": "Meera Joshi", "email": "meera@college.test", "batch_id": batch_id()}
    data.update(over)
    return data


def post(client, headers, **over):
    return client.post(URL, json=body(**over), headers=headers)


def strength_of(client, headers, bid):
    return client.get(f"{BATCHES}/{bid}", headers=headers).get_json()["data"]


def small_batch(client, headers, strength=2, section="Z"):
    program = db.session.scalar(db.select(Program.id))
    return client.post(BATCHES, json={"program_id": program, "semester_no": 5, "section": section, "strength": strength}, headers=headers).get_json()["data"]["id"]


# ---------------------------------------------------------------- permissions & privacy
class TestPermissions:
    def test_requires_login(self, client, seeded):
        assert client.get(URL).status_code == 401
        assert client.post(URL, json=body()).status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_student_records_are_admin_only_even_for_reading(self, client, request, who):
        headers = request.getfixturevalue(who)
        sid = student_by("CSE23001").id
        assert client.get(URL, headers=headers).status_code == 403
        assert client.get(f"{URL}/{sid}", headers=headers).status_code == 403
        assert client.post(URL, json=body(), headers=headers).status_code == 403
        assert client.patch(f"{URL}/{sid}", json={"name": "Hacked"}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{sid}", headers=headers).status_code == 403
        assert student_by("CSE23001").name == "Aarav Singh"
        assert "email" not in client.get(URL, headers=headers).get_data(as_text=True)  # nothing leaks in the refusal

    def test_a_student_still_sees_only_their_own_profile_via_me(self, client, student_headers):
        me = client.get("/api/v1/auth/me", headers=student_headers).get_json()["data"]
        assert me["student"]["enrollment_no"] == "CSE23001" and me["student"]["batch_strength"] == 58


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_seed_students_in_enrollment_order(self, client, admin_headers):
        data = client.get(URL, headers=admin_headers).get_json()["data"]
        assert data["total"] == 4
        assert [s["enrollment_no"] for s in data["items"]] == ["CSE23001", "CSE23002", "CSE23041", "CSE23042"]
        first = data["items"][0]
        assert first["name"] == "Aarav Singh" and first["has_login"] is True
        assert first["batch"] == {"id": batch_id(), "name": "CSE Sem 3 - A", "semester_no": 3, "section": "A", "department_code": "CSE"}
        assert "user_id" not in first and "password_hash" not in str(first)

    def test_pagination(self, client, admin_headers):
        p2 = client.get(f"{URL}?per_page=3&page=2", headers=admin_headers).get_json()["data"]
        assert (p2["total"], p2["pages"], [s["enrollment_no"] for s in p2["items"]]) == (4, 2, ["CSE23042"])

    def test_filters(self, client, admin_headers):
        get = lambda qs: client.get(f"{URL}?{qs}", headers=admin_headers).get_json()["data"]["total"]
        assert get(f"batch_id={batch_id()}") == 2 and get(f"batch_id={batch_id('CSE Sem 3 - B')}") == 2 and get("batch_id=999") == 0
        assert get("semester_no=3") == 4 and get("semester_no=4") == 0
        assert get("department_id=1") == 4 and get("department_id=2") == 0

    def test_search_by_number_name_and_email_case_insensitive(self, client, admin_headers):
        get = lambda q: [s["enrollment_no"] for s in client.get(f"{URL}?q={q}", headers=admin_headers).get_json()["data"]["items"]]
        assert get("cse2304") == ["CSE23041", "CSE23042"]
        assert get("AARAV") == ["CSE23001"]
        assert get("student3@") == ["CSE23041"]
        assert get("nobody") == [] and get("%25") == []

    @pytest.mark.parametrize("qs", ["page=0", "per_page=500", "batch_id=0", "semester_no=99", "department_id=x"])
    def test_bad_query_values_are_400(self, client, admin_headers, qs):
        assert client.get(f"{URL}?{qs}", headers=admin_headers).status_code == 400

    def test_get_one_and_404(self, client, admin_headers):
        sid = student_by("CSE23042").id
        assert client.get(f"{URL}/{sid}", headers=admin_headers).get_json()["data"]["name"] == "Isha Nair"
        assert client.get(f"{URL}/9999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create
class TestCreate:
    def test_DIY_TC01_add_a_student_to_a_batch(self, client, admin_headers):
        response = post(client, admin_headers)
        assert response.status_code == 201
        item = response.get_json()["data"]
        assert (item["enrollment_no"], item["name"], item["email"], item["has_login"]) == ("CSE23100", "Meera Joshi", "meera@college.test", False)
        assert item["batch"]["name"] == "CSE Sem 3 - A"
        assert strength_of(client, admin_headers, batch_id())["student_count"] == 3  # batch count follows the record
        assert strength_of(client, admin_headers, batch_id())["strength"] == 58  # stored strength is not silently changed

    def test_values_are_normalised(self, client, admin_headers):
        item = post(client, admin_headers, enrollment_no=" cse23-101 ", name="  Meera   Joshi ", email=" Meera.J@College.TEST ").get_json()["data"]
        assert (item["enrollment_no"], item["name"], item["email"]) == ("CSE23-101", "Meera Joshi", "meera.j@college.test")

    def test_email_is_optional(self, client, admin_headers):
        assert post(client, admin_headers, email=None).get_json()["data"]["email"] is None
        assert post(client, admin_headers, enrollment_no="CSE23102", email="").get_json()["data"]["email"] is None

    def test_DIY_TC03_missing_enrollment_number_is_rejected_and_nothing_saved(self, client, admin_headers):
        data = body()
        del data["enrollment_no"]
        response = client.post(URL, json=data, headers=admin_headers)
        assert response.status_code == 400 and response.get_json()["error"]["details"] == {"enrollment_no": "This field is required."}
        assert Student.query.count() == 4

    def test_all_missing_required_fields_are_reported(self, client, admin_headers):
        details = client.post(URL, json={}, headers=admin_headers).get_json()["error"]["details"]
        assert set(details) == {"enrollment_no", "name", "batch_id"}

    @pytest.mark.parametrize(
        "field, value",
        [("enrollment_no", "bad number!"), ("enrollment_no", "A" * 31), ("enrollment_no", 5), ("name", "x"), ("name", "n" * 121), ("name", 5),
         ("email", "not-an-email"), ("email", "a@b"), ("email", "x" * 251 + "@a.co"), ("batch_id", 9999), ("batch_id", "x"), ("batch_id", True)],
    )
    def test_invalid_values_are_400_with_the_offending_field(self, client, admin_headers, field, value):
        response = post(client, admin_headers, **{field: value})
        assert response.status_code == 400 and field in response.get_json()["error"]["details"]

    def test_unknown_fields_including_login_link_are_rejected(self, client, admin_headers):
        assert post(client, admin_headers, user_id=1).status_code == 400
        assert post(client, admin_headers, colour="red").status_code == 400
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_duplicate_enrollment_number_is_409_even_with_different_case(self, client, admin_headers):
        for number in ("CSE23001", " cse23001 "):
            response = post(client, admin_headers, enrollment_no=number)
            assert response.status_code == 409 and response.get_json()["error"]["code"] == "duplicate_student"
            assert "enrollment_no" in response.get_json()["error"]["details"]
        assert Student.query.count() == 4

    def test_duplicate_email_is_409(self, client, admin_headers):
        response = post(client, admin_headers, email="STUDENT1@timetable.test")
        assert response.status_code == 409 and "email" in response.get_json()["error"]["details"]


# ---------------------------------------------------------------- batch capacity (strength accuracy)
class TestCapacity:
    def test_a_full_batch_rejects_another_student_until_strength_is_raised(self, client, admin_headers):
        bid = small_batch(client, admin_headers, strength=2)
        assert post(client, admin_headers, enrollment_no="F1", email=None, batch_id=bid).status_code == 201
        assert post(client, admin_headers, enrollment_no="F2", email=None, batch_id=bid).status_code == 201
        response = post(client, admin_headers, enrollment_no="F3", email=None, batch_id=bid)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "batch_full" and "batch_id" in error["details"]
        assert "2 of 2" in error["message"] and student_by("F3") is None
        client.patch(f"{BATCHES}/{bid}", json={"strength": 3}, headers=admin_headers)
        assert post(client, admin_headers, enrollment_no="F3", email=None, batch_id=bid).status_code == 201
        assert strength_of(client, admin_headers, bid)["seats_left"] == 0

    def test_moving_a_student_updates_both_batch_counts(self, client, admin_headers):
        target = small_batch(client, admin_headers, strength=5)
        sid = student_by("CSE23001").id
        response = client.patch(f"{URL}/{sid}", json={"batch_id": target}, headers=admin_headers)
        assert response.status_code == 200 and response.get_json()["data"]["batch"]["id"] == target
        assert strength_of(client, admin_headers, target)["student_count"] == 1
        assert strength_of(client, admin_headers, batch_id())["student_count"] == 1

    def test_moving_into_a_full_batch_is_409_and_the_student_stays_put(self, client, admin_headers):
        target = small_batch(client, admin_headers, strength=1)
        post(client, admin_headers, enrollment_no="F1", email=None, batch_id=target)
        sid = student_by("CSE23001").id
        response = client.patch(f"{URL}/{sid}", json={"batch_id": target}, headers=admin_headers)
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "batch_full"
        assert student_by("CSE23001").batch_id == batch_id()

    def test_a_student_in_an_over_full_batch_can_still_be_edited_without_moving(self, client, admin_headers):
        """Old data may already exceed strength; editing a name must not be blocked by the capacity rule."""
        db.session.get(Batch, batch_id()).strength = 2
        db.session.add(Student(enrollment_no="OVER1", name="Over Full", batch_id=batch_id()))
        db.session.commit()
        sid = student_by("OVER1").id
        assert client.patch(f"{URL}/{sid}", json={"name": "Over Full Renamed"}, headers=admin_headers).status_code == 200


# ---------------------------------------------------------------- update
class TestUpdate:
    def test_DIY_TC02_update_email_and_batch(self, client, admin_headers):
        sid = student_by("CSE23001").id
        item = client.patch(f"{URL}/{sid}", json={"email": "new.address@college.test", "batch_id": batch_id("CSE Sem 3 - B")}, headers=admin_headers).get_json()["data"]
        assert item["email"] == "new.address@college.test" and item["batch"]["section"] == "B"
        assert student_by("CSE23001").batch_id == batch_id("CSE Sem 3 - B")

    def test_keeping_your_own_number_and_email_is_not_a_duplicate(self, client, admin_headers):
        sid = student_by("CSE23001").id
        assert client.patch(f"{URL}/{sid}", json={"enrollment_no": "cse23001", "email": "student1@timetable.test", "name": "Aarav S"}, headers=admin_headers).status_code == 200

    def test_changing_to_another_students_number_or_email_is_409(self, client, admin_headers):
        sid = student_by("CSE23001").id
        assert client.patch(f"{URL}/{sid}", json={"enrollment_no": "CSE23002"}, headers=admin_headers).status_code == 409
        assert client.patch(f"{URL}/{sid}", json={"email": "student2@timetable.test"}, headers=admin_headers).status_code == 409
        assert student_by("CSE23001") is not None

    def test_clearing_the_email(self, client, admin_headers):
        sid = student_by("CSE23001").id
        assert client.patch(f"{URL}/{sid}", json={"email": ""}, headers=admin_headers).get_json()["data"]["email"] is None

    def test_update_validation(self, client, admin_headers):
        sid = student_by("CSE23001").id
        assert client.patch(f"{URL}/{sid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"batch_id": 9999}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"name": "x"}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"user_id": 7}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/9999", json={"name": "Valid Name"}, headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- delete
class TestDelete:
    def test_delete_a_student_without_a_login(self, client, admin_headers):
        sid = post(client, admin_headers).get_json()["data"]["id"]
        response = client.delete(f"{URL}/{sid}", headers=admin_headers)
        assert response.status_code == 200 and response.get_json()["data"] == {"login_disabled": False}
        assert db.session.get(Student, sid) is None
        assert strength_of(client, admin_headers, batch_id())["student_count"] == 2  # count follows the deletion

    def test_deleting_a_student_disables_their_login_but_keeps_other_accounts(self, client, admin_headers):
        sid = student_by("CSE23001").id
        user_id = student_by("CSE23001").user_id
        response = client.delete(f"{URL}/{sid}", headers=admin_headers)
        assert response.get_json()["data"] == {"login_disabled": True}
        assert "login account was disabled" in response.get_json()["message"]
        assert db.session.get(User, user_id).is_active is False  # row kept, just disabled
        assert login(client, "student1@timetable.test").status_code == 401
        assert login(client, "student2@timetable.test").status_code == 200  # others unaffected
        assert auth_header(client, "admin@timetable.test")

    def test_a_disabled_students_existing_token_stops_working(self, client, admin_headers, student_headers):
        sid = student_by("CSE23001").id
        client.delete(f"{URL}/{sid}", headers=admin_headers)
        assert client.get("/api/v1/auth/me", headers=student_headers).status_code == 401

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/9999", headers=admin_headers).status_code == 404

    def test_enrollment_number_can_be_reused_after_deleting(self, client, admin_headers):
        sid = post(client, admin_headers).get_json()["data"]["id"]
        client.delete(f"{URL}/{sid}", headers=admin_headers)
        assert post(client, admin_headers).status_code == 201
