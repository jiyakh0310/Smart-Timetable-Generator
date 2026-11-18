"""R19 announcements: add the `category` column.

ADDITIVE ONLY. This adds one column to the existing `announcements` table (created by the initial migration); no table is created,
dropped, truncated or rewritten, and no row is deleted or changed except that every existing row receives the default
category 'general' (the column is NOT NULL with a server default, so the existing rows stay valid).

Safe to run twice: if the column is already there (for example the schema was created from the models) nothing happens.
The downgrade intentionally does nothing: removing the column would destroy the categories administrators have chosen, and this
project's rule is never to drop data. To undo, leave the column in place; older code simply ignores it.

Revision ID: 7c1d9a4e2b60
Revises: ca2b3aac461f
"""
import sqlalchemy as sa
from alembic import op

revision = "7c1d9a4e2b60"
down_revision = "ca2b3aac461f"
branch_labels = None
depends_on = None

CATEGORIES = ("general", "academic", "timetable_change", "exam", "urgent")


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("announcements")}
    if "category" in columns:
        return
    op.add_column(
        "announcements",
        sa.Column("category", sa.Enum(*CATEGORIES, name="announcementcategory", native_enum=False, length=20), nullable=False, server_default="general"),
    )


def downgrade():
    # Deliberately a no-op: see the module docstring.
    pass
