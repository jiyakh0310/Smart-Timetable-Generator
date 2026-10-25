"""R16 - approval and publishing workflow: Admin-only, re-validated on every step, one current published version per term.

Statuses: draft | validated -> (submit) -> pending_approval -> (approve) -> approved -> (publish) -> published -> archived (when superseded);
reject: pending_approval | approved -> rejected -> (edit, submit again).
"""
import logging
from datetime import date

import pytest

from app.extensions import db
from app.models import AcademicTerm, Faculty, Room, TermType, Timetable, TimetableEntry, TimetableStatus, UnscheduledItem
from app.modules.jiya import approval_service, timetable_service, validation_service
from app.tests.jiya.test_generation import EMPTY, admin_id, counts, disable_slots, entries, gen, term
from app.tests.jiya.test_validation import first_entry, refresh
from app.tests.pragya.helpers import faculty

URL = "/api/v1/timetables"
S = TimetableStatus


@pytest.fixture()
def data(app, seeded):
    return None


@pytest.fixture()
def tt(data):
    return gen()["id"]


def act(client, headers, tid, action, **body):
    return client.post(f"{URL}/{tid}/{action}", json=body, headers=headers)


def ok(client, headers, tid, action, **body):
    r = act(client, headers, tid, action, **body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def advance(client, headers, tid, to):
    """Walk a timetable through the real API up to a status."""
    path = {"pending_approval": ["submit"], "approved": ["submit", "approve"], "published": ["submit", "approve", "publish"]}[to]
    for a in path:
        ok(client, headers, tid, a)
    assert refresh(tid).status.value == to


def snapshot(tid):
    return sorted((e.id, e.assignment_id, e.room_id, e.time_slot_id) for e in entries(tid))


def break_a_room(tid):
    first_entry(tid, "CS301", "A").room.is_available = False
    db.session.commit()


def refused(client, headers, tid, action, code, status=409, **body):
    r = act(client, headers, tid, action, **body)
    assert r.status_code == status and r.get_json()["error"]["code"] == code, r.get_json()
    return r.get_json()["error"]


class TestHappyPath:
    def test_submit_approve_publish(self, client, admin_headers, tt):
        before = snapshot(tt)
        sub = ok(client, admin_headers, tt, "submit")
        assert sub["timetable"]["status"] == "pending_approval" and sub["validation"]["validation_passed"] is True
        app_ = ok(client, admin_headers, tt, "approve")
        t = app_["timetable"]
        assert t["status"] == "approved" and t["approved_by"] == admin_id() and t["approved_at"] and t["published_at"] is None
        pub = ok(client, admin_headers, tt, "publish")
        t = pub["timetable"]
        assert t["status"] == "published" and t["published_at"] and t["is_current_published"] is True and t["validation_passed"] is True and pub["superseded"] == []
        assert snapshot(tt) == before and refresh(tt).version == 1 and counts()["Timetable"] == 1

    def test_the_response_carries_the_fresh_validation_report(self, client, admin_headers, tt):
        rep = ok(client, admin_headers, tt, "submit")["validation"]
        assert rep["is_complete"] and rep["counts"]["required_sessions"] == 32 and rep["hard_errors"] == []

    def test_a_draft_that_was_never_validated_can_be_submitted_because_the_server_validates(self, client, admin_headers, tt):
        assert refresh(tt).validation_passed is False and refresh(tt).validated_at is None
        ok(client, admin_headers, tt, "submit")
        assert refresh(tt).validation_passed is True and refresh(tt).validated_at is not None

    def test_allowed_actions_follow_the_status(self, client, admin_headers, tt):
        def allowed():
            return client.get(f"{URL}/{tt}", headers=admin_headers).get_json()["data"]["allowed_actions"]
        assert allowed() == ["submit"]
        ok(client, admin_headers, tt, "submit")
        assert allowed() == ["approve", "reject"]
        ok(client, admin_headers, tt, "approve")
        assert allowed() == ["reject", "publish"]
        ok(client, admin_headers, tt, "publish")
        assert allowed() == []

    def test_each_transition_is_logged(self, client, admin_headers, tt, caplog):
        with caplog.at_level(logging.INFO):
            advance(client, admin_headers, tt, "published")
        lines = [r.getMessage() for r in caplog.records if "timetable_transition" in r.getMessage()]
        assert [(" action=submit " in l, " action=approve " in l, " action=publish " in l) for l in lines] == [(True, False, False), (False, True, False), (False, False, True)]
        assert all(f"timetable={tt}" in l and f"user={admin_id()}" in l for l in lines)
        assert "from=approved to=published" in lines[-1]


class TestValidationGate:
    def test_an_incomplete_timetable_cannot_be_submitted(self, client, admin_headers, data):
        disable_slots(lambda s: s.day_of_week > 1)
        tid = gen()["id"]
        err = refused(client, admin_headers, tid, "submit", "validation_failed")
        rep = err["details"]["validation"]
        assert rep["is_complete"] is False and rep["counts"]["unscheduled_sessions"] > 0 and rep["unscheduled"][0]["reason_text"]
        assert "not scheduled" in err["message"]
        t = refresh(tid)
        assert t.status == S.DRAFT and t.validation_passed is False and t.approved_by is None and t.published_at is None

    def test_a_hard_conflict_blocks_submit(self, client, admin_headers, tt):
        break_a_room(tt)
        err = refused(client, admin_headers, tt, "submit", "validation_failed")
        assert any(c["code"] == "room_unavailable" for c in err["details"]["validation"]["hard_errors"]) and "hard error" in err["message"]
        assert refresh(tt).status == S.DRAFT

    def test_a_stale_valid_flag_is_not_trusted_at_submit(self, client, admin_headers, tt):
        client.post(f"{URL}/{tt}/validate", headers=admin_headers)
        assert refresh(tt).validation_passed is True and refresh(tt).status == S.VALIDATED
        break_a_room(tt)  # nothing re-validated: the stored flag still says True
        assert refresh(tt).validation_passed is True
        refused(client, admin_headers, tt, "submit", "validation_failed")
        t = refresh(tt)
        assert t.validation_passed is False and t.status == S.DRAFT  # the honest result was stored

    def test_a_stale_valid_flag_is_not_trusted_at_approval(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        break_a_room(tt)
        refused(client, admin_headers, tt, "approve", "validation_failed")
        t = refresh(tt)
        assert t.status == S.PENDING_APPROVAL and t.validation_passed is False and t.approved_by is None

    def test_a_stale_valid_flag_is_not_trusted_at_publication(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "approved")
        break_a_room(tt)
        refused(client, admin_headers, tt, "publish", "validation_failed")
        t = refresh(tt)
        assert t.status == S.APPROVED and t.published_at is None and t.validation_passed is False

    def test_workload_overflow_blocks_submit_and_publish(self, client, admin_headers, tt):
        faculty("F001").max_weekly_hours = 8  # the saved timetable has F001 at 10 h
        db.session.commit()
        err = refused(client, admin_headers, tt, "submit", "validation_failed")
        assert any(c["code"] == "workload_exceeded" for c in err["details"]["validation"]["hard_errors"])
        faculty("F001").max_weekly_hours = 18
        db.session.commit()
        advance(client, admin_headers, tt, "approved")
        faculty("F001").max_weekly_hours = 8
        db.session.commit()
        err = refused(client, admin_headers, tt, "publish", "validation_failed")
        assert any(c["code"] == "workload_exceeded" for c in err["details"]["validation"]["hard_errors"])
        assert refresh(tt).status == S.APPROVED

    def test_a_refused_publication_changes_nothing_else(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        second = gen()["id"]
        advance(client, admin_headers, second, "approved")
        break_a_room(second)
        refused(client, admin_headers, second, "publish", "validation_failed")
        assert refresh(tt).status == S.PUBLISHED and refresh(second).status == S.APPROVED  # the current version is untouched

    def test_a_crash_while_validating_changes_nothing(self, client, admin_headers, tt, monkeypatch):
        monkeypatch.setattr(validation_service, "evaluate", lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
        assert act(client, admin_headers, tt, "submit").status_code == 500
        t = refresh(tt)
        assert t.status == S.DRAFT and t.validated_at is None


STATUSES = [S.DRAFT, S.VALIDATED, S.PENDING_APPROVAL, S.APPROVED, S.PUBLISHED, S.REJECTED, S.ARCHIVED]
ACTIONS = ["submit", "approve", "reject", "publish"]


class TestIllegalTransitions:
    @pytest.mark.parametrize("action", ACTIONS)
    @pytest.mark.parametrize("status", STATUSES)
    def test_every_status_action_pair(self, client, admin_headers, tt, status, action):
        t = refresh(tt)
        t.status = status
        db.session.commit()
        allowed_from = timetable_service.TRANSITIONS[action][0]
        body = {"reason": "Needs another look at Friday."} if action == "reject" else {}
        before = snapshot(tt)
        r = act(client, admin_headers, tt, action, **body)
        if status in allowed_from:
            assert r.status_code == 200, (status, action, r.get_json())
        else:
            assert r.status_code == 409 and r.get_json()["error"]["code"] == "illegal_transition"
            assert r.get_json()["error"]["details"]["status"] == status.value
            assert refresh(tt).status == status and refresh(tt).approved_by is None and refresh(tt).published_at is None
        assert snapshot(tt) == before

    def test_the_message_says_what_to_do(self, client, admin_headers, tt):
        err = refused(client, admin_headers, tt, "publish", "illegal_transition")
        assert "draft timetable cannot be published" in err["message"] and "approved first" in err["message"]

    def test_approving_twice_fails_the_second_time(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        ok(client, admin_headers, tt, "approve")
        refused(client, admin_headers, tt, "approve", "illegal_transition")

    def test_unknown_timetable(self, client, admin_headers, data):
        for a in ACTIONS:
            assert act(client, admin_headers, 9999, a, **({"reason": "xxxxxx"} if a == "reject" else {})).status_code == 404


class TestRejection:
    def test_reject_with_a_reason_from_pending(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        t = ok(client, admin_headers, tt, "reject", reason="  Friday  labs clash with the seminar.  ")["timetable"]
        assert t["status"] == "rejected" and t["rejection_reason"] == "Friday labs clash with the seminar." and t["approved_by"] is None

    def test_an_approval_can_be_withdrawn(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "approved")
        t = ok(client, admin_headers, tt, "reject", reason="Approved by mistake.")["timetable"]
        assert t["status"] == "rejected" and t["approved_at"] is None and t["approved_by"] is None

    @pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "    "}, {"reason": "abc"}, {"reason": "x" * 501}, {"reason": 5}])
    def test_a_reason_is_required(self, client, admin_headers, tt, body):
        advance(client, admin_headers, tt, "pending_approval")
        r = act(client, admin_headers, tt, "reject", **body)
        assert r.status_code == 400 and r.get_json()["error"]["details"]["reason"]
        assert refresh(tt).status == S.PENDING_APPROVAL and refresh(tt).rejection_reason is None

    def test_unknown_fields_are_refused(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        assert act(client, admin_headers, tt, "reject", reason="Not good enough.", status="published").status_code == 400

    def test_a_rejected_timetable_can_be_fixed_and_submitted_again(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        ok(client, admin_headers, tt, "reject", reason="Move CS301 away from Monday.")
        e = first_entry(tt, "CS301", "A")
        opts = client.get(f"{URL}/{tt}/entries/{e.id}/edit-options", headers=admin_headers)
        assert opts.status_code == 200
        target = next(o for o in opts.get_json()["data"]["options"] if not o["is_current"])
        edit = client.patch(f"{URL}/{tt}/entries/{e.id}", json={"time_slot_id": target["time_slot_id"], "room_id": target["rooms"][0]["id"]}, headers=admin_headers)
        assert edit.status_code == 200 and refresh(tt).status == S.REJECTED  # still rejected until it is submitted again
        t = ok(client, admin_headers, tt, "submit")["timetable"]
        assert t["status"] == "pending_approval" and t["rejection_reason"] is None

    def test_a_rejected_timetable_can_be_discarded(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        ok(client, admin_headers, tt, "reject", reason="Start again please.")
        assert client.delete(f"{URL}/{tt}", headers=admin_headers).status_code == 200 and counts() == EMPTY


class TestImmutability:
    @pytest.mark.parametrize("to", ["pending_approval", "approved", "published"])
    def test_cannot_be_edited_or_discarded(self, client, admin_headers, tt, to):
        advance(client, admin_headers, tt, to)
        e = first_entry(tt, "CS301", "A")
        before = snapshot(tt)
        assert client.patch(f"{URL}/{tt}/entries/{e.id}", json={"room_id": Room.query.filter_by(code="R202").one().id}, headers=admin_headers).json["error"]["code"] == "timetable_not_editable"
        assert client.get(f"{URL}/{tt}/entries/{e.id}/edit-options", headers=admin_headers).status_code == 409
        r = client.delete(f"{URL}/{tt}", headers=admin_headers)
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "timetable_not_draft"
        assert snapshot(tt) == before and refresh(tt).status.value == to
        detail = client.get(f"{URL}/{tt}", headers=admin_headers).get_json()["data"]
        assert detail["can_edit"] is False and detail["can_discard"] is False

    def test_an_archived_timetable_is_final(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        newer = gen()["id"]
        advance(client, admin_headers, newer, "published")
        assert refresh(tt).status == S.ARCHIVED
        for a in ACTIONS:
            assert act(client, admin_headers, tt, a, **({"reason": "xxxxxx"} if a == "reject" else {})).status_code == 409
        assert client.delete(f"{URL}/{tt}", headers=admin_headers).status_code == 409
        assert len(entries(tt)) == 36

    def test_a_published_timetable_is_not_changed_by_generating_a_new_version(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        before = snapshot(tt)
        published_at = refresh(tt).published_at
        new = gen()
        assert new["version"] == 2 and new["status"] == "draft"
        assert snapshot(tt) == before and refresh(tt).status == S.PUBLISHED and refresh(tt).published_at == published_at

    def test_the_setup_data_stays_protected_while_a_timetable_is_published(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        a_id = first_entry(tt).assignment_id
        assert client.delete(f"/api/v1/teaching-assignments/{a_id}", headers=admin_headers).status_code == 409

    def test_validating_a_published_timetable_never_changes_its_status(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        break_a_room(tt)
        rep = client.post(f"{URL}/{tt}/validate", headers=admin_headers).get_json()["data"]
        assert rep["validation_passed"] is False and refresh(tt).status == S.PUBLISHED  # truth is recorded, status is not touched


class TestVersionsAndCurrentPublished:
    def test_publishing_a_newer_version_archives_the_old_one_and_keeps_its_history(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        before = snapshot(tt)
        new = gen()["id"]
        advance(client, admin_headers, new, "approved")
        result = ok(client, admin_headers, new, "publish")
        assert result["superseded"] == [tt]
        assert refresh(tt).status == S.ARCHIVED and refresh(new).status == S.PUBLISHED
        assert snapshot(tt) == before                       # the old version's rows are preserved
        assert refresh(tt).published_at is not None and refresh(tt).approved_by == admin_id()  # and so is its history

    def test_there_is_exactly_one_current_published_version_per_term(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "published")
        for _ in range(2):
            n = gen()["id"]
            advance(client, admin_headers, n, "published")
        rows = client.get(f"{URL}?term_id={term().id}", headers=admin_headers).get_json()["data"]["items"]
        assert [r["version"] for r in rows] == [3, 2, 1]
        assert [r["status"] for r in rows] == ["published", "archived", "archived"]
        assert [r["is_current_published"] for r in rows] == [True, False, False]
        assert Timetable.query.filter_by(status=S.PUBLISHED).count() == 1

    def test_another_terms_published_version_is_left_alone(self, client, admin_headers, tt):
        other = AcademicTerm(name="Spring 2027", academic_year="2026-27", term_type=TermType.EVEN, start_date=date(2027, 1, 1), end_date=date(2027, 5, 1), is_active=False)
        db.session.add(other)
        db.session.commit()
        elsewhere = Timetable(term_id=other.id, name="Spring v1", version=1, status=S.PUBLISHED, validation_passed=True, generated_by=admin_id())
        db.session.add(elsewhere)
        db.session.commit()
        advance(client, admin_headers, tt, "published")
        assert refresh(elsewhere.id).status == S.PUBLISHED and Timetable.query.filter_by(status=S.PUBLISHED).count() == 2

    def test_publishing_an_older_approved_version_after_a_newer_one_makes_it_current(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "approved")
        newer = gen()["id"]
        advance(client, admin_headers, newer, "published")
        assert ok(client, admin_headers, tt, "publish")["superseded"] == [newer]  # the last publication wins, history is kept
        assert refresh(tt).status == S.PUBLISHED and refresh(newer).status == S.ARCHIVED

    def test_version_numbers_never_change_with_status(self, client, admin_headers, tt):
        versions = {tt: 1}
        n = gen()
        versions[n["id"]] = n["version"]
        advance(client, admin_headers, tt, "published")
        advance(client, admin_headers, n["id"], "published")
        assert {i: refresh(i).version for i in versions} == versions


class TestConcurrencySafety:
    def test_a_second_request_for_the_same_step_cannot_repeat_it(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "pending_approval")
        first, second = act(client, admin_headers, tt, "approve"), act(client, admin_headers, tt, "approve")
        assert (first.status_code, second.status_code) == (200, 409)
        assert second.get_json()["error"]["code"] == "illegal_transition"

    def test_a_request_made_from_a_stale_view_is_checked_against_the_current_status(self, client, admin_headers, tt):
        advance(client, admin_headers, tt, "approved")  # another admin tab already approved it
        refused(client, admin_headers, tt, "submit", "illegal_transition")
        refused(client, admin_headers, tt, "approve", "illegal_transition")

    def test_a_failure_after_the_old_version_was_archived_rolls_everything_back(self, client, admin_headers, tt, monkeypatch):
        advance(client, admin_headers, tt, "published")
        newer = gen()["id"]
        advance(client, admin_headers, newer, "approved")

        class Boom:
            logger = type("L", (), {"info": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("log failure")))})()
        monkeypatch.setattr(approval_service, "current_app", Boom)
        assert act(client, admin_headers, newer, "publish").status_code == 500
        assert refresh(tt).status == S.PUBLISHED and refresh(newer).status == S.APPROVED and refresh(newer).published_at is None
        assert Timetable.query.filter_by(status=S.PUBLISHED).count() == 1


class TestPermissions:
    def test_login_is_required(self, client, tt):
        for a in ACTIONS:
            assert client.post(f"{URL}/{tt}/{a}", json={}).status_code == 401

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers"])
    def test_faculty_and_students_can_do_nothing_with_timetables(self, client, request, tt, who):
        headers = request.getfixturevalue(who)
        admin = request.getfixturevalue("admin_headers")
        advance(client, admin, tt, "published")
        draft = gen()["id"]
        before = (refresh(tt).status, refresh(draft).status)
        for a in ACTIONS:
            assert act(client, headers, draft, a, **({"reason": "not my call"} if a == "reject" else {})).status_code == 403
            assert act(client, headers, tt, a, **({"reason": "not my call"} if a == "reject" else {})).status_code == 403
        for path in (URL, f"{URL}/{tt}", f"{URL}/{draft}", f"{URL}?status=published", f"{URL}/workload-preview?term_id={term().id}"):
            assert client.get(path, headers=headers).status_code == 403   # neither drafts nor the published version are exposed here
        assert client.patch(f"{URL}/{tt}/entries/{first_entry(tt).id}", json={"room_id": 1}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{draft}", headers=headers).status_code == 403
        db.session.expire_all()
        assert (refresh(tt).status, refresh(draft).status) == before
