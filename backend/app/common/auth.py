"""Backend role-based authorization. Every protected route uses @role_required.

The role is read from the *database* on every request, not trusted from the
token, so disabling a user or changing a role takes effect immediately.
"""
from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.common.errors import AppError
from app.extensions import db
from app.models import Role, User


def current_user() -> User:
    return g.current_user


def role_required(*roles: Role):
    """Require a valid token and (if given) one of `roles`. No roles = any signed-in user."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = db.session.get(User, int(get_jwt_identity()))
            if user is None or not user.is_active:
                raise AppError("unauthorized", "Account not found or disabled.", 401)
            if roles and user.role not in roles:
                raise AppError("forbidden", "You do not have permission to perform this action.", 403)
            g.current_user = user
            return view(*args, **kwargs)

        return wrapper

    return decorator
