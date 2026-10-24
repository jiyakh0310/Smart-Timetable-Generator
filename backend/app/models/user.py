"""Users and roles (owner: Isha - R1)."""
import enum

from flask import current_app
from sqlalchemy import true
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import TimestampMixin, enum_column


class Role(str, enum.Enum):
    ADMIN = "admin"
    FACULTY = "faculty"
    STUDENT = "student"


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = enum_column(Role, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, server_default=true())
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, plain_password: str) -> None:
        # Production uses Werkzeug's default (scrypt). Only the testing config overrides it, to keep the suite fast.
        method = current_app.config.get("PASSWORD_HASH_METHOD", "scrypt")
        self.password_hash = generate_password_hash(plain_password, method=method)

    def check_password(self, plain_password: str) -> bool:
        return check_password_hash(self.password_hash, plain_password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role.value,
        }
