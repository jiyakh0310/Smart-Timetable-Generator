"""Pragya - R8/R9 HTTP endpoints: /conflicts/check, /conflicts/validate, /rooms/suggest."""
import pytest

from app.extensions import db
from app.models import AvailabilityStatus, FacultyAvailability
from app.tests.pragya.helpers import assignment, batch, faculty, new_timetable, place, room, sid, subject

MISSING = object()
CHECK = "/api/v1/conflicts/check"
VALIDATE = "/api/v1/conflicts/validate"
SUGGEST = "/api/v1/rooms/suggest"


def check(client, headers, **body):
    return client.post(CHECK, json=body, headers=headers)


def theory_body(**over):
    data = {"faculty_id": faculty().id, "batch_id": batch("A").id, "subject_id": subject("CS301").id, "room_id": room("R201").id, "time_slot_ids": [sid(0, 1)]}
    data.update(over)
    return data


class TestPermissions:
    def test_requires_login(self, client, seeded):
        assert client.post(CHECK, json={}).status_code == 401
        assert client.get(f"{VALIDATE}?timetable_id=1").status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_non_admins_are_refused(self, client, request, who):
        headers = request.getfixturevalue(who)
        assert client.post(CHECK, json=theory_body(), headers=headers).status_code == 403
        assert client.get(f"{VALIDATE}?timetable_id=1", headers=headers).status_code == 403


class TestCheckEndpoint:
    def test_a_valid_placement_is_ok(self, client, admin_headers):
        data = check(client, admin_headers, **theory_body()).get_json()["data"]
        assert data == {"ok": True, "hard_count": 0, "advisory_count": 0, "conflicts": []}

    def test_hard_conflicts_make_it_not_ok_and_are_listed_first(self, client, admin_headers):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        db.session.add(FacultyAvailability(faculty_id=faculty("F002").id, time_slot_id=sid(1, 1), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        data = check(client, admin_headers, **theory_body(timetable_id=t.id)).get_json()["data"]
        assert data["ok"] is False and data["hard_count"] == 3
        assert {c["code"] for c in data["conflicts"]} == {"batch_clash", "faculty_clash", "room_clash"}
        assert all(c["severity"] == "hard" and c["message"] for c in data["conflicts"])

    def test_a_soft_preference_alone_leaves_the_placement_ok(self, client, admin_headers):
        db.session.add(FacultyAvailability(faculty_id=faculty().id, time_slot_id=sid(1, 1), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        data = check(client, admin_headers, **theory_body()).get_json()["data"]
        assert data["ok"] is True and data["hard_count"] == 0 and data["advisory_count"] == 1
        assert data["conflicts"][0]["severity"] == "advisory" and data["conflicts"][0]["code"] == "outside_preferred_slots"

    def test_hard_unavailability_is_not_ok(self, client, admin_headers):
        db.session.add(FacultyAvailability(faculty_id=faculty().id, time_slot_id=sid(0, 1), status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        data = check(client, admin_headers, **theory_body()).get_json()["data"]
        assert data["ok"] is False and data["conflicts"][0]["code"] == "faculty_unavailable"

    def test_back_to_back_with_an_existing_class_is_ok(self, client, admin_headers):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        assert check(client, admin_headers, **theory_body(timetable_id=t.id, time_slot_ids=[sid(0, 2)])).get_json()["data"]["ok"] is True

    def test_ignore_entry_ids_supports_moving_an_existing_class(self, client, admin_headers):
        t = new_timetable()
        entry = place(t, assignment("A", "CS301"), "R201", 0, 1)
        assert check(client, admin_headers, **theory_body(timetable_id=t.id)).get_json()["data"]["ok"] is False
        assert check(client, admin_headers, **theory_body(timetable_id=t.id, ignore_entry_ids=[entry.id])).get_json()["data"]["ok"] is True

    def test_lab_session_rules_over_http(self, client, admin_headers):
        lab = dict(faculty_id=faculty().id, batch_id=batch("A").id, subject_id=subject("CS351").id, room_id=room("LAB1").id)
        assert check(client, admin_headers, **lab, time_slot_ids=[sid(0, 1), sid(0, 2)]).get_json()["data"]["ok"] is True
        split = check(client, admin_headers, **lab, time_slot_ids=[sid(0, 3), sid(0, 5)]).get_json()["data"]
        assert split["ok"] is False and split["conflicts"][0]["code"] == "not_consecutive"
        short = check(client, admin_headers, **lab, time_slot_ids=[sid(0, 1)]).get_json()["data"]
        assert short["conflicts"][0]["code"] == "wrong_session_length"

    def test_an_assignment_id_supplies_faculty_batch_and_subject(self, client, admin_headers):
        a = assignment("A", "CS351")
        ok = check(client, admin_headers, assignment_id=a.id, room_id=room("LAB1").id, time_slot_ids=[sid(0, 1), sid(0, 2)]).get_json()["data"]
        assert ok["ok"] is True
        wrong_room = check(client, admin_headers, assignment_id=a.id, room_id=room("R201").id, time_slot_ids=[sid(0, 1), sid(0, 2)]).get_json()["data"]
        assert wrong_room["conflicts"][0]["code"] == "room_type_mismatch"

    def test_an_assignment_id_that_contradicts_explicit_ids_is_400(self, client, admin_headers):
        a = assignment("A", "CS351")
        response = check(client, admin_headers, assignment_id=a.id, faculty_id=faculty("F006").id, room_id=room("LAB1").id, time_slot_ids=[sid(0, 1), sid(0, 2)])
        assert response.status_code == 400 and "faculty_id" in response.get_json()["error"]["details"]

    @pytest.mark.parametrize(
        "mutation, field",
        [({"room_id": MISSING}, "room_id"), ({"room_id": "x"}, "room_id"), ({"room_id": True}, "room_id"), ({"time_slot_ids": []}, "time_slot_ids"),
         ({"time_slot_ids": MISSING}, "time_slot_ids"), ({"time_slot_ids": "1"}, "time_slot_ids"), ({"time_slot_ids": [1, "2"]}, "time_slot_ids"),
         ({"faculty_id": MISSING}, "faculty_id"), ({"batch_id": 0}, "batch_id"), ({"ignore_entry_ids": "3"}, "ignore_entry_ids"),
         ({"colour": "red"}, "colour"), ({"assignment_id": 999999}, "assignment_id")],
    )
    def test_invalid_input_is_400_with_the_offending_field(self, client, admin_headers, mutation, field):
        body = {**theory_body(), **mutation}
        body = {k: v for k, v in body.items() if v is not MISSING}  # MISSING = leave the key out of the request
        response = client.post(CHECK, json=body, headers=admin_headers)
        assert response.status_code == 400 and field in response.get_json()["error"]["details"]

    def test_unknown_records_are_400_and_unknown_timetables_404(self, client, admin_headers):
        assert check(client, admin_headers, **theory_body(room_id=99999)).status_code == 400
        assert check(client, admin_headers, **theory_body(timetable_id=99999)).status_code == 404
        assert client.post(CHECK, data="nope", headers=admin_headers).status_code == 400

    def test_checking_never_changes_the_timetable(self, client, admin_headers):
        from app.models import TimetableEntry
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        before = TimetableEntry.query.count()
        check(client, admin_headers, **theory_body(timetable_id=t.id, room_id=room("R202").id, time_slot_ids=[sid(0, 3)]))
        assert TimetableEntry.query.count() == before


class TestValidateEndpoint:
    def test_a_clean_timetable(self, client, admin_headers):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        data = client.get(f"{VALIDATE}?timetable_id={t.id}", headers=admin_headers).get_json()["data"]
        assert data == {"timetable_id": t.id, "is_valid": True, "hard_count": 0, "advisory_count": 0, "conflicts": []}

    def test_problems_make_it_invalid_and_advisories_do_not(self, client, admin_headers):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "LAB1", 0, 1)  # theory class in a lab
        db.session.add(FacultyAvailability(faculty_id=faculty("F001").id, time_slot_id=sid(1, 1), status=AvailabilityStatus.PREFERRED))
        db.session.commit()
        data = client.get(f"{VALIDATE}?timetable_id={t.id}", headers=admin_headers).get_json()["data"]
        assert data["is_valid"] is False and data["hard_count"] == 1 and data["advisory_count"] == 1
        assert data["conflicts"][0]["severity"] == "hard"  # hard conflicts are listed first

    def test_validation_errors(self, client, admin_headers):
        assert client.get(VALIDATE, headers=admin_headers).status_code == 400
        assert client.get(f"{VALIDATE}?timetable_id=abc", headers=admin_headers).status_code == 400
        assert client.get(f"{VALIDATE}?timetable_id=99999", headers=admin_headers).status_code == 404


class TestSuggestEndpoint:
    def _url(self, batch_section="A", subject_code="CS301", slots=((0, 1),), **extra):
        ids = ",".join(str(sid(d, p)) for d, p in slots)
        qs = f"batch_id={batch(batch_section).id}&subject_id={subject(subject_code).id}&time_slot_ids={ids}"
        return f"{SUGGEST}?{qs}" + "".join(f"&{k}={v}" for k, v in extra.items())

    def test_suitable_rooms_smallest_first_with_reasons_for_the_rest(self, client, admin_headers):
        data = client.get(self._url(), headers=admin_headers).get_json()["data"]
        assert [r["code"] for r in data["suitable"]] == ["R201", "R202"]
        assert data["suitable"][0]["spare_seats"] == 2 and data["suitable"][1]["spare_seats"] == 12
        reasons = {r["code"]: [x["code"] for x in r["reasons"]] for r in data["excluded"]}
        assert reasons["R102"] == ["room_too_small"] and reasons["LAB1"] == ["room_type_mismatch"] and reasons["SEM1"] == ["room_type_mismatch"]
        assert data["batch"]["strength"] == 58 and data["subject"]["class_type"] == "theory" and data["slot_problems"] == []

    def test_labs_get_laboratories(self, client, admin_headers):
        data = client.get(self._url("B", "CS351", ((0, 1), (0, 2))), headers=admin_headers).get_json()["data"]
        assert [r["code"] for r in data["suitable"]] == ["LAB2", "LAB1"]

    def test_a_room_in_use_in_that_period_is_excluded_with_a_clash_reason(self, client, admin_headers):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)
        data = client.get(self._url(timetable_id=t.id), headers=admin_headers).get_json()["data"]
        assert [r["code"] for r in data["suitable"]] == ["R202"]
        assert {r["code"]: [x["code"] for x in r["reasons"]] for r in data["excluded"]}["R201"] == ["room_clash"]
        assert [r["code"] for r in client.get(self._url(slots=((0, 2),), timetable_id=t.id), headers=admin_headers).get_json()["data"]["suitable"]] == ["R201", "R202"]

    def test_a_break_slot_means_no_room_is_suggested(self, client, admin_headers):
        data = client.get(self._url(slots=((0, 4),)), headers=admin_headers).get_json()["data"]
        assert data["suitable"] == [] and data["slot_problems"][0]["code"] == "slot_is_break"

    @pytest.mark.parametrize("qs", ["", "batch_id=1", "batch_id=999&subject_id=1&time_slot_ids=1", "batch_id=1&subject_id=1", "batch_id=1&subject_id=1&time_slot_ids=a,b", "batch_id=1&subject_id=1&time_slot_ids="])
    def test_bad_input_is_400(self, client, admin_headers, qs):
        assert client.get(f"{SUGGEST}?{qs}", headers=admin_headers).status_code == 400

    def test_unknown_timetable_is_404(self, client, admin_headers):
        assert client.get(self._url(timetable_id=99999), headers=admin_headers).status_code == 404
