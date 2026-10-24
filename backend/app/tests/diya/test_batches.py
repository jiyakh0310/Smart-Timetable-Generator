"""Diya - R3 Batch management API (DIY-TC04 plus strength accuracy, permission and in-use rules)."""
import pytest

from app.extensions import db
from app.models import Announcement, AnnouncementStatus, Audience, Batch, Program, Room, Student, TeachingAssignment, Timetable, TimetableEntry, TimeSlot, User

URL = "/api/v1/batches"


def program_id():
    return db.session.scalar(db.select(Program.id))


def batch_by_name(name):
    return db.session.scalar(db.select(Batch).where(Batch.name == name))


def body(**over):
    data = {"program_id": program_id(), "semester_no": 4, "section": "A", "strength": 60}
    data.update(over)
    return data


def post(client, headers, **over):
    return client.post(URL, json=body(**over), headers=headers)


def add_student(batch_id, number="X1"):
    s = Student(enrollment_no=number, name="Test Student", batch_id=batch_id)
    db.session.add(s)
    db.session.commit()
    return s


# ---------------------------------------------------------------- permissions
class TestPermissions:
    def test_requires_login(self, client, seeded):
        assert client.get(URL).status_code == 401
        assert client.post(URL, json=body()).status_code == 401
        assert client.get("/api/v1/programs").status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_non_admins_cannot_write(self, client, request, who):
        headers = request.getfixturevalue(who)
        bid = batch_by_name("CSE Sem 3 - A").id
        assert client.post(URL, json=body(), headers=headers).status_code == 403
        assert client.patch(f"{URL}/{bid}", json={"strength": 10}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{bid}", headers=headers).status_code == 403
        assert db.session.get(Batch, bid).strength == 58

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers", "admin_headers"])
    def test_every_signed_in_role_can_read_batches_and_programs(self, client, request, who):
        headers = request.getfixturevalue(who)
        assert client.get(URL, headers=headers).status_code == 200
        assert client.get("/api/v1/programs", headers=headers).status_code == 200


def test_programs_lookup(client, admin_headers):
    item = client.get("/api/v1/programs", headers=admin_headers).get_json()["data"]["items"][0]
    assert item["name"] == "B.Tech CSE" and item["duration_semesters"] == 8 and item["department"]["code"] == "CSE"


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_seed_batches_with_enrolment_and_usage(self, client, admin_headers):
        body_ = client.get(URL, headers=admin_headers).get_json()["data"]
        assert body_["total"] == 2
        a, b = body_["items"]
        assert (a["name"], a["section"], a["strength"], a["student_count"], a["seats_left"]) == ("CSE Sem 3 - A", "A", 58, 2, 56)
        assert b["section"] == "B" and b["strength"] == 42
        assert a["program"]["name"] == "B.Tech CSE" and a["department"]["code"] == "CSE"
        assert a["usage"] == {"students": 2, "teaching_assignments": 6, "timetable_entries": 0, "announcements": 0}
        assert a["in_use"] is True and a["scheduled"] is True

    def test_pagination(self, client, admin_headers):
        page1 = client.get(f"{URL}?per_page=1", headers=admin_headers).get_json()["data"]
        page2 = client.get(f"{URL}?per_page=1&page=2", headers=admin_headers).get_json()["data"]
        assert (page1["total"], page1["pages"]) == (2, 2)
        assert [page1["items"][0]["section"], page2["items"][0]["section"]] == ["A", "B"]

    def test_filters_and_search(self, client, admin_headers):
        post(client, admin_headers)  # semester 4, section A
        get = lambda qs: client.get(f"{URL}?{qs}", headers=admin_headers).get_json()["data"]["total"]
        assert get("semester_no=3") == 2 and get("semester_no=4") == 1 and get("semester_no=5") == 0
        assert get(f"program_id={program_id()}") == 3 and get("program_id=999") == 0
        assert get("department_id=1") == 3
        assert get("q=sem 4") == 1 and get("q=SEM") == 3 and get("q=b") == 1 and get("q=zzz") == 0
        assert get("q=%25") == 0

    @pytest.mark.parametrize("qs", ["page=0", "per_page=101", "semester_no=0", "semester_no=13", "program_id=0", "department_id=x"])
    def test_bad_query_values_are_400(self, client, admin_headers, qs):
        assert client.get(f"{URL}?{qs}", headers=admin_headers).status_code == 400

    def test_get_one_and_404(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - B").id
        assert client.get(f"{URL}/{bid}", headers=admin_headers).get_json()["data"]["strength"] == 42
        assert client.get(f"{URL}/9999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create
class TestCreate:
    def test_DIY_TC04_create_a_valid_batch_with_generated_name(self, client, admin_headers):
        response = post(client, admin_headers)
        assert response.status_code == 201
        item = response.get_json()["data"]
        assert item["name"] == "CSE Sem 4 - A" and item["semester_no"] == 4 and item["strength"] == 60
        assert item["department"]["code"] == "CSE"  # taken from the program, never from the client
        assert (item["student_count"], item["seats_left"], item["in_use"]) == (0, 60, False)
        assert db.session.get(Batch, item["id"]).department_id == 1

    def test_section_is_stored_upper_case_and_custom_name_is_kept(self, client, admin_headers):
        item = post(client, admin_headers, section=" b ", name="  Morning   batch  ").get_json()["data"]
        assert item["section"] == "B" and item["name"] == "Morning batch"

    def test_missing_fields_are_each_reported(self, client, admin_headers):
        details = client.post(URL, json={}, headers=admin_headers).get_json()["error"]["details"]
        assert set(details) == {"program_id", "semester_no", "section", "strength"}
        assert Batch.query.count() == 2

    @pytest.mark.parametrize(
        "field, value",
        [
            ("program_id", 999), ("program_id", "x"), ("semester_no", 0), ("semester_no", 9), ("semester_no", "4"), ("semester_no", True),
            ("section", "A B"), ("section", "ABCDEFGHIJK"), ("section", "A!"), ("section", 3),
            ("strength", 0), ("strength", -5), ("strength", 501), ("strength", "60"), ("strength", 60.5), ("strength", True),
            ("name", "x"), ("name", "n" * 81),
        ],
    )
    def test_invalid_values_are_400_with_the_offending_field(self, client, admin_headers, field, value):
        response = post(client, admin_headers, **{field: value})
        assert response.status_code == 400
        assert field in response.get_json()["error"]["details"]

    def test_semester_must_fit_the_programs_duration(self, client, admin_headers):
        response = post(client, admin_headers, semester_no=9)
        assert "8 semesters" in response.get_json()["error"]["details"]["semester_no"]

    def test_client_cannot_set_the_department(self, client, admin_headers):
        response = post(client, admin_headers, department_id=2)
        assert response.status_code == 400 and "department_id" in response.get_json()["error"]["details"]

    def test_unknown_fields_and_non_json(self, client, admin_headers):
        assert post(client, admin_headers, colour="red").status_code == 400
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_duplicate_program_semester_section_is_409(self, client, admin_headers):
        response = post(client, admin_headers, semester_no=3, section="A")
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "duplicate_batch"
        assert "section" in response.get_json()["error"]["details"]

    def test_duplicate_section_ignores_case(self, client, admin_headers):
        assert post(client, admin_headers, semester_no=3, section="a").status_code == 409

    def test_duplicate_name_is_409(self, client, admin_headers):
        response = post(client, admin_headers, name="cse sem 3 - a")
        assert response.status_code == 409 and "name" in response.get_json()["error"]["details"]


# ---------------------------------------------------------------- update & strength accuracy
class TestUpdate:
    def test_update_strength_and_name(self, client, admin_headers):
        bid = post(client, admin_headers).get_json()["data"]["id"]
        item = client.patch(f"{URL}/{bid}", json={"strength": 75, "name": "Evening A"}, headers=admin_headers).get_json()["data"]
        assert (item["strength"], item["name"], item["seats_left"]) == (75, "Evening A", 75)

    def test_clearing_the_name_regenerates_it(self, client, admin_headers):
        bid = post(client, admin_headers, name="Custom").get_json()["data"]["id"]
        assert client.patch(f"{URL}/{bid}", json={"name": ""}, headers=admin_headers).get_json()["data"]["name"] == "CSE Sem 4 - A"

    def test_strength_cannot_drop_below_the_students_already_in_the_batch(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - A").id  # 2 student records
        response = client.patch(f"{URL}/{bid}", json={"strength": 1}, headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "strength_too_low" and "strength" in error["details"]
        assert db.session.get(Batch, bid).strength == 58

    def test_strength_equal_to_enrolment_is_allowed(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - A").id
        item = client.patch(f"{URL}/{bid}", json={"strength": 2}, headers=admin_headers).get_json()["data"]
        assert (item["strength"], item["seats_left"]) == (2, 0)

    def test_student_counts_follow_the_real_records(self, client, admin_headers):
        item = post(client, admin_headers, strength=5).get_json()["data"]
        add_student(item["id"], "N1")
        add_student(item["id"], "N2")
        fresh = client.get(f"{URL}/{item['id']}", headers=admin_headers).get_json()["data"]
        assert (fresh["student_count"], fresh["seats_left"], fresh["strength"]) == (2, 3, 5)

    def test_scheduled_batch_cannot_change_program_or_semester(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - A").id
        response = client.patch(f"{URL}/{bid}", json={"semester_no": 4}, headers=admin_headers)
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "batch_in_use"
        assert db.session.get(Batch, bid).semester_no == 3

    def test_scheduled_batch_can_still_change_strength_name_and_section_and_accepts_unchanged_resends(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - B").id
        payload = {"program_id": program_id(), "semester_no": 3, "section": "C", "strength": 50, "name": "CSE Sem 3 - C"}
        item = client.patch(f"{URL}/{bid}", json=payload, headers=admin_headers).get_json()["data"]
        assert (item["section"], item["strength"], item["name"]) == ("C", 50, "CSE Sem 3 - C")

    def test_unscheduled_batch_can_change_semester(self, client, admin_headers):
        bid = post(client, admin_headers).get_json()["data"]["id"]
        item = client.patch(f"{URL}/{bid}", json={"semester_no": 5}, headers=admin_headers).get_json()["data"]
        assert item["semester_no"] == 5

    def test_update_into_an_existing_section_is_409(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - B").id
        assert client.patch(f"{URL}/{bid}", json={"section": "a"}, headers=admin_headers).status_code == 409

    def test_update_validation(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - A").id
        assert client.patch(f"{URL}/{bid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{bid}", json={"strength": 0}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{bid}", json={"id": 3}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/9999", json={"strength": 5}, headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- delete / in-use
class TestDelete:
    def test_delete_an_empty_unused_batch(self, client, admin_headers):
        bid = post(client, admin_headers).get_json()["data"]["id"]
        assert client.delete(f"{URL}/{bid}", headers=admin_headers).status_code == 200
        assert db.session.get(Batch, bid) is None

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/9999", headers=admin_headers).status_code == 404

    def test_batch_with_students_cannot_be_deleted(self, client, admin_headers):
        bid = post(client, admin_headers).get_json()["data"]["id"]
        add_student(bid)
        response = client.delete(f"{URL}/{bid}", headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "batch_in_use" and "1 student" in error["message"]
        assert db.session.get(Batch, bid) is not None and Student.query.filter_by(batch_id=bid).count() == 1

    def test_seeded_batch_with_students_and_assignments_cannot_be_deleted(self, client, admin_headers):
        bid = batch_by_name("CSE Sem 3 - A").id
        message = client.delete(f"{URL}/{bid}", headers=admin_headers).get_json()["error"]["message"]
        assert "2 students" in message and "6 teaching assignments" in message
        assert TeachingAssignment.query.filter_by(batch_id=bid).count() == 6  # nothing cascaded away

    def test_batch_referenced_by_an_announcement_cannot_be_deleted(self, client, admin_headers):
        bid = post(client, admin_headers).get_json()["data"]["id"]
        admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
        db.session.add(Announcement(title="Room change", message="x", audience=Audience.BATCH, batch_id=bid, status=AnnouncementStatus.DRAFT, created_by=admin.id))
        db.session.commit()
        response = client.delete(f"{URL}/{bid}", headers=admin_headers)
        assert response.status_code == 409 and "1 announcement" in response.get_json()["error"]["message"]

    def test_batch_in_a_timetable_reports_timetable_entries(self, client, admin_headers):
        batch = batch_by_name("CSE Sem 3 - B")
        assignment = db.session.scalar(db.select(TeachingAssignment).where(TeachingAssignment.batch_id == batch.id))
        admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
        timetable = Timetable(term_id=assignment.term_id, name="T", version=1, generated_by=admin.id)
        db.session.add(timetable)
        db.session.flush()
        db.session.add(TimetableEntry(timetable_id=timetable.id, assignment_id=assignment.id, faculty_id=assignment.faculty_id, batch_id=batch.id,
                                      room_id=db.session.scalar(db.select(Room.id)), time_slot_id=db.session.scalar(db.select(TimeSlot.id))))
        db.session.commit()
        message = client.delete(f"{URL}/{batch.id}", headers=admin_headers).get_json()["error"]["message"]
        assert "1 timetable entry" in message
        response = client.patch(f"{URL}/{batch.id}", json={"semester_no": 4}, headers=admin_headers)
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "batch_in_use"
