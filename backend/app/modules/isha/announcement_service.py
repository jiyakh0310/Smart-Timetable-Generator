"""Isha - R19 Announcements: validation and business rules.

  * Admin creates drafts, edits, publishes, unpublishes and deletes; everyone signed in can read PUBLISHED announcements.
  * Draft content is never returned by a read-only (feed) query: `list_statement(published_only=True)` is the only thing the
    faculty / student endpoints use.
  * Content is plain text (paragraph breaks are kept). The UI renders it as text, so no markup is ever interpreted.
  * `published_at` is the moment of publishing (kept when a published announcement is edited, cleared when it is unpublished).
  * `audience` / `batch_id` columns already exist in the table; targeting is not part of R19, so every announcement is for everyone.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import func, or_

from app.common import fields
from app.common.errors import AppError
from app.extensions import db
from app.models import Announcement, AnnouncementCategory, AnnouncementStatus, Audience

CREATE_FIELDS = {"title", "message", "category", "publish"}
UPDATE_FIELDS = {"title", "message", "category"}
CATEGORY_LABEL = {
    "general": "General",
    "academic": "Academic",
    "timetable_change": "Timetable change",
    "exam": "Exam",
    "urgent": "Urgent",
}
TITLE_MIN, TITLE_MAX = 3, 200
MESSAGE_MIN, MESSAGE_MAX = 5, 5000


# ---------- reading ----------
def serialize(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "category": a.category.value,
        "category_label": CATEGORY_LABEL[a.category.value],
        "status": a.status.value,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "author": {"name": a.author.full_name if a.author else "Unknown"},  # the name only: never the author's email
    }


def serialize_many(rows: list[Announcement]) -> list[dict]:
    return [serialize(r) for r in rows]


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_statement(status=None, category=None, q=None, published_only=False):
    """Admin list (all statuses, newest edit first) or, with published_only, the read-only feed (newest published first)."""
    if published_only:
        stmt = db.select(Announcement).where(Announcement.status == AnnouncementStatus.PUBLISHED).order_by(Announcement.published_at.desc(), Announcement.id.desc())
    else:
        stmt = db.select(Announcement).order_by(Announcement.updated_at.desc(), Announcement.id.desc())
        if status is not None:
            stmt = stmt.where(Announcement.status == status)
    if category is not None:
        stmt = stmt.where(Announcement.category == category)
    if q and q.strip():
        like = _like(q)
        stmt = stmt.where(or_(func.lower(Announcement.title).like(like, escape="\\"), func.lower(Announcement.message).like(like, escape="\\")))
    return stmt


def get_or_404(announcement_id: int, published_only: bool = False) -> Announcement:
    a = db.session.get(Announcement, announcement_id)
    # a draft is indistinguishable from a missing announcement for read-only callers
    if a is None or (published_only and a.status != AnnouncementStatus.PUBLISHED):
        raise AppError("not_found", "Announcement not found.", 404)
    return a


def parse_category(raw):
    if raw in (None, ""):
        return None
    try:
        return AnnouncementCategory(raw)
    except ValueError:
        raise AppError("validation_error", "'category' is not a valid category.", 400, {"category": "Choose General, Academic, Timetable change, Exam or Urgent."}) from None


def parse_status(raw):
    if raw in (None, ""):
        return None
    try:
        return AnnouncementStatus(raw)
    except ValueError:
        raise AppError("validation_error", "'status' must be draft or published.", 400, {"status": "Choose draft or published."}) from None


# ---------- validation ----------
def clean_message(value, errors: dict):
    """Plain text with paragraph breaks kept: normalised line endings, trailing spaces removed, at most one blank line in a row."""
    if not isinstance(value, str):
        errors["message"] = "Must be text."
        return None
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not MESSAGE_MIN <= len(text) <= MESSAGE_MAX:
        errors["message"] = f"The announcement must be {MESSAGE_MIN} to {MESSAGE_MAX} characters."
        return None
    return text


def clean(data: dict, announcement: Announcement | None = None) -> dict:
    fields.reject_unknown(data, CREATE_FIELDS if announcement is None else UPDATE_FIELDS, AppError)
    if announcement is not None and not data:
        raise AppError("validation_error", "Nothing to update.", 400)
    merged = {"title": announcement.title, "message": announcement.message, "category": announcement.category.value, **data} if announcement else {"category": "general", **data}
    errors: dict = {}
    out: dict = {}
    for f in ("title", "message"):
        if merged.get(f) in (None, ""):
            errors[f] = "This field is required."
    if "title" not in errors:
        out["title"] = fields.text(merged["title"], "title", errors, TITLE_MIN, TITLE_MAX, "The title")
    if "message" not in errors:
        out["message"] = clean_message(merged["message"], errors)
    try:
        out["category"] = AnnouncementCategory(merged.get("category") or "general")
    except (ValueError, TypeError):
        errors["category"] = "Choose General, Academic, Timetable change, Exam or Urgent."
    if "publish" in data and not isinstance(data["publish"], bool):
        errors["publish"] = "Must be true or false."
    if errors:
        raise AppError("validation_error", "Please correct the highlighted fields.", 400, errors)
    return out


# ---------- commands ----------
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create(data: dict, author_id: int) -> Announcement:
    publish = data.get("publish") is True
    values = clean(data)
    a = Announcement(**values, audience=Audience.ALL, status=AnnouncementStatus.PUBLISHED if publish else AnnouncementStatus.DRAFT,
                     published_at=_now() if publish else None, created_by=author_id)
    db.session.add(a)
    db.session.commit()
    return a


def update(a: Announcement, data: dict) -> Announcement:
    for field, value in clean(data, a).items():
        setattr(a, field, value)
    db.session.commit()
    return a


def publish(a: Announcement) -> Announcement:
    if a.status == AnnouncementStatus.PUBLISHED:
        raise AppError("already_published", "This announcement is already published.", 409)
    a.status, a.published_at = AnnouncementStatus.PUBLISHED, _now()
    db.session.commit()
    return a


def unpublish(a: Announcement) -> Announcement:
    if a.status != AnnouncementStatus.PUBLISHED:
        raise AppError("not_published", "This announcement is not published.", 409)
    a.status, a.published_at = AnnouncementStatus.DRAFT, None
    db.session.commit()
    return a


def delete(a: Announcement) -> None:
    db.session.delete(a)
    db.session.commit()
