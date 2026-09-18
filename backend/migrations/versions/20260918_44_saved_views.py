"""Add user-specific saved catalogue views.

Revision ID: 20260918_44
Revises: 20260917_43
"""

import sqlalchemy as sa
from alembic import op

revision = "20260918_44"
down_revision = "20260917_43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("catalogue_state", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "normalized_name"),
    )
    op.create_index("ix_saved_views_user_id", "saved_views", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_saved_views_user_id", table_name="saved_views")
    op.drop_table("saved_views")
