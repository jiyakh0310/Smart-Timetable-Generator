"""Isha - R19 Announcement endpoints: /api/v1/announcements

Admin only:  list (all statuses), read, create, edit, publish, unpublish, delete.
Any signed-in role (faculty, students; admins too):  GET /published and GET /published/:id - PUBLISHED announcements only.
"""
from flask import Blueprint, g, request

from app.common.auth import role_required
from app.common.pagination import paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import Role
from app.modules.isha import announcement_service as service

bp = Blueprint("announcements", __name__, url_prefix="/api/v1/announcements")


def _filters(published_only: bool) -> dict:
    return {
        "status": None if published_only else service.parse_status(request.args.get("status")),
        "category": service.parse_category(request.args.get("category")),
        "q": request.args.get("q"),
        "published_only": published_only,
    }


# ---------- read-only feed (published only) ----------
@bp.get("/published")
@role_required()
def list_published():
    page, per_page = pagination_args(default_per_page=10, max_per_page=50)
    return success(paginate(service.list_statement(**_filters(True)), page, per_page, service.serialize_many))


@bp.get("/published/<int:announcement_id>")
@role_required()
def get_published(announcement_id):
    return success(service.serialize(service.get_or_404(announcement_id, published_only=True)))


# ---------- management (Admin only) ----------
@bp.get("")
@role_required(Role.ADMIN)
def list_announcements():
    page, per_page = pagination_args(default_per_page=10, max_per_page=100)
    return success(paginate(service.list_statement(**_filters(False)), page, per_page, service.serialize_many))


@bp.get("/<int:announcement_id>")
@role_required(Role.ADMIN)
def get_announcement(announcement_id):
    return success(service.serialize(service.get_or_404(announcement_id)))


@bp.post("")
@role_required(Role.ADMIN)
def create_announcement():
    a = service.create(json_body(), g.current_user.id)
    return success(service.serialize(a), status=201, message="Announcement published." if a.status.value == "published" else "Draft saved.")


@bp.patch("/<int:announcement_id>")
@role_required(Role.ADMIN)
def update_announcement(announcement_id):
    return success(service.serialize(service.update(service.get_or_404(announcement_id), json_body())), message="Announcement updated.")


@bp.post("/<int:announcement_id>/publish")
@role_required(Role.ADMIN)
def publish_announcement(announcement_id):
    return success(service.serialize(service.publish(service.get_or_404(announcement_id))), message="Announcement published.")


@bp.post("/<int:announcement_id>/unpublish")
@role_required(Role.ADMIN)
def unpublish_announcement(announcement_id):
    return success(service.serialize(service.unpublish(service.get_or_404(announcement_id))), message="Announcement moved back to drafts.")


@bp.delete("/<int:announcement_id>")
@role_required(Role.ADMIN)
def delete_announcement(announcement_id):
    service.delete(service.get_or_404(announcement_id))
    return success(message="Announcement deleted.")
