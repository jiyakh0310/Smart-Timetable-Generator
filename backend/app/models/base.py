"""Helpers shared by all models."""
from app.extensions import db


def enum_column(enum_cls, **kwargs):
    """Store a Python Enum as a short VARCHAR holding the enum *value*.

    Plain VARCHAR (not a native MySQL ENUM) keeps migrations simple when
    values are added later.
    """
    return db.Column(
        db.Enum(
            enum_cls,
            native_enum=False,
            length=20,
            validate_strings=True,
            values_callable=lambda members: [m.value for m in members],
        ),
        **kwargs,
    )


class TimestampMixin:
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now(), nullable=False)
