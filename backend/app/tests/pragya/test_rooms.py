"""Pragya - R5 Classroom and laboratory management API (PRA-TC01 .. PRA-TC06 plus permissions, locks and deletion)."""
import pytest

from app.extensions import db
from app.models import Room
from app.tests.pragya.helpers import assignment, new_timetable, place, room

URL = "/api/v1/rooms"


def body(**over):
    data = {"code": "R301", "name": "Room 301", "location": "Main Block, Floor 3", "capacity": 50, "room_type": "classroom"}
    data.update(over)
    return data


def post(client, headers, **over):
    return client.post(URL, json=body(**over), headers=headers)


# ---------------------------------------------------------------- permissions
class TestPermissions:
    def test_requires_login(self, client, seeded):
        for call in (lambda: client.get(URL), lambda: client.post(URL, json=body()), lambda: client.get(f"{URL}/suggest")):
            assert call().status_code == 401

    @pytest.mark.parametrize("who", ["student_headers", "faculty_headers"])
    def test_rooms_are_admin_only(self, client, request, who):
        headers = request.getfixturevalue(who)
        rid = room("R101").id
        assert client.get(URL, headers=headers).status_code == 403
        assert client.get(f"{URL}/{rid}", headers=headers).status_code == 403
        assert client.post(URL, json=body(), headers=headers).status_code == 403
        assert client.patch(f"{URL}/{rid}", json={"capacity": 500}, headers=headers).status_code == 403
        assert client.delete(f"{URL}/{rid}", headers=headers).status_code == 403
        assert client.get(f"{URL}/suggest?batch_id=1&subject_id=1&time_slot_ids=1", headers=headers).status_code == 403
        assert room("R101").capacity == 40


# ---------------------------------------------------------------- listing
class TestList:
    def test_lists_seed_rooms_ordered_by_code(self, client, admin_headers):
        data = client.get(URL, headers=admin_headers).get_json()["data"]
        assert data["total"] == 7
        assert [r["code"] for r in data["items"]] == ["LAB1", "LAB2", "R101", "R102", "R201", "R202", "SEM1"]
        lab = data["items"][0]
        assert (lab["name"], lab["capacity"], lab["room_type"], lab["lab_type"], lab["is_available"]) == ("Computer Lab 1", 60, "lab", "Computer", True)
        assert lab["usage"] == {"timetable_entries": 0} and lab["in_use"] is False and lab["min_capacity"] == 0

    def test_pagination(self, client, admin_headers):
        p2 = client.get(f"{URL}?per_page=3&page=2", headers=admin_headers).get_json()["data"]
        assert (p2["total"], p2["pages"], [r["code"] for r in p2["items"]]) == (7, 3, ["R102", "R201", "R202"])

    def test_filters_and_search(self, client, admin_headers):
        total = lambda qs: client.get(f"{URL}?{qs}", headers=admin_headers).get_json()["data"]["total"]
        assert total("room_type=lab") == 2 and total("room_type=classroom") == 4 and total("room_type=seminar_hall") == 1 and total("room_type=auditorium") == 0
        assert total("min_capacity=60") == 4 and total("min_capacity=121") == 0
        assert total("available=true") == 7 and total("available=false") == 0
        assert total("q=lab") == 2 and total("q=floor 1") == 4 and total("q=r2") == 2 and total("q=nothing") == 0 and total("q=%25") == 0
        assert total("room_type=lab&min_capacity=50") == 1

    @pytest.mark.parametrize("qs", ["page=0", "per_page=101", "room_type=garage", "min_capacity=0", "available=maybe", "min_capacity=x"])
    def test_bad_query_values_are_400(self, client, admin_headers, qs):
        assert client.get(f"{URL}?{qs}", headers=admin_headers).status_code == 400

    def test_get_one_and_404(self, client, admin_headers):
        assert client.get(f"{URL}/{room('R201').id}", headers=admin_headers).get_json()["data"]["capacity"] == 60
        assert client.get(f"{URL}/9999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- create / validation
class TestCreate:
    def test_PRA_TC01_add_a_classroom(self, client, admin_headers):
        response = post(client, admin_headers)
        assert response.status_code == 201
        item = response.get_json()["data"]
        assert (item["code"], item["name"], item["capacity"], item["room_type"], item["lab_type"], item["is_available"]) == ("R301", "Room 301", 50, "classroom", None, True)
        assert room("R301") is not None

    def test_PRA_TC02_add_a_laboratory_with_its_type(self, client, admin_headers):
        item = post(client, admin_headers, code="LAB3", name="Electronics Lab", room_type="lab", lab_type="Electronics", capacity=40).get_json()["data"]
        assert (item["room_type"], item["lab_type"]) == ("lab", "Electronics")

    def test_values_are_normalised(self, client, admin_headers):
        item = post(client, admin_headers, code=" r-302 ", name="  Room   302 ", location="  ").get_json()["data"]
        assert (item["code"], item["name"], item["location"]) == ("R-302", "Room 302", None)

    def test_a_room_can_be_created_out_of_service(self, client, admin_headers):
        assert post(client, admin_headers, is_available=False).get_json()["data"]["is_available"] is False

    def test_PRA_TC05_missing_required_details_are_reported_and_nothing_saved(self, client, admin_headers):
        data = body()
        del data["code"]
        del data["capacity"]
        response = client.post(URL, json=data, headers=admin_headers)
        assert response.status_code == 400 and set(response.get_json()["error"]["details"]) == {"code", "capacity"}
        assert Room.query.count() == 7
        assert set(client.post(URL, json={}, headers=admin_headers).get_json()["error"]["details"]) == {"code", "name", "capacity", "room_type"}

    @pytest.mark.parametrize("capacity", [0, -5, 2001, "40", 40.5, True, None])
    def test_PRA_TC06_invalid_capacity_is_rejected(self, client, admin_headers, capacity):
        response = post(client, admin_headers, capacity=capacity)
        assert response.status_code == 400 and "capacity" in response.get_json()["error"]["details"]
        assert Room.query.count() == 7

    def test_capacity_boundaries_are_accepted(self, client, admin_headers):
        assert post(client, admin_headers, code="MIN1", capacity=1).status_code == 201
        assert post(client, admin_headers, code="MAX1", capacity=2000).status_code == 201

    @pytest.mark.parametrize(
        "field, value",
        [("code", "bad code!"), ("code", "A" * 31), ("code", 5), ("name", "x"), ("name", "n" * 101), ("room_type", "garage"), ("room_type", 3),
         ("location", "l" * 121), ("is_available", "yes"), ("lab_type", "Computer")],  # lab_type is rejected for a classroom
    )
    def test_invalid_values_are_400_with_the_offending_field(self, client, admin_headers, field, value):
        response = post(client, admin_headers, **{field: value})
        assert response.status_code == 400 and field in response.get_json()["error"]["details"]

    def test_unknown_fields_and_non_json(self, client, admin_headers):
        assert post(client, admin_headers, colour="red").status_code == 400
        assert client.post(URL, data="nope", headers=admin_headers).status_code == 400

    def test_duplicate_code_is_409_even_with_different_case(self, client, admin_headers):
        for code in ("R101", " r101 "):
            response = post(client, admin_headers, code=code)
            assert response.status_code == 409 and response.get_json()["error"]["code"] == "duplicate_room" and "code" in response.get_json()["error"]["details"]
        assert Room.query.count() == 7


# ---------------------------------------------------------------- update (PRA-TC03)
class TestUpdate:
    def test_PRA_TC03_update_capacity_and_type(self, client, admin_headers):
        rid = post(client, admin_headers).get_json()["data"]["id"]
        item = client.patch(f"{URL}/{rid}", json={"capacity": 75, "room_type": "seminar_hall"}, headers=admin_headers).get_json()["data"]
        assert (item["capacity"], item["room_type"]) == (75, "seminar_hall")
        assert db.session.get(Room, rid).capacity == 75

    def test_keeping_your_own_code_is_not_a_duplicate(self, client, admin_headers):
        rid = room("R101").id
        assert client.patch(f"{URL}/{rid}", json={"code": "r101", "name": "Room 101 (renovated)"}, headers=admin_headers).status_code == 200

    def test_changing_to_another_rooms_code_is_409(self, client, admin_headers):
        assert client.patch(f"{URL}/{room('R101').id}", json={"code": "R102"}, headers=admin_headers).status_code == 409

    def test_lab_type_is_cleared_requirement_when_a_lab_becomes_a_classroom(self, client, admin_headers):
        rid = room("LAB2").id
        assert client.patch(f"{URL}/{rid}", json={"room_type": "classroom"}, headers=admin_headers).status_code == 400  # still has lab_type "Computer"
        assert client.patch(f"{URL}/{rid}", json={"room_type": "classroom", "lab_type": None}, headers=admin_headers).status_code == 200

    def test_update_validation(self, client, admin_headers):
        rid = room("R101").id
        assert client.patch(f"{URL}/{rid}", json={}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{rid}", json={"capacity": 0}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/{rid}", json={"id": 9}, headers=admin_headers).status_code == 400
        assert client.patch(f"{URL}/9999", json={"capacity": 5}, headers=admin_headers).status_code == 404
        assert room("R101").capacity == 40


# ---------------------------------------------------------------- rooms in timetables
class TestInUse:
    def _scheduled(self, client):
        t = new_timetable()
        place(t, assignment("A", "CS301"), "R201", 0, 1)  # batch A (58 students) in R201 (60 seats)
        return room("R201").id

    def test_a_scheduled_room_reports_its_usage(self, client, admin_headers):
        rid = self._scheduled(client)
        item = client.get(f"{URL}/{rid}", headers=admin_headers).get_json()["data"]
        assert item["usage"] == {"timetable_entries": 1} and item["in_use"] is True and item["min_capacity"] == 58

    def test_a_scheduled_room_cannot_be_deleted_and_stays_intact(self, client, admin_headers):
        rid = self._scheduled(client)
        response = client.delete(f"{URL}/{rid}", headers=admin_headers)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "room_in_use" and "1 timetable entry" in error["message"] and "unavailable instead" in error["message"]
        assert db.session.get(Room, rid) is not None

    def test_the_type_of_a_scheduled_room_is_locked(self, client, admin_headers):
        rid = self._scheduled(client)
        response = client.patch(f"{URL}/{rid}", json={"room_type": "seminar_hall"}, headers=admin_headers)
        assert response.status_code == 409 and "room_type" in response.get_json()["error"]["details"]
        assert db.session.get(Room, rid).room_type.value == "classroom"

    def test_capacity_cannot_drop_below_the_largest_scheduled_batch_but_can_stay_at_it(self, client, admin_headers):
        rid = self._scheduled(client)
        response = client.patch(f"{URL}/{rid}", json={"capacity": 57}, headers=admin_headers)
        assert response.status_code == 409 and "58" in response.get_json()["error"]["message"]
        assert client.patch(f"{URL}/{rid}", json={"capacity": 58}, headers=admin_headers).status_code == 200  # boundary: equal is fine
        assert client.patch(f"{URL}/{rid}", json={"capacity": 100}, headers=admin_headers).status_code == 200

    def test_a_scheduled_room_can_still_be_renamed_and_taken_out_of_service_with_a_warning(self, client, admin_headers):
        rid = self._scheduled(client)
        assert client.patch(f"{URL}/{rid}", json={"name": "Room 201 (north)"}, headers=admin_headers).get_json()["message"] == "Room updated."
        response = client.patch(f"{URL}/{rid}", json={"is_available": False}, headers=admin_headers)
        assert response.status_code == 200 and "out of service" in response.get_json()["message"] and "1 timetable entries" in response.get_json()["message"]
        assert response.get_json()["data"]["is_available"] is False

    def test_an_unscheduled_room_can_be_deleted_and_its_code_reused(self, client, admin_headers):
        rid = post(client, admin_headers).get_json()["data"]["id"]
        assert client.delete(f"{URL}/{rid}", headers=admin_headers).status_code == 200
        assert db.session.get(Room, rid) is None and Room.query.count() == 7
        assert post(client, admin_headers).status_code == 201

    def test_delete_404(self, client, admin_headers):
        assert client.delete(f"{URL}/9999", headers=admin_headers).status_code == 404

    def test_other_rooms_are_untouched_by_all_of_this(self, client, admin_headers):
        self._scheduled(client)
        client.delete(f"{URL}/{room('R201').id}", headers=admin_headers)
        assert {r.code: r.capacity for r in Room.query} == {"LAB1": 60, "LAB2": 45, "R101": 40, "R102": 45, "R201": 60, "R202": 70, "SEM1": 120}
