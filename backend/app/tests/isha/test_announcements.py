"""R19 Announcements: Admin manages; every signed-in role reads PUBLISHED announcements only."""
import pytest
from sqlalchemy import text

from app.extensions import db
from app.models import Announcement, AnnouncementCategory, AnnouncementStatus

URL = "/api/v1/announcements"
FEED = f"{URL}/published"
GOOD = {"title": "Mid-term exam schedule", "message": "The mid-term exams start on Monday.\n\nPlease check the timetable.", "category": "exam"}


def create(client, headers, **over):
    r = client.post(URL, json={**GOOD, **over}, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def listing(client, headers, path=URL, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"{path}?{query}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def titles(page):
    return [i["title"] for i in page["items"]]


class TestPermissions:
    def test_login_is_required_everywhere(self, client, seeded):
        for method, path in (("get", URL), ("get", f"{URL}/1"), ("post", URL), ("patch", f"{URL}/1"), ("delete", f"{URL}/1"),
                             ("post", f"{URL}/1/publish"), ("post", f"{URL}/1/unpublish"), ("get", FEED), ("get", f"{FEED}/1")):
            assert getattr(client, method)(path, **({"json": {}} if method in ("post", "patch") else {})).status_code == 401, (method, path)

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers"])
    def test_faculty_and_students_cannot_manage_anything(self, client, admin_headers, request, who):
        headers = request.getfixturevalue(who)
        item = create(client, admin_headers)
        before = listing(client, admin_headers)["total"]
        for method, path, body in (("get", URL, None), ("get", f"{URL}/{item['id']}", None), ("post", URL, GOOD), ("patch", f"{URL}/{item['id']}", {"title": "Hacked title"}),
                                   ("delete", f"{URL}/{item['id']}", None), ("post", f"{URL}/{item['id']}/publish", {}), ("post", f"{URL}/{item['id']}/unpublish", {})):
            kwargs = {"json": body} if body is not None else {}
            assert getattr(client, method)(path, headers=headers, **kwargs).status_code == 403, (method, path)
        after = client.get(f"{URL}/{item['id']}", headers=admin_headers).get_json()["data"]
        assert after["title"] == item["title"] and after["status"] == "draft" and listing(client, admin_headers)["total"] == before

    @pytest.mark.parametrize("who", ["faculty_headers", "student_headers", "admin_headers"])
    def test_every_role_can_read_the_feed(self, client, admin_headers, request, who):
        create(client, admin_headers, publish=True)
        assert listing(client, request.getfixturevalue(who), FEED)["total"] == 1


class TestCreate:
    def test_a_draft_by_default_with_the_author_and_no_publish_date(self, client, admin_headers):
        item = create(client, admin_headers)
        assert item["status"] == "draft" and item["published_at"] is None and item["category"] == "exam" and item["category_label"] == "Exam"
        assert item["author"] == {"name": "Dr. Anita Verma (Admin)"}
        assert "email" not in str(item).lower()

    def test_publishing_on_create_sets_the_publish_date(self, client, admin_headers):
        item = create(client, admin_headers, publish=True)
        assert item["status"] == "published" and item["published_at"]

    def test_the_category_defaults_to_general(self, client, admin_headers):
        item = create(client, admin_headers, category=None)
        assert item["category"] == "general"
        body = {k: v for k, v in GOOD.items() if k != "category"}
        assert client.post(URL, json=body, headers=admin_headers).get_json()["data"]["category"] == "general"

    @pytest.mark.parametrize("category", ["general", "academic", "timetable_change", "exam", "urgent"])
    def test_every_category_is_accepted(self, client, admin_headers, category):
        assert create(client, admin_headers, category=category)["category"] == category

    def test_it_is_stored_permanently_in_the_database(self, client, admin_headers):
        item = create(client, admin_headers, publish=True)
        db.session.expire_all()
        row = db.session.get(Announcement, item["id"])
        assert (row.title, row.category, row.status) == (GOOD["title"], AnnouncementCategory.EXAM, AnnouncementStatus.PUBLISHED)
        assert row.published_at is not None and row.created_by == row.author.id

    def test_paragraph_breaks_are_kept_and_line_endings_normalised(self, client, admin_headers):
        item = create(client, admin_headers, message="Line one  \r\n\r\n\r\n\r\nLine two\rLine three   ")
        assert item["message"] == "Line one\n\nLine two\nLine three"

    def test_the_title_has_its_spaces_tidied(self, client, admin_headers):
        assert create(client, admin_headers, title="  Room   change   today ")["title"] == "Room change today"

    def test_markup_is_stored_as_plain_text_never_interpreted(self, client, admin_headers):
        item = create(client, admin_headers, title="<script>alert(1)</script> notice", message='<img src=x onerror="alert(1)"> hello there')
        assert item["title"].startswith("<script>") and "<img" in item["message"]   # the UI renders text, so this is inert

    @pytest.mark.parametrize("body,field", [
        ({"title": ""}, "title"), ({"title": "  "}, "title"), ({"title": "ab"}, "title"), ({"title": "x" * 201}, "title"), ({"title": 5}, "title"),
        ({"message": ""}, "message"), ({"message": "abcd"}, "message"), ({"message": "x" * 5001}, "message"), ({"message": ["a"]}, "message"),
        ({"category": "sports"}, "category"), ({"category": 3}, "category"), ({"publish": "yes"}, "publish"), ({"publish": 1}, "publish"),
    ])
    def test_invalid_input_is_refused_with_the_field_named(self, client, admin_headers, body, field):
        r = client.post(URL, json={**GOOD, **body}, headers=admin_headers)
        assert r.status_code == 400 and field in r.get_json()["error"]["details"]
        assert listing(client, admin_headers)["total"] == 0

    @pytest.mark.parametrize("missing", ["title", "message"])
    def test_required_fields(self, client, admin_headers, missing):
        body = {k: v for k, v in GOOD.items() if k != missing}
        r = client.post(URL, json=body, headers=admin_headers)
        assert r.status_code == 400 and r.get_json()["error"]["details"][missing] == "This field is required."

    @pytest.mark.parametrize("extra", ["status", "created_by", "published_at", "audience", "batch_id", "author", "id"])
    def test_the_client_cannot_set_server_controlled_fields(self, client, admin_headers, extra):
        assert client.post(URL, json={**GOOD, extra: "x"}, headers=admin_headers).status_code == 400

    def test_a_body_that_is_not_an_object(self, client, admin_headers):
        assert client.post(URL, json=["x"], headers=admin_headers).status_code == 400

    def test_the_boundary_lengths_are_accepted(self, client, admin_headers):
        assert create(client, admin_headers, title="abc", message="12345")["id"]
        assert create(client, admin_headers, title="t" * 200, message="m" * 5000)["id"]


class TestAdminList:
    def test_all_statuses_newest_edit_first_with_paging_metadata(self, client, admin_headers):
        create(client, admin_headers, title="First notice")
        create(client, admin_headers, title="Second notice", publish=True)
        page = listing(client, admin_headers)
        assert page["total"] == 2 and titles(page) == ["Second notice", "First notice"]
        assert {"items", "page", "per_page", "total", "pages"} <= set(page)

    def test_filter_by_status_and_category(self, client, admin_headers):
        create(client, admin_headers, title="Draft exam", category="exam")
        create(client, admin_headers, title="Live urgent", category="urgent", publish=True)
        create(client, admin_headers, title="Live exam", category="exam", publish=True)
        assert sorted(titles(listing(client, admin_headers, status="draft"))) == ["Draft exam"]
        assert sorted(titles(listing(client, admin_headers, status="published"))) == ["Live exam", "Live urgent"]
        assert sorted(titles(listing(client, admin_headers, category="exam"))) == ["Draft exam", "Live exam"]
        assert titles(listing(client, admin_headers, status="published", category="urgent")) == ["Live urgent"]

    def test_search_covers_title_and_content_ignoring_case(self, client, admin_headers):
        create(client, admin_headers, title="Library closed", message="The library will be closed on Friday.")
        create(client, admin_headers, title="Sports day", message="Bring your LIBRARY card to enter.")
        create(client, admin_headers, title="Other", message="Nothing relevant here.")
        assert sorted(titles(listing(client, admin_headers, q="LIBRARY"))) == ["Library closed", "Sports day"]
        assert titles(listing(client, admin_headers, q="friday")) == ["Library closed"]
        assert listing(client, admin_headers, q="zzzz")["total"] == 0

    def test_search_treats_percent_and_underscore_literally(self, client, admin_headers):
        create(client, admin_headers, title="100% attendance", message="Attendance is compulsory.")
        create(client, admin_headers, title="Hundred notice", message="Nothing to see here.")
        assert titles(listing(client, admin_headers, q="%")) == ["100% attendance"]
        assert listing(client, admin_headers, q="_")["total"] == 0

    def test_paging(self, client, admin_headers):
        for i in range(5):
            create(client, admin_headers, title=f"Notice number {i}")
        first = listing(client, admin_headers, per_page=2, page=1)
        third = listing(client, admin_headers, per_page=2, page=3)
        assert first["total"] == 5 and first["pages"] == 3 and len(first["items"]) == 2 and len(third["items"]) == 1

    @pytest.mark.parametrize("params", ["status=sleeping", "category=sports", "page=0", "per_page=1000", "page=x"])
    def test_bad_filters_are_400(self, client, admin_headers, params):
        assert client.get(f"{URL}?{params}", headers=admin_headers).status_code == 400

    def test_detail(self, client, admin_headers):
        item = create(client, admin_headers)
        r = client.get(f"{URL}/{item['id']}", headers=admin_headers)
        assert r.status_code == 200 and r.get_json()["data"]["message"] == GOOD["message"]
        assert client.get(f"{URL}/9999", headers=admin_headers).status_code == 404

    def test_rows_that_existed_before_categories_read_as_general(self, client, admin_headers, app):
        admin = db.session.execute(text("select id from users where role='admin'")).scalar()
        db.session.execute(text("insert into announcements(title,message,audience,status,created_by) values ('Old notice','from before categories','all','published',:u)"), {"u": admin})
        db.session.commit()
        old = listing(client, admin_headers)["items"][0]
        assert old["category"] == "general" and old["status"] == "published"


class TestFeed:
    def test_only_published_announcements_are_visible_to_faculty_and_students(self, client, admin_headers, faculty_headers, student_headers):
        create(client, admin_headers, title="Secret draft")
        create(client, admin_headers, title="Public notice", publish=True)
        for headers in (faculty_headers, student_headers):
            assert titles(listing(client, headers, FEED)) == ["Public notice"]

    def test_a_draft_cannot_be_read_even_by_its_id(self, client, admin_headers, student_headers):
        draft = create(client, admin_headers)
        r = client.get(f"{FEED}/{draft['id']}", headers=student_headers)
        assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"
        assert "mid-term" not in r.get_data(as_text=True).lower()

    def test_a_published_one_can_be_read_in_full(self, client, admin_headers, student_headers):
        item = create(client, admin_headers, publish=True)
        got = client.get(f"{FEED}/{item['id']}", headers=student_headers).get_json()["data"]
        assert got["message"] == GOOD["message"] and got["author"]["name"] == "Dr. Anita Verma (Admin)" and got["published_at"]

    def test_the_feed_has_no_admin_only_filter(self, client, admin_headers, student_headers):
        create(client, admin_headers, title="Hidden draft")
        assert client.get(f"{FEED}?status=draft", headers=student_headers).get_json()["data"]["total"] == 0

    def test_newest_published_first_category_filter_and_search(self, client, admin_headers, student_headers):
        create(client, admin_headers, title="Older exam note", category="exam", publish=True)
        create(client, admin_headers, title="Newer urgent note", category="urgent", message="Water supply issue in block B.", publish=True)
        assert titles(listing(client, student_headers, FEED)) == ["Newer urgent note", "Older exam note"]
        assert titles(listing(client, student_headers, FEED, category="exam")) == ["Older exam note"]
        assert titles(listing(client, student_headers, FEED, q="water")) == ["Newer urgent note"]

    def test_the_feed_never_includes_author_emails_or_internal_fields(self, client, admin_headers, student_headers):
        create(client, admin_headers, publish=True)
        text_ = client.get(FEED, headers=student_headers).get_data(as_text=True)
        assert "@" not in text_ and "created_by" not in text_ and "audience" not in text_

    def test_the_feed_pages(self, client, admin_headers, student_headers):
        for i in range(4):
            create(client, admin_headers, title=f"Live notice {i}", publish=True)
        page = listing(client, student_headers, FEED, per_page=3)
        assert page["total"] == 4 and page["pages"] == 2 and len(page["items"]) == 3


class TestEditPublishDelete:
    def test_edit_changes_content_and_keeps_the_status_and_publish_date(self, client, admin_headers):
        item = create(client, admin_headers, publish=True)
        r = client.patch(f"{URL}/{item['id']}", json={"title": "Exam schedule moved", "category": "timetable_change"}, headers=admin_headers)
        data = r.get_json()["data"]
        assert r.status_code == 200 and data["title"] == "Exam schedule moved" and data["category"] == "timetable_change"
        assert data["status"] == "published" and data["published_at"] == item["published_at"] and data["message"] == GOOD["message"]

    def test_edits_reach_readers_at_once(self, client, admin_headers, student_headers):
        item = create(client, admin_headers, publish=True)
        client.patch(f"{URL}/{item['id']}", json={"message": "The exam moved to Tuesday."}, headers=admin_headers)
        assert client.get(f"{FEED}/{item['id']}", headers=student_headers).get_json()["data"]["message"] == "The exam moved to Tuesday."

    @pytest.mark.parametrize("body", [{}, {"title": "ab"}, {"message": "abc"}, {"category": "x"}, {"status": "published"}, {"publish": True}, {"created_by": 2}, {"published_at": "2020-01-01"}])
    def test_invalid_edits_change_nothing(self, client, admin_headers, body):
        item = create(client, admin_headers)
        assert client.patch(f"{URL}/{item['id']}", json=body, headers=admin_headers).status_code == 400
        assert client.get(f"{URL}/{item['id']}", headers=admin_headers).get_json()["data"]["title"] == GOOD["title"]

    def test_publish_then_unpublish(self, client, admin_headers, student_headers):
        item = create(client, admin_headers)
        assert listing(client, student_headers, FEED)["total"] == 0
        pub = client.post(f"{URL}/{item['id']}/publish", headers=admin_headers).get_json()["data"]
        assert pub["status"] == "published" and pub["published_at"] and listing(client, student_headers, FEED)["total"] == 1
        back = client.post(f"{URL}/{item['id']}/unpublish", headers=admin_headers).get_json()["data"]
        assert back["status"] == "draft" and back["published_at"] is None and listing(client, student_headers, FEED)["total"] == 0

    def test_publishing_twice_or_unpublishing_a_draft_is_a_conflict(self, client, admin_headers):
        item = create(client, admin_headers)
        assert client.post(f"{URL}/{item['id']}/unpublish", headers=admin_headers).get_json()["error"]["code"] == "not_published"
        client.post(f"{URL}/{item['id']}/publish", headers=admin_headers)
        r = client.post(f"{URL}/{item['id']}/publish", headers=admin_headers)
        assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_published"

    def test_delete_removes_it_for_good(self, client, admin_headers, student_headers):
        item = create(client, admin_headers, publish=True)
        assert client.delete(f"{URL}/{item['id']}", headers=admin_headers).status_code == 200
        assert client.get(f"{URL}/{item['id']}", headers=admin_headers).status_code == 404
        assert client.get(f"{FEED}/{item['id']}", headers=student_headers).status_code == 404
        assert client.delete(f"{URL}/{item['id']}", headers=admin_headers).status_code == 404
        db.session.expire_all()
        assert db.session.get(Announcement, item["id"]) is None

    def test_deleting_one_leaves_the_others(self, client, admin_headers):
        a, b = create(client, admin_headers, title="Keep this one"), create(client, admin_headers, title="Remove this one")
        client.delete(f"{URL}/{b['id']}", headers=admin_headers)
        assert titles(listing(client, admin_headers)) == ["Keep this one"] and a["id"]

    @pytest.mark.parametrize("method,suffix", [("patch", ""), ("delete", ""), ("post", "/publish"), ("post", "/unpublish")])
    def test_unknown_ids_are_404(self, client, admin_headers, method, suffix):
        kwargs = {"json": {"title": "Some title"}} if method == "patch" else {}
        assert getattr(client, method)(f"{URL}/9999{suffix}", headers=admin_headers, **kwargs).status_code == 404


class TestRegression:
    def test_existing_batch_usage_counts_still_work_with_announcements_present(self, client, admin_headers):
        create(client, admin_headers, publish=True)
        assert client.get("/api/v1/batches", headers=admin_headers).status_code == 200

    def test_the_demo_seed_is_unaffected(self, client, seeded, admin_headers):
        assert listing(client, admin_headers)["total"] == 0
