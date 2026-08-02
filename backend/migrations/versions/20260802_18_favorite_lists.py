"""Add private user favorite lists.

Revision ID: 20260802_18
Revises: 20260802_17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_18"
down_revision: str | Sequence[str] | None = "20260802_17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favorite_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "normalized_name"),
    )
    op.create_index(
        op.f("ix_favorite_lists_user_id"), "favorite_lists", ["user_id"]
    )
    op.create_table(
        "favorite_list_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("favorite_list_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_key", sa.String(length=600), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["favorite_list_id"], ["favorite_lists.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["library_models.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("favorite_list_id", "entity_type", "entity_key"),
    )
    op.create_index(
        op.f("ix_favorite_list_items_favorite_list_id"),
        "favorite_list_items",
        ["favorite_list_id"],
    )
    op.create_index(
        op.f("ix_favorite_list_items_model_id"),
        "favorite_list_items",
        ["model_id"],
    )
    op.create_index(
        op.f("ix_favorite_list_items_tag_id"),
        "favorite_list_items",
        ["tag_id"],
    )


def downgrade() -> None:
    op.drop_table("favorite_list_items")
    op.drop_table("favorite_lists")
