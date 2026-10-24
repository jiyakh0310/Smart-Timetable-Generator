"""Diya - R4 Subject/Course Management API (DIY-TC05 .. DIY-TC08 plus permission, duplicate, in-use rules)."""
import pytest

from app.extensions import db
from app.models import Department, Room, Subject, TeachingAssignment, Timetable, TimetableEntry, TimeSlot, User

URL = "/api/v1/subjects"


def dept_id():
    return db.session.scalar(db.select(Department.id).where(Department.code == "CSE"))


def theory(**over):
    body = {"code": "CS401", "name": "Computer Networks", "department_id": dept_id(), "semester_no": 4, "credits": 4, "weekly_hours": 4, "class_type": "theory"}
    body.update(over)
    return body


def lab(**over):
    body = {"code": "CS451", "name": "Networks Lab", "department_id": dept_id(), "semester_no": 4, "credits": 2, "weekly_hours": 4, "class_type": "lab"}
    body.update(over)
    return body


def subject_by_code(code):
    return db.session.scalar(db.select(Subject).where(Subject.code == code))


def post(client, headers, body):
    return client.post(URL, json=body, headers=headers)


# ---------------------------------------------------------------- permissions
class TestPermissions:
    def test_requires_login(self, client, seeded):
        assert client.get(URL).status_code == 401
        assert client.post(URL, json={}).status_code == 401
        assert client.get("/api/v1/departments").status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_non_admins_cannot_write(self, client, request, who):
        headers = request.getfixturevalue(who)
        sid = subject_by_code("CS301").id
        assert post(client, headers, theory()).status_code == 403
        assert client.patch(f"{URL}/{sid}", json={"name": "Hacked"}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{sid}", headers=headers).status_code == 403
        assert subject_by_code("CS301").name == "Data Structures"
        assert subject_by_code("CS401") is None

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers", "admin_headers"])
    def test_every_signed_in_role_can_read(self, client, request, who):
        headers = request.getfixturevalue(who)
        assert client.get(URL, headers=headers).status_code == 200
        assert client.get("/api/v1/departments", headers=headers).status_code == 200


def test_departments_lookup(client, admin_headers):
    items = client.get("/api/v1/departments", headers=admin_headers).get_json()["data"]["items"]
    assert items == [{"id": dept_id(), "code": "CSE", "name": "Computer Science & Engineering"}]


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_seed_subjects_ordered_by_code_with_department_and_usage(self, client, admin_headers):
        body = client.get(f"{URL}?per_page=4", headers=admin_headers).get_json()["data"]
        assert (body["total"], body["pages"], body["per_page"]) == (6, 2, 4)
        assert [i["code"] for i in body["items"]] == ["CS301", "CS302", "CS303", "CS351"]
        first = body["items"][0]
        assert first["department"]["code"] == "CSE" and first["class_type"] == "theory" and first["sessions_per_week"] == 4
        assert first["usage"]["teaching_assignments"] == 2 and first["in_use"] is True
        lab_item = client.get(f"{URL}?class_type=lab", headers=admin_headers).get_json()["data"]["items"][0]
        assert lab_item["sessions_per_week"] == 1  # 2 hours / 2-period sessions

    def test_second_page(self, client, admin_headers):
        body = client.get(f"{URL}?per_page=4&page=2", headers=admin_headers).get_json()["data"]
        assert [i["code"] for i in body["items"]] == ["CS352", "MA301"]

    def test_filters(self, client, admin_headers):
        get = lambda qs: client.get(f"{URL}?{qs}", headers=admin_headers).get_json()["data"]
        assert get("class_type=lab")["total"] == 2
        assert get("class_type=theory")["total"] == 4
        assert get("semester_no=3")["total"] == 6
        assert get("semester_no=4")["total"] == 0
        assert get(f"department_id={dept_id()}")["total"] == 6
        assert get("department_id=9999")["total"] == 0
        assert get("class_type=lab&semester_no=3")["total"] == 2

    def test_search_by_code_and_name_is_case_insensitive(self, client, admin_headers):
        get = lambda q: [i["code"] for i in client.get(f"{URL}?q={q}", headers=admin_headers).get_json()["data"]["items"]]
        assert get("cs35") == ["CS351", "CS352"]
        assert get("DATA") == ["CS301", "CS302", "CS351"]  # "Data Structures", "DataBase ...", "Data Structures Lab"
        assert get("lab") == ["CS351", "CS352"]
        assert get("nothing-like-this") == []

    def test_search_treats_percent_and_underscore_literally(self, client, admin_headers):
        assert client.get(f"{URL}?q=%25", headers=admin_headers).get_json()["data"]["total"] == 0
        assert client.get(f"{URL}?q=_", headers=admin_headers).get_json()["data"]["total"] == 0

    @pytest.mark.parametrize("qs", ["page=0", "per_page=101", "semester_no=0", "semester_no=13", "department_id=0", "department_id=x", "class_type=seminar"])
    def test_bad_query_parameters_are_400(self, client, admin_headers, qs):
        assert client.get(f"{URL}?{qs}", headers=admin_headers).status_code == 400

    def test_get_one_and_404(self, client, admin_headers):
        sid = subject_by_code("CS302").id
        assert client.get(f"{URL}/{sid}", headers=admin_headers).get_json()["data"]["name"] == "Database Management Systems"
        assert client.get(f"{URL}/99999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create
class TestCreate:
    def test_DIY_TC05_create_a_valid_theory_subject(self, client, admin_headers):
        response = post(client, admin_headers, theory())
        assert response.status_code == 201
        item = response.get_json()["data"]
        assert (item["code"], item["name"], item["credits"], item["weekly_hours"]) == ("CS401", "Computer Networks", 4, 4)
        assert item["class_type"] == "theory" and item["required_room_type"] == "classroom"  # default for theory
        assert item["sessions_per_week"] == 4 and item["in_use"] is False
        assert subject_by_code("CS401") is not None

    def test_DIY_TC08_create_a_lab_subject_with_defaults(self, client, admin_headers):
        item = post(client, admin_headers, lab()).get_json()["data"]
        assert item["class_type"] == "lab" and item["lab_block_periods"] == 2 and item["required_room_type"] == "lab"
        assert item["sessions_per_week"] == 2  # 4 hours / 2-period sessions

    def test_lab_session_length_is_configurable(self, client, admin_headers):
        item = post(client, admin_headers, lab(weekly_hours=3, lab_block_periods=3)).get_json()["data"]
        assert item["lab_block_periods"] == 3 and item["sessions_per_week"] == 1

    def test_theory_can_use_a_seminar_hall(self, client, admin_headers):
        item = post(client, admin_headers, theory(required_room_type="seminar_hall")).get_json()["data"]
        assert item["required_room_type"] == "seminar_hall"

    def test_code_and_name_are_normalised(self, client, admin_headers):
        item = post(client, admin_headers, theory(code="  cs-402 ", name="  Operating   Systems II ")).get_json()["data"]
        assert item["code"] == "CS-402" and item["name"] == "Operating Systems II"

    def test_credits_may_be_zero(self, client, admin_headers):
        assert post(client, admin_headers, theory(credits=0)).status_code == 201

    def test_DIY_TC07_missing_code_is_rejected_and_nothing_saved(self, client, admin_headers):
        body = theory()
        del body["code"]
        response = post(client, admin_headers, body)
        error = response.get_json()["error"]
        assert response.status_code == 400 and error["code"] == "validation_error"
        assert error["details"] == {"code": "This field is required."}
        assert Subject.query.count() == 6

    def test_blank_code_is_rejected(self, client, admin_headers):
        assert "code" in post(client, admin_headers, theory(code="   ")).get_json()["error"]["details"]

    def test_all_missing_fields_are_listed(self, client, admin_headers):
        details = post(client, admin_headers, {}).get_json()["error"]["details"]
        assert set(details) == {"code", "name", "department_id", "semester_no", "credits", "weekly_hours", "class_type"}

    @pytest.mark.parametrize(
        "field, value",
        [
            ("code", "bad code!"), ("code", "A" * 21), ("code", 301), ("name", "x"), ("name", "n" * 151), ("name", 5),
            ("semester_no", 0), ("semester_no", 13), ("semester_no", "3"), ("semester_no", 3.5), ("semester_no", True),
            ("credits", -1), ("credits", 21), ("credits", "four"), ("weekly_hours", 0), ("weekly_hours", 41), ("weekly_hours", -3),
            ("class_type", "practical"), ("department_id", 99999), ("department_id", "x"), ("required_room_type", "garage"),
        ],
    )
    def test_invalid_values_are_400_with_the_offending_field(self, client, admin_headers, field, value):
        response = post(client, admin_headers, theory(**{field: value}))
        assert response.status_code == 400
        assert field in response.get_json()["error"]["details"]

    def test_unknown_field_is_rejected(self, client, admin_headers):
        response = post(client, admin_headers, theory(faculty="Dr X"))
        assert response.status_code == 400 and "faculty" in response.get_json()["error"]["details"]

    def test_body_must_be_json(self, client, admin_headers):
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_duplicate_code_is_409(self, client, admin_headers):
        response = post(client, admin_headers, theory(code="CS301"))
        assert response.status_code == 409
        assert response.get_json()["error"]["code"] == "duplicate_subject"
        assert "code" in response.get_json()["error"]["details"]

    def test_duplicate_code_ignores_case_and_spaces(self, client, admin_headers):
        assert post(client, admin_headers, theory(code=" cs301 ")).status_code == 409

    def test_lab_must_use_a_laboratory(self, client, admin_headers):
        response = post(client, admin_headers, lab(required_room_type="classroom"))
        assert response.status_code == 400 and "required_room_type" in response.get_json()["error"]["details"]

    def test_theory_cannot_require_a_laboratory(self, client, admin_headers):
        assert "required_room_type" in post(client, admin_headers, theory(required_room_type="lab")).get_json()["error"]["details"]

    def test_lab_hours_must_fit_whole_sessions(self, client, admin_headers):
        response = post(client, admin_headers, lab(weekly_hours=3, lab_block_periods=2))
        assert response.status_code == 400 and "weekly_hours" in response.get_json()["error"]["details"]

    def test_lab_block_out_of_range(self, client, admin_headers):
        assert "lab_block_periods" in post(client, admin_headers, lab(lab_block_periods=7)).get_json()["error"]["details"]

    def test_lab_session_length_is_not_allowed_for_theory(self, client, admin_headers):
        assert "lab_block_periods" in post(client, admin_headers, theory(lab_block_periods=2)).get_json()["error"]["details"]


# ---------------------------------------------------------------- update
class TestUpdate:
    def _new(self, client, headers, **over):
        return post(client, headers, theory(**over)).get_json()["data"]["id"]

    def test_DIY_TC06_update_weekly_hours_of_an_unused_subject(self, client, admin_headers):
        sid = self._new(client, admin_headers)
        response = client.patch(f"{URL}/{sid}", json={"weekly_hours": 5}, headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"]["weekly_hours"] == 5
        assert db.session.get(Subject, sid).weekly_hours == 5

    def test_update_name_credits_and_code(self, client, admin_headers):
        sid = self._new(client, admin_headers)
        item = client.patch(f"{URL}/{sid}", json={"name": "Networks II", "credits": 3, "code": "cs499"}, headers=admin_headers).get_json()["data"]
        assert (item["name"], item["credits"], item["code"]) == ("Networks II", 3, "CS499")

    def test_keeping_your_own_code_is_not_a_duplicate(self, client, admin_headers):
        sid = self._new(client, admin_headers)
        assert client.patch(f"{URL}/{sid}", json={"code": "CS401", "name": "Renamed"}, headers=admin_headers).status_code == 200

    def test_changing_to_another_subjects_code_is_409(self, client, admin_headers):
        sid = self._new(client, admin_headers)
        response = client.patch(f"{URL}/{sid}", json={"code": "cs302"}, headers=admin_headers)
        assert response.status_code == 409 and db.session.get(Subject, sid).code == "CS401"

    def test_changing_type_to_lab_applies_lab_defaults(self, client, admin_headers):
        sid = self._new(client, admin_headers)
        item = client.patch(f"{URL}/{sid}", json={"class_type": "lab"}, headers=admin_headers).get_json()["data"]
        assert item["class_type"] == "lab" and item["required_room_type"] == "lab" and item["lab_block_periods"] == 2

    def test_changing_lab_back_to_theory_resets_room_and_block(self, client, admin_headers):
        sid = post(client, admin_headers, lab()).get_json()["data"]["id"]
        item = client.patch(f"{URL}/{sid}", json={"class_type": "theory"}, headers=admin_headers).get_json()["data"]
        assert item["class_type"] == "theory" and item["required_room_type"] == "classroom" and item["lab_block_periods"] == 1

    def test_update_validation_and_unknown_fields(self, client, admin_headers):
        sid = self._new(client, admin_headers)
        assert client.patch(f"{URL}/{sid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"credits": -2}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"id": 7}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"required_room_type": "lab"}, headers=admin_headers).status_code == 400
        assert db.session.get(Subject, sid).credits == 4

    def test_update_404(self, client, admin_headers):
        assert client.patch(f"{URL}/99999", json={"name": "Xx"}, headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- in-use rules
class TestInUse:
    def test_scheduling_fields_are_locked_when_the_subject_has_teaching_assignments(self, client, admin_headers):
        sid = subject_by_code("CS301").id
        response = client.patch(f"{URL}/{sid}", json={"weekly_hours": 5}, headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "subject_in_use"
        assert "weekly_hours" in error["details"] and "2 batch" in error["message"]
        assert subject_by_code("CS301").weekly_hours == 4

    @pytest.mark.parametrize("change", [{"semester_no": 5}, {"class_type": "lab"}, {"department_id": None}])
    def test_other_locked_fields(self, client, admin_headers, change):
        sid = subject_by_code("CS301").id
        if "department_id" in change:  # a second department so the change is valid but still locked
            other = Department(code="ECE", name="Electronics")
            db.session.add(other)
            db.session.commit()
            change = {"department_id": other.id}
        assert client.patch(f"{URL}/{sid}", json=change, headers=admin_headers).status_code == 409

    def test_harmless_fields_can_still_be_edited_when_in_use(self, client, admin_headers):
        sid = subject_by_code("CS301").id
        item = client.patch(f"{URL}/{sid}", json={"name": "Data Structures & Algorithms", "credits": 5, "required_room_type": "seminar_hall"}, headers=admin_headers).get_json()["data"]
        assert (item["name"], item["credits"], item["required_room_type"]) == ("Data Structures & Algorithms", 5, "seminar_hall")

    def test_resending_unchanged_locked_values_is_fine(self, client, admin_headers):
        """The edit form always sends every field; unchanged ones must not trigger the lock."""
        sid = subject_by_code("CS351").id
        current = client.get(f"{URL}/{sid}", headers=admin_headers).get_json()["data"]
        payload = {k: current[k] for k in ("code", "name", "semester_no", "credits", "weekly_hours", "class_type", "lab_block_periods", "required_room_type")}
        payload["department_id"] = current["department"]["id"]
        payload["credits"] = 3
        assert client.patch(f"{URL}/{sid}", json=payload, headers=admin_headers).status_code == 200

    def test_cannot_delete_a_subject_with_teaching_assignments(self, client, admin_headers):
        sid = subject_by_code("CS301").id
        before = TeachingAssignment.query.filter_by(subject_id=sid).count()
        response = client.delete(f"{URL}/{sid}", headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "subject_in_use"
        assert "2 teaching assignments" in error["message"] and "Remove those assignments" in error["message"]
        assert db.session.get(Subject, sid) is not None
        assert TeachingAssignment.query.filter_by(subject_id=sid).count() == before == 2  # nothing cascaded away

    def test_message_mentions_timetable_entries_when_scheduled(self, client, admin_headers):
        subject = subject_by_code("CS301")
        assignment = db.session.scalar(db.select(TeachingAssignment).where(TeachingAssignment.subject_id == subject.id))
        admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
        timetable = Timetable(term_id=assignment.term_id, name="T", version=1, generated_by=admin.id)
        db.session.add(timetable)
        db.session.flush()
        db.session.add(TimetableEntry(timetable_id=timetable.id, assignment_id=assignment.id, faculty_id=assignment.faculty_id, batch_id=assignment.batch_id,
                                      room_id=db.session.scalar(db.select(Room.id)), time_slot_id=db.session.scalar(db.select(TimeSlot.id))))
        db.session.commit()
        response = client.delete(f"{URL}/{subject.id}", headers=admin_headers)
        assert response.status_code == 409 and "1 timetable entry" in response.get_json()["error"]["message"]
        assert client.get(f"{URL}/{subject.id}", headers=admin_headers).get_json()["data"]["usage"] == {"teaching_assignments": 2, "timetable_entries": 1}


# ---------------------------------------------------------------- delete
class TestDelete:
    def test_delete_an_unused_subject(self, client, admin_headers):
        sid = post(client, admin_headers, theory()).get_json()["data"]["id"]
        assert client.delete(f"{URL}/{sid}", headers=admin_headers).status_code == 200
        assert db.session.get(Subject, sid) is None
        assert client.get(f"{URL}/{sid}", headers=admin_headers).status_code == 404
        assert Subject.query.count() == 6

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/99999", headers=admin_headers).status_code == 404

    def test_code_can_be_reused_after_deleting(self, client, admin_headers):
        sid = post(client, admin_headers, theory()).get_json()["data"]["id"]
        client.delete(f"{URL}/{sid}", headers=admin_headers)
        assert post(client, admin_headers, theory()).status_code == 201
