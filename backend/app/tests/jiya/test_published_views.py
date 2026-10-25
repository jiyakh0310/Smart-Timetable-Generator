"""R11 / R12 - Faculty and Student read-only views of the current published timetable.

Seed: F001 teaches 8 theory sessions (CS301 for A and B) + 1 two-period lab (CS351 for A) = 9 sessions / 10 periods;
each batch has 16 sessions (14 theory + 2 labs), but taught by different teachers. faculty1..6 and student1..4 (1,2 = batch A; 3,4 = batch B).
"""
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import AcademicTerm, Role, Student, TermType, Timetable, TimetableEntry, TimetableStatus, User
from app.tests.conftest import auth_header, login, make_user
from app.tests.jiya.test_generation import admin_id, entries, gen, term
from app.tests.jiya.test_validation import first_entry, refresh

FAC = "/api/v1/faculty/timetable"
STU = "/api/v1/student/timetable"
URL = "/api/v1/timetables"
S = TimetableStatus


@pytest.fixture()
def data(app, seeded):
    return None


def publish(client, admin, tid):
    for a in ("submit", "approve", "publish"):
        r = client.post(f"{URL}/{tid}/{a}", json={}, headers=admin)
        assert r.status_code == 200, r.get_json()


@pytest.fixture()
def published(client, admin_headers):
    tid = gen()["id"]
    publish(client, admin_headers, tid)
    return tid


def token_for(client, email, password):
    return {"Authorization": f"Bearer {login(client, email, password).get_json()['data']['token']}"}


def as_(client, email):
    return auth_header(client, f"{email}@timetable.test")


def body(response):
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def codes(view):
    return sorted(s["subject"]["code"] for s in view["sessions"])


class TestFacultyView:
    def test_own_classes_only(self, client, published):
        view = body(client.get(FAC, headers=as_(client, "faculty1")))
        assert view["owner"]["employee_code"] == "F001" and view["term"]["is_active"] is True
        assert len(view["sessions"]) == 9 and codes(view).count("CS301") == 8 and codes(view).count("CS351") == 1
        assert {s["batch"]["name"] for s in view["sessions"]} == {"CSE Sem 3 - A", "CSE Sem 3 - B"}
        assert sum(s["periods"] for s in view["sessions"]) == 10

    def test_each_teacher_sees_a_different_schedule(self, client, published):
        f1 = body(client.get(FAC, headers=as_(client, "faculty1")))
        f5 = body(client.get(FAC, headers=as_(client, "faculty5")))
        assert codes(f5) == ["CS303"] * 3 and f1["sessions"] != f5["sessions"]
        assert all("CS303" not in c for c in codes(f1))

    def test_the_lab_is_one_session_of_two_consecutive_periods(self, client, published):
        view = body(client.get(FAC, headers=as_(client, "faculty1")))
        lab = next(s for s in view["sessions"] if s["subject"]["class_type"] == "lab")
        assert lab["periods"] == 2
        periods = {(s["day_of_week"], s["period_no"]): s for s in view["slots"]}
        assert lab["end_time"] == periods[(lab["day_of_week"], lab["period_no"] + 1)]["end_time"]
        assert lab["room"]["code"].startswith("LAB")

    def test_the_view_includes_the_week_structure_with_breaks(self, client, published):
        view = body(client.get(FAC, headers=as_(client, "faculty1")))
        assert any(s["slot_type"] == "break" for s in view["slots"]) and {s["day_of_week"] for s in view["slots"]} == {0, 1, 2, 3, 4}

    def test_a_teacher_with_no_classes_gets_an_empty_but_published_view(self, client, published):
        make_user("loner@timetable.test", Role.FACULTY, "Password123")
        from app.models import Faculty
        dept = db.session.scalar(db.select(Faculty.department_id))
        user = db.session.scalar(db.select(User).filter_by(email="loner@timetable.test"))
        db.session.add(Faculty(user_id=user.id, employee_code="F900", department_id=dept, max_weekly_hours=10))
        db.session.commit()
        view = body(client.get(FAC, headers=token_for(client, "loner@timetable.test", "Password123")))
        assert view["timetable"] is not None and view["sessions"] == []

    def test_a_faculty_account_without_a_faculty_record(self, client, published):
        make_user("norecord@timetable.test", Role.FACULTY, "Password123")
        r = client.get(FAC, headers=token_for(client, "norecord@timetable.test", "Password123"))
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "no_profile"


class TestStudentView:
    def test_own_batch_only(self, client, published):
        a = body(client.get(STU, headers=as_(client, "student1")))
        b = body(client.get(STU, headers=as_(client, "student3")))
        assert a["owner"]["batch"] == "CSE Sem 3 - A" and b["owner"]["batch"] == "CSE Sem 3 - B"
        assert len(a["sessions"]) == 16 and len(b["sessions"]) == 16
        assert "MA301" in codes(a) and a["sessions"] != b["sessions"]
        assert {s["faculty"]["name"] for s in a["sessions"]} != {s["faculty"]["name"] for s in b["sessions"]}  # different teachers per batch
        assert all("batch" not in s for s in a["sessions"])           # a student sees no other batch names
        assert {s["faculty"]["name"] for s in a["sessions"]} >= {"Dr. Rakesh Sharma"}

    def test_classmates_see_the_same_timetable(self, client, published):
        assert body(client.get(STU, headers=as_(client, "student1")))["sessions"] == body(client.get(STU, headers=as_(client, "student2")))["sessions"]

    def test_labs_are_one_two_period_session(self, client, published):
        view = body(client.get(STU, headers=as_(client, "student1")))
        labs = [s for s in view["sessions"] if s["subject"]["class_type"] == "lab"]
        assert len(labs) == 2 and all(s["periods"] == 2 for s in labs)
        assert sum(s["periods"] for s in view["sessions"]) == 14 + 4

    def test_the_view_has_no_internal_fields(self, client, published):
        view = body(client.get(STU, headers=as_(client, "student1")))
        assert set(view) == {"owner", "term", "terms", "timetable", "slots", "sessions"}
        assert set(view["timetable"]) == {"name", "version", "published_at"}
        text = json.dumps(view)
        for leak in ("validation_passed", "rejection_reason", "approved_by", "capacity", "generated_by", "email", "password"):
            assert leak not in text

    def test_a_student_account_without_a_student_record(self, client, published):
        make_user("norecord2@timetable.test", Role.STUDENT, "Password123")
        r = client.get(STU, headers=token_for(client, "norecord2@timetable.test", "Password123"))
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "no_profile"


class TestNothingUnpublishedIsEverShown:
    @pytest.mark.parametrize("status", [S.DRAFT, S.VALIDATED, S.PENDING_APPROVAL, S.APPROVED, S.REJECTED, S.ARCHIVED])
    def test_a_timetable_in_status_is_invisible(self, client, data, status):
        tid = gen()["id"]
        t = refresh(tid)
        t.status = status
        db.session.commit()
        for path, who in ((FAC, "faculty1"), (STU, "student1")):
            view = body(client.get(path, headers=as_(client, who)))
            assert view["timetable"] is None and view["sessions"] == [] and view["slots"] == []
            assert view["term"]["is_active"] is True and view["terms"] == []

    def test_no_timetable_at_all(self, client, data):
        for path, who in ((FAC, "faculty1"), (STU, "student1")):
            view = body(client.get(path, headers=as_(client, who)))
            assert view["timetable"] is None and view["sessions"] == []

    def test_a_draft_next_to_the_published_one_does_not_leak(self, client, admin_headers, published):
        draft = gen()["id"]
        e = first_entry(draft, "CS301", "A")
        before = body(client.get(STU, headers=as_(client, "student1")))
        slot = client.get(f"{URL}/{draft}/entries/{e.id}/edit-options", headers=admin_headers).get_json()["data"]["options"]
        target = next(o for o in slot if not o["is_current"])
        client.patch(f"{URL}/{draft}/entries/{e.id}", json={"time_slot_id": target["time_slot_id"], "room_id": target["rooms"][0]["id"]}, headers=admin_headers)
        assert body(client.get(STU, headers=as_(client, "student1"))) == before          # edits to a draft never show
        assert before["timetable"]["version"] == 1

    def test_superseded_versions_are_not_current(self, client, admin_headers, published):
        v2 = gen()["id"]
        publish(client, admin_headers, v2)
        assert refresh(published).status == S.ARCHIVED
        for path, who in ((FAC, "faculty1"), (STU, "student1")):
            assert body(client.get(path, headers=as_(client, who)))["timetable"]["version"] == 2

    def test_only_an_archived_version_means_no_current_timetable(self, client, published):
        refresh(published).status = S.ARCHIVED
        db.session.commit()
        view = body(client.get(STU, headers=as_(client, "student1")))
        assert view["timetable"] is None and view["terms"] == []

    def test_withdrawing_an_approval_before_publishing_shows_nothing(self, client, admin_headers, data):
        tid = gen()["id"]
        for a in ("submit", "approve"):
            client.post(f"{URL}/{tid}/{a}", json={}, headers=admin_headers)
        assert body(client.get(STU, headers=as_(client, "student1")))["timetable"] is None


class TestTerms:
    def _other_term(self, published_status=S.PUBLISHED, active=False):
        t = AcademicTerm(name="Spring 2027", academic_year="2026-27", term_type=TermType.EVEN, start_date=date(2027, 1, 1), end_date=date(2027, 5, 1), is_active=active)
        db.session.add(t)
        db.session.commit()
        tt = Timetable(term_id=t.id, name="Spring v1", version=1, status=published_status, generated_by=admin_id(), published_at=None)
        db.session.add(tt)
        db.session.commit()
        return t, tt

    def test_the_active_term_is_shown_by_default_and_others_can_be_chosen(self, client, published):
        other, tt = self._other_term()
        src = first_entry(published, "CS301", "A")
        db.session.add(TimetableEntry(timetable_id=tt.id, assignment_id=src.assignment_id, faculty_id=src.faculty_id, batch_id=src.batch_id, room_id=src.room_id, time_slot_id=src.time_slot_id))
        db.session.commit()
        default = body(client.get(STU, headers=as_(client, "student1")))
        assert default["term"]["id"] == term().id and len(default["sessions"]) == 16
        assert [t["id"] for t in default["terms"]] == [other.id, term().id]
        chosen = body(client.get(f"{STU}?term_id={other.id}", headers=as_(client, "student1")))
        assert chosen["term"]["id"] == other.id and len(chosen["sessions"]) == 1 and chosen["timetable"]["name"] == "Spring v1"

    def test_a_term_without_a_published_timetable_is_empty_not_an_error(self, client, published):
        other, _ = self._other_term(published_status=S.APPROVED)
        view = body(client.get(f"{STU}?term_id={other.id}", headers=as_(client, "student1")))
        assert view["timetable"] is None and view["sessions"] == [] and other.id not in [t["id"] for t in view["terms"]]

    def test_an_unknown_term_is_an_empty_view(self, client, published):
        view = body(client.get(f"{FAC}?term_id=9999", headers=as_(client, "faculty1")))
        assert view["timetable"] is None and view["term"] is None and view["sessions"] == []

    @pytest.mark.parametrize("raw", ["x", "0", "-1"])
    def test_a_bad_term_value_is_refused(self, client, published, raw):
        assert client.get(f"{STU}?term_id={raw}", headers=as_(client, "student1")).status_code == 400

    def test_the_active_term_without_a_published_timetable_is_empty_even_if_an_older_term_has_one(self, client, data):
        other, tt = self._other_term()          # published in a non-active term
        view = body(client.get(STU, headers=as_(client, "student1")))
        assert view["timetable"] is None and view["term"]["id"] == term().id and [t["id"] for t in view["terms"]] == [other.id]


class TestRequestingOtherPeoplesData:
    @pytest.mark.parametrize("param", ["faculty_id=2", "batch_id=2", "student_id=3", "timetable_id=1", "user_id=1", "employee_code=F005", "batch=B"])
    def test_identity_parameters_are_refused_for_a_student(self, client, published, param):
        r = client.get(f"{STU}?{param}", headers=as_(client, "student1"))
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"
        assert "sessions" not in json.dumps(r.get_json())

    @pytest.mark.parametrize("param", ["faculty_id=5", "batch_id=1", "user_id=1", "timetable_id=1", "employee_code=F005"])
    def test_identity_parameters_are_refused_for_faculty(self, client, published, param):
        r = client.get(f"{FAC}?{param}", headers=as_(client, "faculty1"))
        assert r.status_code == 400 and "sessions" not in json.dumps(r.get_json())

    def test_changing_a_students_batch_changes_what_they_see_only_after_the_admin_does_it(self, client, admin_headers, published):
        before = body(client.get(STU, headers=as_(client, "student1")))
        assert before["owner"]["batch"] == "CSE Sem 3 - A"
        student = db.session.scalar(db.select(Student).join(User).where(User.email == "student1@timetable.test"))
        from app.models import Batch
        student.batch_id = db.session.scalar(db.select(Batch.id).where(Batch.section == "B"))
        db.session.commit()
        after = body(client.get(STU, headers=as_(client, "student1")))
        assert after["owner"]["batch"] == "CSE Sem 3 - B" and after["sessions"] != before["sessions"]

    def test_a_faculty_member_cannot_use_the_student_view_or_the_reverse(self, client, published):
        assert client.get(STU, headers=as_(client, "faculty1")).status_code == 403
        assert client.get(FAC, headers=as_(client, "student1")).status_code == 403

    def test_admin_has_no_personal_view(self, client, admin_headers, published):
        assert client.get(FAC, headers=admin_headers).status_code == 403 and client.get(STU, headers=admin_headers).status_code == 403

    def test_login_is_required(self, client, published):
        assert client.get(FAC).status_code == 401 and client.get(STU).status_code == 401


class TestReadOnlyAndAdminUnchanged:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    @pytest.mark.parametrize("path,who", [(FAC, "faculty1"), (STU, "student1")])
    def test_only_get_exists(self, client, published, method, path, who):
        before = body(client.get(path, headers=as_(client, who)))
        r = getattr(client, method)(path, json={"status": "draft"}, headers=as_(client, who))
        assert r.status_code == 405
        assert body(client.get(path, headers=as_(client, who))) == before

    @pytest.mark.parametrize("who", ["faculty1", "student1"])
    def test_every_admin_timetable_endpoint_stays_forbidden(self, client, published, who):
        h = as_(client, who)
        e = first_entry(published, "CS301", "A")
        for method, path, payload in (
            ("get", URL, None), ("get", f"{URL}/{published}", None), ("post", f"{URL}/generate", {"term_id": term().id}), ("post", f"{URL}/{published}/validate", {}),
            ("post", f"{URL}/{published}/publish", {}), ("post", f"{URL}/{published}/reject", {"reason": "nope nope"}), ("delete", f"{URL}/{published}", None),
            ("patch", f"{URL}/{published}/entries/{e.id}", {"room_id": 1}), ("get", f"{URL}/{published}/entries/{e.id}/edit-options", None),
        ):
            r = getattr(client, method)(path, **({"json": payload} if payload is not None else {}), headers=h)
            assert r.status_code == 403, (method, path)
        assert refresh(published).status == S.PUBLISHED

    def test_publishing_still_works_and_is_what_makes_it_visible(self, client, admin_headers, data):
        tid = gen()["id"]
        assert body(client.get(STU, headers=as_(client, "student1")))["timetable"] is None
        publish(client, admin_headers, tid)
        assert len(body(client.get(STU, headers=as_(client, "student1")))["sessions"]) == 16
