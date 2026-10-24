"""Isha - authentication endpoints: /api/v1/auth/*"""
from flask import Blueprint
from flask_jwt_extended import create_access_token

from app.common.auth import current_user, role_required
from app.common.responses import success
from app.common.validation import json_body, required_strings
from app.modules.isha import services

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@bp.post("/login")
def login():
    data = json_body()
    fields = required_strings(data, "email", "password")
    user = services.authenticate(fields["email"], data["password"])  # password is never stripped
    token = create_access_token(identity=str(user.id))
    return success({"token": token, "user": services.profile_for(user)})


@bp.get("/me")
@role_required()
def me():
    return success(services.profile_for(current_user()))


@bp.post("/change-password")
@role_required()
def change_password():
    data = json_body()
    fields = required_strings(data, "current_password", "new_password")
    services.change_password(current_user(), data["current_password"], fields["new_password"])
    return success(message="Password updated.")
