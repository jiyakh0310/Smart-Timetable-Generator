"""Diya - R3 Batch endpoints: /api/v1/batches (+ read-only /api/v1/programs lookup).

Read: any signed-in user (batches hold no personal data).  Write: Admin only.
"""
from flask import Blueprint, request

from app.common.auth import role_required
from app.common.pagination import int_arg, paginate, pagination_args
from app.common.responses import success
from app.common.validation import json_body
from app.models import Role
from app.modules.diya import batch_service as service

bp = Blueprint("batches", __name__, url_prefix="/api/v1/batches")
programs_bp = Blueprint("programs", __name__, url_prefix="/api/v1/programs")


@bp.get("")
@role_required()
def list_batches():
    page, per_page = pagination_args(default_per_page=20, max_per_page=100)
    stmt = service.list_statement(
        department_id=int_arg("department_id", minimum=1),
        program_id=int_arg("program_id", minimum=1),
        semester_no=int_arg("semester_no", minimum=1, maximum=12),
        q=request.args.get("q"),
    )
    return success(paginate(stmt, page, per_page, service.serialize_many))


@bp.get("/<int:batch_id>")
@role_required()
def get_batch(batch_id):
    return success(service.serialize_many([service.get_or_404(batch_id)])[0])


@bp.post("")
@role_required(Role.ADMIN)
def create_batch():
    return success(service.serialize_many([service.create_batch(json_body())])[0], status=201, message="Batch created.")


@bp.patch("/<int:batch_id>")
@role_required(Role.ADMIN)
def update_batch(batch_id):
    batch = service.update_batch(service.get_or_404(batch_id), json_body())
    return success(service.serialize_many([batch])[0], message="Batch updated.")


@bp.delete("/<int:batch_id>")
@role_required(Role.ADMIN)
def delete_batch(batch_id):
    service.delete_batch(service.get_or_404(batch_id))
    return success(message="Batch deleted.")


@programs_bp.get("")
@role_required()
def list_programs():
    """Lookup list for form dropdowns (programs are not managed from the UI yet)."""
    return success({"items": service.list_programs()})
