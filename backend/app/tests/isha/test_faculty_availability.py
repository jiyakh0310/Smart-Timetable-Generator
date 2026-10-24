"""Isha - R13 Faculty availability and preferences API (ISH-TC09 .. ISH-TC12, Admin-managed)."""
import pytest

from app.extensions import db
from app.models import AvailabilityStatus, Faculty, FacultyAvailability, TimeSlot

FAC = "/api/v1/faculty"
SLOTS = "/api/v1/time-slots"


def faculty_id(code="F001"):
    return db.session.scalar(db.select(Faculty.id).where(Faculty.employee_code == code))


def slot_id(day, period):
    return db.session.scalar(db.select(TimeSlot.id).where(TimeSlot.day_of_week == day, TimeSlot.period_no == period))


def put(client, headers, entries, code="F001"):
    return client.put(f"{FAC}/{faculty_id(code)}/availability", json={"entries": entries}, headers=headers)


def get(client, headers, code="F001"):
    return client.get(f"{FAC}/{faculty_id(code)}/availability", headers=headers).get_json()["data"]


def status_of(data, day, period):
    return next(s["status"] for s in data["slots"] if s["day_of_week"] == day and s["period_no"] == period)


def entry(day, period, status):
    return {"time_slot_id": slot_id(day, period), "status": status}


class TestView:
    def test_shows_every_time_slot_defaulting_to_available(self, client, admin_headers):
        data = get(client, admin_headers)
        assert data["faculty"]["employee_code"] == "F001" and len(data["slots"]) == 35
        assert {s["status"] for s in data["slots"]} == {"available"}
        assert data["summary"] == {"unavailable": 0, "preferred": 0}
        first = data["slots"][0]
        assert (first["day_name"], first["period_no"], first["start_time"], first["end_time"], first["slot_type"], first["is_active"]) == ("Monday", 1, "09:00", "10:00", "class", True)
        assert [s["slot_type"] for s in data["slots"] if s["period_no"] == 4][0] == "break"

    def test_404_for_unknown_faculty(self, client, admin_headers):
        assert client.get(f"{FAC}/9999/availability", headers=admin_headers).status_code == 404
        assert client.put(f"{FAC}/9999/availability", json={"entries": []}, headers=admin_headers).status_code == 404


class TestSave:
    def test_ISH_TC09_add_availability_distinguishing_hard_unavailability_from_soft_preference(self, client, admin_headers):
        response = put(client, admin_headers, [entry(0, 1, "unavailable"), entry(0, 2, "unavailable"), entry(1, 3, "preferred")])
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["summary"] == {"unavailable": 2, "preferred": 1}
        assert status_of(data, 0, 1) == "unavailable" and status_of(data, 1, 3) == "preferred" and status_of(data, 2, 1) == "available"
        stored = {(r.time_slot_id, r.status) for r in FacultyAvailability.query.filter_by(faculty_id=faculty_id())}
        assert stored == {(slot_id(0, 1), AvailabilityStatus.UNAVAILABLE), (slot_id(0, 2), AvailabilityStatus.UNAVAILABLE), (slot_id(1, 3), AvailabilityStatus.PREFERRED)}

    def test_the_list_summarises_availability_per_faculty(self, client, admin_headers):
        put(client, admin_headers, [entry(0, 1, "unavailable"), entry(1, 3, "preferred")])
        items = client.get(FAC, headers=admin_headers).get_json()["data"]["items"]
        assert items[0]["availability"] == {"unavailable": 1, "preferred": 1}
        assert items[1]["availability"] == {"unavailable": 0, "preferred": 0}

    def test_ISH_TC10_update_availability_replaces_the_previous_settings(self, client, admin_headers):
        put(client, admin_headers, [entry(0, 1, "unavailable"), entry(1, 3, "preferred")])
        data = put(client, admin_headers, [entry(0, 1, "preferred"), entry(2, 5, "unavailable")]).get_json()["data"]
        assert status_of(data, 0, 1) == "preferred" and status_of(data, 2, 5) == "unavailable"
        assert status_of(data, 1, 3) == "available"  # not in the new list -> back to default
        assert FacultyAvailability.query.filter_by(faculty_id=faculty_id()).count() == 2

    def test_ISH_TC11_set_time_preferences_such_as_mornings(self, client, admin_headers):
        mornings = [entry(day, p, "preferred") for day in range(5) for p in (1, 2, 3)]
        data = put(client, admin_headers, mornings).get_json()["data"]
        assert data["summary"] == {"unavailable": 0, "preferred": 15}

    def test_sending_available_removes_the_row_and_an_empty_list_clears_everything(self, client, admin_headers):
        put(client, admin_headers, [entry(0, 1, "unavailable"), entry(0, 2, "preferred")])
        put(client, admin_headers, [entry(0, 1, "available"), entry(0, 2, "preferred")])
        assert FacultyAvailability.query.filter_by(faculty_id=faculty_id()).count() == 1
        assert put(client, admin_headers, []).get_json()["data"]["summary"] == {"unavailable": 0, "preferred": 0}
        assert FacultyAvailability.query.filter_by(faculty_id=faculty_id()).count() == 0

    def test_availability_is_per_faculty(self, client, admin_headers):
        put(client, admin_headers, [entry(0, 1, "unavailable")], code="F001")
        assert status_of(get(client, admin_headers, "F002"), 0, 1) == "available"

    @pytest.mark.parametrize("payload", [{}, {"entries": "x"}, {"entries": None}, {"entries": [], "extra": 1}])
    def test_malformed_bodies_are_400(self, client, admin_headers, payload):
        assert client.put(f"{FAC}/{faculty_id()}/availability", json=payload, headers=admin_headers).status_code == 400

    @pytest.mark.parametrize(
        "bad",
        [{"time_slot_id": 1}, {"status": "unavailable"}, {"time_slot_id": "1", "status": "unavailable"}, {"time_slot_id": True, "status": "unavailable"},
         {"time_slot_id": 1, "status": "busy"}, {"time_slot_id": 1, "status": "unavailable", "note": "x"}, "text", 5],
    )
    def test_ISH_TC12_invalid_entries_are_rejected_and_nothing_changes(self, client, admin_headers, bad):
        put(client, admin_headers, [entry(0, 1, "unavailable")])
        response = put(client, admin_headers, [bad])
        assert response.status_code == 400 and "entries.0" in response.get_json()["error"]["details"]
        assert FacultyAvailability.query.filter_by(faculty_id=faculty_id()).count() == 1

    def test_duplicate_slots_in_one_request_are_rejected(self, client, admin_headers):
        response = put(client, admin_headers, [entry(0, 1, "unavailable"), entry(0, 1, "preferred")])
        assert response.status_code == 400 and "more than once" in response.get_json()["error"]["details"]["entries.1"]
        assert FacultyAvailability.query.count() == 0

    def test_unknown_time_slots_are_rejected(self, client, admin_headers):
        response = put(client, admin_headers, [{"time_slot_id": 99999, "status": "unavailable"}])
        assert response.status_code == 400 and "does not exist" in response.get_json()["error"]["details"]["entries.0"]

    def test_breaks_cannot_be_configured(self, client, admin_headers):
        response = put(client, admin_headers, [entry(0, 4, "unavailable")])  # period 4 is the lunch break
        assert response.status_code == 400 and "break" in response.get_json()["error"]["details"]["entries.0"]

    def test_disabled_slots_cannot_be_newly_configured(self, client, admin_headers):
        client.patch(f"{SLOTS}/{slot_id(0, 7)}", json={"is_active": False}, headers=admin_headers)
        response = put(client, admin_headers, [entry(0, 7, "unavailable")])
        assert response.status_code == 400 and "disabled" in response.get_json()["error"]["details"]["entries.0"]

    def test_one_bad_entry_means_nothing_is_saved(self, client, admin_headers):
        response = put(client, admin_headers, [entry(0, 1, "unavailable"), entry(0, 4, "unavailable")])
        assert response.status_code == 400 and FacultyAvailability.query.count() == 0


class TestPreservation:
    def test_disabling_a_slot_keeps_existing_availability_and_later_saves_do_not_delete_it(self, client, admin_headers):
        put(client, admin_headers, [entry(0, 7, "unavailable"), entry(0, 1, "preferred")])
        assert client.patch(f"{SLOTS}/{slot_id(0, 7)}", json={"is_active": False}, headers=admin_headers).status_code == 200
        data = get(client, admin_headers)
        assert status_of(data, 0, 7) == "unavailable"  # still there
        assert next(s for s in data["slots"] if s["day_of_week"] == 0 and s["period_no"] == 7)["is_active"] is False
        put(client, admin_headers, [entry(0, 1, "preferred"), entry(1, 1, "unavailable")])  # saved without mentioning the disabled slot
        assert status_of(get(client, admin_headers), 0, 7) == "unavailable"  # preserved
        client.patch(f"{SLOTS}/{slot_id(0, 7)}", json={"is_active": True}, headers=admin_headers)
        assert status_of(get(client, admin_headers), 0, 7) == "unavailable"

    def test_a_time_slot_with_availability_cannot_be_deleted(self, client, admin_headers):
        put(client, admin_headers, [entry(1, 2, "unavailable")])
        response = client.delete(f"{SLOTS}/{slot_id(1, 2)}", headers=admin_headers)
        assert response.status_code == 409 and "availability" in response.get_json()["error"]["message"]
        assert FacultyAvailability.query.count() == 1

    def test_deleting_an_unused_faculty_member_removes_only_their_availability(self, client, admin_headers):
        created = client.post(FAC, json={"name": "Temp Faculty", "email": "temp.f@college.test", "employee_code": "FTMP", "department_id": 1, "password": "Temporary#Pw1"}, headers=admin_headers)
        temp_id = created.get_json()["data"]["id"]
        client.put(f"{FAC}/{temp_id}/availability", json={"entries": [entry(0, 1, "unavailable")]}, headers=admin_headers)
        put(client, admin_headers, [entry(0, 2, "preferred")], code="F001")
        assert FacultyAvailability.query.count() == 2
        assert client.delete(f"{FAC}/{temp_id}", headers=admin_headers).status_code == 200
        assert FacultyAvailability.query.count() == 1 and FacultyAvailability.query.first().faculty_id == faculty_id("F001")
