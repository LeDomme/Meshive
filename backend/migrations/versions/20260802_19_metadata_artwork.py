"""Add custom metadata artwork.

Revision ID: 20260802_19
Revises: 20260802_18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_19"
down_revision: str | Sequence[str] | None = "20260802_18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metadata_artwork",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_value", sa.String(length=512), nullable=False),
        sa.Column("entity_key", sa.String(length=600), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(length=64), nullable=False),
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
        sa.UniqueConstraint("entity_type", "entity_key"),
    )
    op.create_index(
        op.f("ix_metadata_artwork_entity_type"),
        "metadata_artwork",
        ["entity_type"],
    )


def downgrade() -> None:
    op.drop_table("metadata_artwork")
