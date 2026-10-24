"""Teaching assignments API: CRUD, references, compatibility, computed session counts, in-use protection, availability warnings."""
import itertools

import pytest

from app.extensions import db
from app.models import (
    AcademicTerm,
    Batch,
    Department,
    Faculty,
    Room,
    Subject,
    TeachingAssignment,
    TermType,
    TimeSlot,
    Timetable,
    TimetableEntry,
    UnscheduledItem,
    User,
)

URL = "/api/v1/teaching-assignments"


# ---------------------------------------------------------------- helpers
def term_id():
    return db.session.scalar(db.select(AcademicTerm.id))


def batch(name="CSE Sem 3 - A"):
    return db.session.scalar(db.select(Batch).where(Batch.name == name))


def fac(code):
    return db.session.scalar(db.select(Faculty).where(Faculty.employee_code == code))


def subject(code):
    return db.session.scalar(db.select(Subject).where(Subject.code == code))


_codes = itertools.count(800)


def new_subject(client, headers, code=None, **over):
    code = code or f"CS{next(_codes)}"  # unique every call
    body = {"code": code, "name": f"Subject {code}", "department_id": 1, "semester_no": 3, "credits": 3, "weekly_hours": 3, "class_type": "theory"}
    body.update(over)
    response = client.post("/api/v1/subjects", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["id"]


def new_faculty(client, headers, code="FNEW", **over):
    body = {"name": f"Faculty {code}", "email": f"{code.lower()}@college.test", "employee_code": code, "department_id": 1, "password": "Secure#Pass42"}
    body.update(over)
    response = client.post("/api/v1/faculty", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["id"]


def payload(client, headers, **over):
    """A valid, not-yet-existing assignment: batch A + a fresh semester-3 subject, taught by F001."""
    data = {"term_id": term_id(), "batch_id": batch().id, "faculty_id": fac("F001").id}
    data["subject_id"] = over.pop("subject_id") if "subject_id" in over else new_subject(client, headers)  # only create one when not supplied
    data.update(over)
    return data


def post(client, headers, **over):
    return client.post(URL, json=payload(client, headers, **over), headers=headers)


def set_unavailable(client, headers, faculty_id, keep_period_nos=()):
    """Mark every active class slot unavailable except the given period numbers (hard rule)."""
    slots = db.session.scalars(db.select(TimeSlot).where(TimeSlot.slot_type == "class", TimeSlot.is_active.is_(True))).all()
    entries = [{"time_slot_id": s.id, "status": "unavailable"} for s in slots if s.period_no not in keep_period_nos]
    assert client.put(f"/api/v1/faculty/{faculty_id}/availability", json={"entries": entries}, headers=headers).status_code == 200


def use_in_timetable(assignment, unscheduled_only=False):
    admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
    timetable = Timetable(term_id=assignment.term_id, name="T", version=1, generated_by=admin.id)
    db.session.add(timetable)
    db.session.flush()
    if unscheduled_only:
        db.session.add(UnscheduledItem(timetable_id=timetable.id, assignment_id=assignment.id, session_no=1, reason_code="no_slot", reason_text="No slot"))
    else:
        db.session.add(TimetableEntry(timetable_id=timetable.id, assignment_id=assignment.id, faculty_id=assignment.faculty_id, batch_id=assignment.batch_id,
                                      room_id=db.session.scalar(db.select(Room.id)), time_slot_id=db.session.scalar(db.select(TimeSlot.id))))
    db.session.commit()


def codes(response):
    return {w["code"] for w in response.get_json()["data"]["warnings"]}


# ---------------------------------------------------------------- permissions
class TestPermissions:
    def test_requires_login(self, client, seeded):
        assert client.get(URL).status_code == 401
        assert client.post(URL, json={}).status_code == 401
        assert client.get("/api/v1/terms").status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_assignments_are_admin_only_even_for_reading(self, client, request, who):
        headers = request.getfixturevalue(who)
        aid = db.session.scalar(db.select(TeachingAssignment.id))
        assert client.get(URL, headers=headers).status_code == 403
        assert client.get(f"{URL}/{aid}", headers=headers).status_code == 403
        assert client.post(URL, json={}, headers=headers).status_code == 403
        assert client.patch(f"{URL}/{aid}", json={"faculty_id": 1}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{aid}", headers=headers).status_code == 403
        assert TeachingAssignment.query.count() == 12

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers", "admin_headers"])
    def test_term_lookup_is_readable_by_any_signed_in_user(self, client, request, who):
        items = client.get("/api/v1/terms", headers=request.getfixturevalue(who)).get_json()["data"]["items"]
        assert items[0]["name"] == "2026-27 Odd" and items[0]["is_active"] is True


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_the_seed_assignments_with_computed_session_information(self, client, admin_headers):
        data = client.get(f"{URL}?per_page=100", headers=admin_headers).get_json()["data"]
        assert data["total"] == 12
        by_key = {(i["batch"]["name"], i["subject"]["code"]): i for i in data["items"]}
        theory = by_key[("CSE Sem 3 - A", "CS301")]
        assert (theory["sessions_per_week"], theory["session_length"], theory["periods_per_week"]) == (4, 1, 4)
        assert theory["faculty"]["employee_code"] == "F001" and theory["term"]["name"] == "2026-27 Odd"
        lab = by_key[("CSE Sem 3 - A", "CS351")]
        assert (lab["sessions_per_week"], lab["session_length"], lab["periods_per_week"]) == (1, 2, 2)
        for item in data["items"]:
            assert item["cross_department"] is False and item["session_mismatch"] is False and item["in_use"] is False and item["warnings"] == []

    def test_pagination_and_ordering(self, client, admin_headers):
        p1 = client.get(f"{URL}?per_page=5", headers=admin_headers).get_json()["data"]
        p3 = client.get(f"{URL}?per_page=5&page=3", headers=admin_headers).get_json()["data"]
        assert (p1["total"], p1["pages"], len(p1["items"]), len(p3["items"])) == (12, 3, 5, 2)
        assert [i["subject"]["code"] for i in p1["items"]] == ["CS301", "CS302", "CS303", "CS351", "CS352"]
        assert {i["batch"]["name"] for i in p1["items"]} == {"CSE Sem 3 - A"}

    def test_filters(self, client, admin_headers):
        get = lambda qs: client.get(f"{URL}?{qs}&per_page=100", headers=admin_headers).get_json()["data"]["total"]
        assert get(f"batch_id={batch().id}") == 6
        assert get(f"faculty_id={fac('F001').id}") == 3 and get(f"faculty_id={fac('F006').id}") == 2
        assert get(f"subject_id={subject('CS301').id}") == 2
        assert get("class_type=lab") == 4 and get("class_type=theory") == 8
        assert get("semester_no=3") == 12 and get("semester_no=4") == 0
        assert get(f"term_id={term_id()}") == 12 and get("term_id=999") == 0

    def test_search_by_subject_faculty_or_batch(self, client, admin_headers):
        get = lambda q: client.get(f"{URL}?q={q}&per_page=100", headers=admin_headers).get_json()["data"]["total"]
        assert get("cs351") == 2 and get("rakesh") == 3 and get("f006") == 2 and get("sem 3 - b") == 6 and get("nothing") == 0 and get("%25") == 0

    @pytest.mark.parametrize("qs", ["page=0", "per_page=101", "term_id=0", "batch_id=x", "faculty_id=-1", "semester_no=13", "class_type=seminar"])
    def test_bad_query_values_are_400(self, client, admin_headers, qs):
        assert client.get(f"{URL}?{qs}", headers=admin_headers).status_code == 400

    def test_get_one_and_404(self, client, admin_headers):
        aid = db.session.scalar(db.select(TeachingAssignment.id))
        assert client.get(f"{URL}/{aid}", headers=admin_headers).status_code == 200
        assert client.get(f"{URL}/9999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create + session counts
class TestCreate:
    def test_a_theory_subject_needs_one_session_per_weekly_hour(self, client, admin_headers):
        response = post(client, admin_headers)
        assert response.status_code == 201
        item = response.get_json()["data"]
        assert (item["sessions_per_week"], item["session_length"], item["periods_per_week"]) == (3, 1, 3)
        stored = db.session.get(TeachingAssignment, item["id"])
        assert stored.sessions_per_week == 3 and (stored.faculty_id, stored.batch_id) == (fac("F001").id, batch().id)

    def test_a_lab_subject_needs_hours_divided_by_the_session_length(self, client, admin_headers):
        sid = new_subject(client, admin_headers, code="CS361", class_type="lab", weekly_hours=6, lab_block_periods=3)
        item = post(client, admin_headers, subject_id=sid).get_json()["data"]
        assert (item["sessions_per_week"], item["session_length"], item["periods_per_week"]) == (2, 3, 6)
        assert db.session.get(TeachingAssignment, item["id"]).sessions_per_week == 2

    def test_a_client_cannot_set_the_session_count(self, client, admin_headers):
        response = post(client, admin_headers, sessions_per_week=99)
        assert response.status_code == 400 and "sessions_per_week" in response.get_json()["error"]["details"]
        assert TeachingAssignment.query.count() == 12

    def test_missing_fields_are_each_reported(self, client, admin_headers):
        details = client.post(URL, json={}, headers=admin_headers).get_json()["error"]["details"]
        assert set(details) == {"term_id", "batch_id", "subject_id", "faculty_id"}

    @pytest.mark.parametrize("field", ["term_id", "batch_id", "subject_id", "faculty_id"])
    @pytest.mark.parametrize("value", [99999, "x", True, 0, -1])
    def test_invalid_references_are_400_on_the_right_field(self, client, admin_headers, field, value):
        response = post(client, admin_headers, **{field: value})
        assert response.status_code == 400 and field in response.get_json()["error"]["details"]
        assert TeachingAssignment.query.count() == 12

    def test_unknown_fields_and_non_json(self, client, admin_headers):
        assert post(client, admin_headers, colour="red").status_code == 400
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_subject_and_batch_must_be_in_the_same_semester(self, client, admin_headers):
        sem4 = new_subject(client, admin_headers, code="CS460", semester_no=4)
        response = post(client, admin_headers, subject_id=sem4)
        error = response.get_json()["error"]
        assert response.status_code == 400 and "semester 4" in error["details"]["subject_id"] and "semester 3" in error["details"]["subject_id"]

    def test_a_department_mismatch_is_allowed_but_flagged(self, client, admin_headers):
        ece = Department(code="ECE", name="Electronics")
        db.session.add(ece)
        db.session.commit()
        sid = new_subject(client, admin_headers, code="EC301", department_id=ece.id)
        item = post(client, admin_headers, subject_id=sid).get_json()["data"]
        assert item["cross_department"] is True and item["subject"]["department_code"] == "ECE" and item["batch"]["department_code"] == "CSE"

    def test_an_inactive_faculty_member_cannot_be_assigned(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        client.patch(f"/api/v1/faculty/{fid}", json={"is_active": False}, headers=admin_headers)
        response = post(client, admin_headers, faculty_id=fid)
        assert response.status_code == 400 and "inactive" in response.get_json()["error"]["details"]["faculty_id"]

    def test_an_inactive_term_cannot_get_new_assignments(self, client, admin_headers):
        old = AcademicTerm(name="2025-26 Even", academic_year="2025-26", term_type=TermType.EVEN, is_active=False)
        db.session.add(old)
        db.session.commit()
        response = post(client, admin_headers, term_id=old.id)
        assert response.status_code == 400 and "term_id" in response.get_json()["error"]["details"]

    def test_a_batch_has_one_teacher_per_subject_per_term(self, client, admin_headers):
        existing = db.session.scalar(db.select(TeachingAssignment).where(TeachingAssignment.batch_id == batch().id, TeachingAssignment.subject_id == subject("CS301").id))
        response = client.post(URL, json={"term_id": existing.term_id, "batch_id": existing.batch_id, "subject_id": existing.subject_id, "faculty_id": fac("F004").id}, headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "duplicate_assignment" and "subject_id" in error["details"]
        assert "F001" not in error["message"] and "Dr. Rakesh Sharma" in error["message"]
        assert TeachingAssignment.query.count() == 12

    def test_the_same_subject_can_go_to_another_batch_or_term(self, client, admin_headers):
        sid = new_subject(client, admin_headers)
        assert post(client, admin_headers, subject_id=sid, faculty_id=fac("F001").id).status_code == 201
        assert post(client, admin_headers, subject_id=sid, batch_id=batch("CSE Sem 3 - B").id, faculty_id=fac("F002").id).status_code == 201


# ---------------------------------------------------------------- update
class TestUpdate:
    def _make(self, client, headers, **over):
        return post(client, headers, **over).get_json()["data"]

    def test_change_the_teacher(self, client, admin_headers):
        item = self._make(client, admin_headers)
        updated = client.patch(f"{URL}/{item['id']}", json={"faculty_id": fac("F002").id}, headers=admin_headers).get_json()["data"]
        assert updated["faculty"]["employee_code"] == "F002"
        assert db.session.get(TeachingAssignment, item["id"]).faculty_id == fac("F002").id

    def test_changing_the_subject_recomputes_the_session_count(self, client, admin_headers):
        item = self._make(client, admin_headers)  # theory, 3 sessions
        lab = new_subject(client, admin_headers, code="CS362", class_type="lab", weekly_hours=4, lab_block_periods=2)
        updated = client.patch(f"{URL}/{item['id']}", json={"subject_id": lab}, headers=admin_headers).get_json()["data"]
        assert (updated["sessions_per_week"], updated["session_length"], updated["periods_per_week"]) == (2, 2, 4)

    def test_resending_unchanged_values_is_fine(self, client, admin_headers):
        item = self._make(client, admin_headers)
        same = {"term_id": item["term"]["id"], "batch_id": item["batch"]["id"], "subject_id": item["subject"]["id"], "faculty_id": item["faculty"]["id"]}
        assert client.patch(f"{URL}/{item['id']}", json=same, headers=admin_headers).status_code == 200

    def test_an_existing_assignment_with_a_now_inactive_teacher_can_still_be_edited_without_changing_the_teacher(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        item = self._make(client, admin_headers, faculty_id=fid)
        client.patch(f"/api/v1/faculty/{fid}", json={"is_active": False}, headers=admin_headers)
        same = {"faculty_id": fid, "batch_id": item["batch"]["id"]}
        assert client.patch(f"{URL}/{item['id']}", json=same, headers=admin_headers).status_code == 200
        assert client.patch(f"{URL}/{item['id']}", json={"faculty_id": fac("F002").id}, headers=admin_headers).status_code == 200

    def test_moving_an_assignment_onto_an_existing_batch_and_subject_is_409(self, client, admin_headers):
        item = self._make(client, admin_headers)
        taken = subject("CS301").id
        assert client.patch(f"{URL}/{item['id']}", json={"subject_id": taken}, headers=admin_headers).status_code == 409

    def test_update_validation(self, client, admin_headers):
        item = self._make(client, admin_headers)
        aid = item["id"]
        assert client.patch(f"{URL}/{aid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{aid}", json={"faculty_id": 99999}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{aid}", json={"sessions_per_week": 9}, headers=admin_headers).status_code == 400
        sem4 = new_subject(client, admin_headers, code="CS461", semester_no=4)
        assert client.patch(f"{URL}/{aid}", json={"subject_id": sem4}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/9999", json={"faculty_id": 1}, headers=admin_headers).status_code == 404
        assert db.session.get(TeachingAssignment, aid).sessions_per_week == 3


# ---------------------------------------------------------------- protection of generated timetables
class TestInUse:
    @pytest.mark.parametrize("unscheduled_only", [False, True], ids=["timetable_entry", "unscheduled_item"])
    def test_an_assignment_used_by_a_timetable_is_frozen_and_cannot_be_deleted(self, client, admin_headers, unscheduled_only):
        a = db.session.scalar(db.select(TeachingAssignment).where(TeachingAssignment.faculty_id == fac("F005").id))
        use_in_timetable(a, unscheduled_only)
        before = (a.term_id, a.batch_id, a.subject_id, a.faculty_id, a.sessions_per_week)
        for change in ({"faculty_id": fac("F002").id}, {"subject_id": new_subject(client, admin_headers)}, {"batch_id": batch("CSE Sem 3 - A").id}):
            response = client.patch(f"{URL}/{a.id}", json=change, headers=admin_headers)
            assert response.status_code == 409 and response.get_json()["error"]["code"] == "assignment_in_use", change
        response = client.delete(f"{URL}/{a.id}", headers=admin_headers)
        assert response.status_code == 409 and "generated timetable" in response.get_json()["error"]["message"]
        db.session.expire_all()
        a = db.session.get(TeachingAssignment, a.id)
        assert (a.term_id, a.batch_id, a.subject_id, a.faculty_id, a.sessions_per_week) == before

    def test_a_frozen_assignment_still_accepts_an_unchanged_resend_and_reports_in_use(self, client, admin_headers):
        a = db.session.scalar(db.select(TeachingAssignment).where(TeachingAssignment.faculty_id == fac("F005").id))
        use_in_timetable(a)
        item = client.get(f"{URL}/{a.id}", headers=admin_headers).get_json()["data"]
        assert item["in_use"] is True and item["usage"] == {"timetable_entries": 1, "unscheduled_items": 0}
        same = {"term_id": a.term_id, "batch_id": a.batch_id, "subject_id": a.subject_id, "faculty_id": a.faculty_id}
        assert client.patch(f"{URL}/{a.id}", json=same, headers=admin_headers).status_code == 200


# ---------------------------------------------------------------- delete + regressions of other modules
class TestDelete:
    def test_delete_an_assignment_nothing_depends_on(self, client, admin_headers):
        aid = post(client, admin_headers).get_json()["data"]["id"]
        assert client.delete(f"{URL}/{aid}", headers=admin_headers).status_code == 200
        assert db.session.get(TeachingAssignment, aid) is None and TeachingAssignment.query.count() == 12
        assert post(client, admin_headers).status_code == 201

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/9999", headers=admin_headers).status_code == 404

    def test_removing_an_assignment_unlocks_the_subject_batch_and_faculty_it_was_holding(self, client, admin_headers):
        sid = new_subject(client, admin_headers)
        fid = new_faculty(client, admin_headers)
        aid = post(client, admin_headers, subject_id=sid, faculty_id=fid).get_json()["data"]["id"]
        assert client.delete(f"/api/v1/subjects/{sid}", headers=admin_headers).status_code == 409
        assert client.delete(f"/api/v1/faculty/{fid}", headers=admin_headers).status_code == 409
        assert client.patch(f"/api/v1/subjects/{sid}", json={"weekly_hours": 5}, headers=admin_headers).status_code == 409
        client.delete(f"{URL}/{aid}", headers=admin_headers)
        assert client.patch(f"/api/v1/subjects/{sid}", json={"weekly_hours": 5}, headers=admin_headers).status_code == 200
        assert client.delete(f"/api/v1/subjects/{sid}", headers=admin_headers).status_code == 200
        assert client.delete(f"/api/v1/faculty/{fid}", headers=admin_headers).status_code == 200

    def test_existing_protections_still_hold_for_seeded_data(self, client, admin_headers):
        assert client.delete(f"/api/v1/batches/{batch().id}", headers=admin_headers).status_code == 409
        assert client.patch(f"/api/v1/batches/{batch().id}", json={"semester_no": 4}, headers=admin_headers).status_code == 409
        assert client.delete(f"/api/v1/subjects/{subject('CS301').id}", headers=admin_headers).status_code == 409
        assert client.delete(f"/api/v1/faculty/{fac('F001').id}", headers=admin_headers).status_code == 409
        assert TeachingAssignment.query.count() == 12


# ---------------------------------------------------------------- availability warnings (hard vs soft)
class TestAvailabilityWarnings:
    def test_assignments_are_never_blocked_by_availability_but_a_shortfall_is_reported(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        set_unavailable(client, admin_headers, fid, keep_period_nos=(1,))  # only 6 usable slots left (period 1 on 5 days... 5)
        sid = new_subject(client, admin_headers, code="CS370", weekly_hours=8)  # theory: needs 8 periods
        response = post(client, admin_headers, subject_id=sid, faculty_id=fid)
        assert response.status_code == 201  # not blocked
        warning = next(w for w in response.get_json()["data"]["warnings"] if w["code"] == "availability_shortfall")
        assert "8 periods per week" in warning["message"] and "only 5 time slots" in warning["message"]

    def test_a_soft_preference_never_counts_as_unavailability(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        slots = db.session.scalars(db.select(TimeSlot).where(TimeSlot.slot_type == "class")).all()
        client.put(f"/api/v1/faculty/{fid}/availability", json={"entries": [{"time_slot_id": s.id, "status": "preferred"} for s in slots]}, headers=admin_headers)
        sid = new_subject(client, admin_headers, code="CS371", weekly_hours=8)
        assert codes(post(client, admin_headers, subject_id=sid, faculty_id=fid)) == set()

    def test_the_shortfall_counts_all_of_the_faculty_members_assignments_in_the_term(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        set_unavailable(client, admin_headers, fid, keep_period_nos=(1,))  # 5 usable
        first = post(client, admin_headers, subject_id=new_subject(client, admin_headers, code="CS372", weekly_hours=3), faculty_id=fid)
        assert codes(first) == set()  # 3 <= 5
        second = post(client, admin_headers, subject_id=new_subject(client, admin_headers, code="CS373", weekly_hours=3), faculty_id=fid)
        assert "availability_shortfall" in codes(second)  # 6 > 5
        listed = client.get(f"{URL}?faculty_id={fid}", headers=admin_headers).get_json()["data"]["items"]
        assert all("availability_shortfall" in {w["code"] for w in i["warnings"]} for i in listed)

    def test_a_lab_needs_a_window_of_consecutive_free_periods_and_a_break_does_not_connect_periods(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        set_unavailable(client, admin_headers, fid, keep_period_nos=(3, 5))  # periods 3 and 5 are separated by the lunch break (4)
        lab = new_subject(client, admin_headers, code="CS374", class_type="lab", weekly_hours=2, lab_block_periods=2)
        response = post(client, admin_headers, subject_id=lab, faculty_id=fid)
        assert response.status_code == 201 and "no_lab_window" in codes(response)
        set_unavailable(client, admin_headers, fid, keep_period_nos=(5, 6))  # now two consecutive free periods exist
        item = client.get(f"{URL}/{response.get_json()['data']['id']}", headers=admin_headers).get_json()["data"]
        assert "no_lab_window" not in {w["code"] for w in item["warnings"]}

    def test_warnings_disappear_when_availability_is_cleared(self, client, admin_headers):
        fid = new_faculty(client, admin_headers)
        set_unavailable(client, admin_headers, fid, keep_period_nos=(1,))
        sid = new_subject(client, admin_headers, code="CS375", weekly_hours=8)
        aid = post(client, admin_headers, subject_id=sid, faculty_id=fid).get_json()["data"]["id"]
        client.put(f"/api/v1/faculty/{fid}/availability", json={"entries": []}, headers=admin_headers)
        assert client.get(f"{URL}/{aid}", headers=admin_headers).get_json()["data"]["warnings"] == []
