"""Diya - R6 Time-Slot Management API (DIY-TC09 .. DIY-TC12 plus permission / overlap / in-use rules)."""
from datetime import time

import pytest

from app.extensions import db
from app.models import FacultyAvailability, Faculty, Room, TeachingAssignment, TimeSlot, Timetable, TimetableEntry, User, AvailabilityStatus
from app.tests.conftest import auth_header

URL = "/api/v1/time-slots"


def payload(**overrides):
    """A valid create body for an unused Saturday (seed data covers Mon-Fri)."""
    body = {"days": [5], "period_no": 1, "start_time": "09:00", "end_time": "10:00", "slot_type": "class"}
    body.update(overrides)
    return body


def create(client, headers, **overrides):
    return client.post(URL, json=payload(**overrides), headers=headers)


def slot_id(day, period):
    return db.session.scalar(db.select(TimeSlot.id).where(TimeSlot.day_of_week == day, TimeSlot.period_no == period))


# ---------------------------------------------------------------- permissions
class TestPermissions:
    def test_requires_login(self, client, seeded):
        assert client.get(URL).status_code == 401
        assert client.post(URL, json=payload()).status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_non_admins_cannot_write(self, client, request, who):
        headers = request.getfixturevalue(who)
        sid = slot_id(0, 1)
        assert client.post(URL, json=payload(), headers=headers).status_code == 403
        assert client.patch(f"{URL}/{sid}", json={"is_active": False}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{sid}", headers=headers).status_code == 403
        assert db.session.get(TimeSlot, sid).is_active is True  # nothing changed

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers", "admin_headers"])
    def test_every_signed_in_role_can_read(self, client, request, who):
        assert client.get(URL, headers=request.getfixturevalue(who)).status_code == 200


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_seed_data_in_day_period_order_with_pagination(self, client, admin_headers):
        body = client.get(f"{URL}?per_page=10", headers=admin_headers).get_json()["data"]
        assert (body["total"], body["pages"], body["page"], body["per_page"]) == (35, 4, 1, 10)
        assert [(i["day_of_week"], i["period_no"]) for i in body["items"]][:3] == [(0, 1), (0, 2), (0, 3)]
        first = body["items"][0]
        assert first["start_time"] == "09:00" and first["end_time"] == "10:00" and first["day_name"] == "Monday"
        last_page = client.get(f"{URL}?per_page=10&page=4", headers=admin_headers).get_json()["data"]
        assert len(last_page["items"]) == 5

    def test_page_past_the_end_is_empty_not_an_error(self, client, admin_headers):
        body = client.get(f"{URL}?page=99", headers=admin_headers).get_json()["data"]
        assert body["items"] == [] and body["total"] == 35

    def test_filters(self, client, admin_headers):
        get = lambda qs: client.get(f"{URL}?per_page=100&{qs}", headers=admin_headers).get_json()["data"]
        assert get("day=2")["total"] == 7
        assert get("slot_type=break")["total"] == 5
        assert get("slot_type=class&day=0")["total"] == 6
        assert get("active=false")["total"] == 0
        assert get("active=true")["total"] == 35

    def test_search_by_period_number_and_by_time(self, client, admin_headers):
        get = lambda q: client.get(f"{URL}?per_page=100&q={q}", headers=admin_headers).get_json()["data"]
        assert {i["period_no"] for i in get("3")["items"]} == {3}
        assert get("3")["total"] == 5
        assert get("13:")["total"] == 5 + 5  # start 13:00 (period 5) or end 13:00 (period 4 break)
        assert get("zzz")["total"] == 0

    @pytest.mark.parametrize("qs", ["page=0", "page=abc", "per_page=0", "per_page=500", "day=9", "day=x", "slot_type=lunch", "active=maybe"])
    def test_bad_query_parameters_are_400(self, client, admin_headers, qs):
        response = client.get(f"{URL}?{qs}", headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "validation_error"

    def test_get_one_and_404(self, client, admin_headers):
        sid = slot_id(1, 2)
        item = client.get(f"{URL}/{sid}", headers=admin_headers).get_json()["data"]
        assert item["day_name"] == "Tuesday" and item["period_no"] == 2
        assert client.get(f"{URL}/999999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create
class TestCreate:
    def test_DIY_TC09_create_a_valid_time_slot(self, client, admin_headers):
        response = create(client, admin_headers)
        assert response.status_code == 201
        item = response.get_json()["data"]["items"][0]
        assert (item["day_of_week"], item["period_no"], item["start_time"], item["end_time"]) == (5, 1, "09:00", "10:00")
        assert item["slot_type"] == "class" and item["is_active"] is True and item["in_use"] is False
        stored = db.session.get(TimeSlot, item["id"])
        assert stored.start_time == time(9, 0)

    def test_DIY_TC12_define_working_days_and_a_break_in_one_request(self, client, admin_headers):
        response = create(client, admin_headers, days=[5, 6], period_no=4, start_time="12:00", end_time="13:00", slot_type="break")
        assert response.status_code == 201
        items = response.get_json()["data"]["items"]
        assert [(i["day_name"], i["slot_type"]) for i in items] == [("Saturday", "break"), ("Sunday", "break")]

    def test_DIY_TC10_end_before_start_is_rejected_and_nothing_saved(self, client, admin_headers):
        before = TimeSlot.query.count()
        response = create(client, admin_headers, start_time="11:00", end_time="10:00")
        error = response.get_json()["error"]
        assert response.status_code == 400 and error["code"] == "validation_error"
        assert "end_time" in error["details"]
        assert TimeSlot.query.count() == before

    def test_equal_start_and_end_is_rejected(self, client, admin_headers):
        assert create(client, admin_headers, start_time="10:00", end_time="10:00").status_code == 400

    def test_missing_fields_are_each_reported(self, client, admin_headers):
        details = client.post(URL, json={}, headers=admin_headers).get_json()["error"]["details"]
        assert set(details) == {"days", "period_no", "start_time", "end_time"}

    @pytest.mark.parametrize(
        "field, value",
        [
            ("days", []), ("days", "mon"), ("days", [7]), ("days", [-1]), ("days", [1, 1]), ("days", [True]),
            ("period_no", 0), ("period_no", 21), ("period_no", "1"), ("period_no", 1.5), ("period_no", True),
            ("start_time", "9am"), ("start_time", "25:00"), ("start_time", "09:60"), ("start_time", "9:00"), ("start_time", 900),
            ("end_time", "noon"), ("slot_type", "lunch"), ("is_active", "yes"),
        ],
    )
    def test_invalid_values_are_400_with_the_offending_field(self, client, admin_headers, field, value):
        response = create(client, admin_headers, **{field: value})
        assert response.status_code == 400
        assert field in response.get_json()["error"]["details"]

    def test_unknown_fields_are_rejected(self, client, admin_headers):
        response = create(client, admin_headers, colour="red")
        assert response.status_code == 400 and "colour" in response.get_json()["error"]["details"]

    def test_body_must_be_json_object(self, client, admin_headers):
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_duplicate_day_and_period_is_409(self, client, admin_headers):
        response = create(client, admin_headers, days=[0], period_no=1, start_time="16:00", end_time="17:00")
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "duplicate_slot"
        assert "period_no" in error["details"]

    def test_overlapping_times_on_the_same_day_is_409(self, client, admin_headers):
        response = create(client, admin_headers, days=[0], period_no=9, start_time="09:30", end_time="10:30")
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "overlapping_slot"
        assert "Period 1" in error["message"]

    def test_back_to_back_slots_do_not_clash(self, client, admin_headers):
        # Monday period 7 ends 16:00; 16:00-17:00 starts exactly when it ends (PRA-TC10/11 style boundary).
        assert create(client, admin_headers, days=[0], period_no=8, start_time="16:00", end_time="17:00").status_code == 201

    def test_same_times_on_a_different_day_are_fine(self, client, admin_headers):
        assert create(client, admin_headers, days=[5], period_no=1, start_time="09:00", end_time="10:00").status_code == 201

    def test_period_numbers_must_follow_time_order(self, client, admin_headers):
        # Monday period 1 is 09:00; a *later* period number may not start before it.
        response = create(client, admin_headers, days=[0], period_no=8, start_time="08:00", end_time="08:45")
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "invalid_period_order"

    def test_multi_day_create_is_all_or_nothing(self, client, admin_headers):
        before = TimeSlot.query.count()
        # Saturday is free but Monday period 1 already exists -> nothing may be created.
        response = create(client, admin_headers, days=[5, 0], period_no=1)
        assert response.status_code == 409
        assert TimeSlot.query.count() == before


# ---------------------------------------------------------------- update
class TestUpdate:
    def test_DIY_TC11_update_start_and_end_times(self, client, admin_headers):
        sid = create(client, admin_headers).get_json()["data"]["items"][0]["id"]
        response = client.patch(f"{URL}/{sid}", json={"start_time": "09:15", "end_time": "10:15"}, headers=admin_headers)
        assert response.status_code == 200
        item = response.get_json()["data"]
        assert (item["start_time"], item["end_time"]) == ("09:15", "10:15")
        assert db.session.get(TimeSlot, sid).start_time == time(9, 15)

    def test_a_slot_does_not_conflict_with_itself(self, client, admin_headers):
        sid = slot_id(0, 2)  # 10:00-11:00
        assert client.patch(f"{URL}/{sid}", json={"start_time": "10:00", "end_time": "10:50"}, headers=admin_headers).status_code == 200

    def test_can_disable_and_enable(self, client, admin_headers):
        sid = slot_id(0, 7)
        off = client.patch(f"{URL}/{sid}", json={"is_active": False}, headers=admin_headers).get_json()["data"]
        assert off["is_active"] is False
        assert client.get(f"{URL}?active=false", headers=admin_headers).get_json()["data"]["total"] == 1
        assert client.patch(f"{URL}/{sid}", json={"is_active": True}, headers=admin_headers).get_json()["data"]["is_active"] is True

    def test_can_change_type(self, client, admin_headers):
        sid = slot_id(0, 4)
        assert client.patch(f"{URL}/{sid}", json={"slot_type": "class"}, headers=admin_headers).get_json()["data"]["slot_type"] == "class"

    def test_update_into_an_overlap_is_409(self, client, admin_headers):
        sid = slot_id(0, 2)  # 10:00-11:00 ; stretching into period 3 (11:00-12:00)
        response = client.patch(f"{URL}/{sid}", json={"end_time": "11:30"}, headers=admin_headers)
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "overlapping_slot"
        assert db.session.get(TimeSlot, sid).end_time == time(11, 0)

    def test_update_into_a_duplicate_period_is_409(self, client, admin_headers):
        sid = slot_id(0, 2)
        assert client.patch(f"{URL}/{sid}", json={"period_no": 3}, headers=admin_headers).status_code == 409

    def test_update_validation(self, client, admin_headers):
        sid = slot_id(0, 2)
        assert client.patch(f"{URL}/{sid}", json={"start_time": "12:00"}, headers=admin_headers).status_code == 400  # start after existing end
        assert client.patch(f"{URL}/{sid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"id": 5}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{sid}", json={"day_of_week": 9}, headers=admin_headers).status_code == 400

    def test_update_404(self, client, admin_headers):
        assert client.patch(f"{URL}/999999", json={"is_active": False}, headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- delete & in-use rules
def _use_in_timetable(slot):
    admin = db.session.scalar(db.select(User).filter_by(email="admin@timetable.test"))
    assignment = db.session.scalars(db.select(TeachingAssignment)).first()
    room = db.session.scalars(db.select(Room)).first()
    timetable = Timetable(term_id=assignment.term_id, name="T", version=1, generated_by=admin.id)
    db.session.add(timetable)
    db.session.flush()
    db.session.add(TimetableEntry(timetable_id=timetable.id, assignment_id=assignment.id, faculty_id=assignment.faculty_id,
                                  batch_id=assignment.batch_id, room_id=room.id, time_slot_id=slot.id))
    db.session.commit()


class TestDelete:
    def test_delete_an_unused_slot(self, client, admin_headers):
        sid = create(client, admin_headers).get_json()["data"]["items"][0]["id"]
        assert client.delete(f"{URL}/{sid}", headers=admin_headers).status_code == 200
        assert db.session.get(TimeSlot, sid) is None
        assert client.get(f"{URL}/{sid}", headers=admin_headers).status_code == 404

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/999999", headers=admin_headers).status_code == 404

    def test_slot_used_by_a_timetable_cannot_be_deleted(self, client, admin_headers):
        slot = db.session.get(TimeSlot, slot_id(0, 1))
        _use_in_timetable(slot)
        response = client.delete(f"{URL}/{slot.id}", headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "slot_in_use"
        assert "1 timetable entry" in error["message"] and "Disable it" in error["message"]
        assert db.session.get(TimeSlot, slot.id) is not None
        assert client.get(f"{URL}/{slot.id}", headers=admin_headers).get_json()["data"]["in_use"] is True

    def test_slot_with_faculty_availability_cannot_be_deleted_and_the_record_survives(self, client, admin_headers):
        slot = db.session.get(TimeSlot, slot_id(1, 1))
        faculty = db.session.scalars(db.select(Faculty)).first()
        db.session.add(FacultyAvailability(faculty_id=faculty.id, time_slot_id=slot.id, status=AvailabilityStatus.UNAVAILABLE))
        db.session.commit()
        response = client.delete(f"{URL}/{slot.id}", headers=admin_headers)
        assert response.status_code == 409 and "availability" in response.get_json()["error"]["message"]
        assert FacultyAvailability.query.count() == 1  # not silently cascaded away

    def test_a_used_slot_can_still_be_disabled(self, client, admin_headers):
        slot = db.session.get(TimeSlot, slot_id(0, 1))
        _use_in_timetable(slot)
        assert client.patch(f"{URL}/{slot.id}", json={"is_active": False}, headers=admin_headers).status_code == 200

    def test_moving_a_slot_used_by_a_timetable_is_blocked(self, client, admin_headers):
        slot = db.session.get(TimeSlot, slot_id(0, 1))
        _use_in_timetable(slot)
        response = client.patch(f"{URL}/{slot.id}", json={"end_time": "09:50"}, headers=admin_headers)
        assert response.status_code == 409 and response.get_json()["error"]["code"] == "slot_in_use"
        assert db.session.get(TimeSlot, slot.id).end_time == time(10, 0)

    def test_in_use_flag_in_the_list(self, client, admin_headers):
        slot = db.session.get(TimeSlot, slot_id(0, 1))
        _use_in_timetable(slot)
        items = client.get(f"{URL}?day=0&per_page=100", headers=admin_headers).get_json()["data"]["items"]
        assert {i["period_no"]: i["in_use"] for i in items} == {1: True, 2: False, 3: False, 4: False, 5: False, 6: False, 7: False}


def test_existing_login_still_works_after_adding_the_module(client, seeded):
    assert auth_header(client, "admin@timetable.test")["Authorization"].startswith("Bearer ")
