"""Create library sources.

Revision ID: 20260730_01
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "library_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("directory_pattern", sa.Text(), nullable=False),
        sa.Column("model_pattern", sa.Text(), nullable=True),
        sa.Column("default_creator", sa.String(length=255), nullable=True),
        sa.Column("default_franchise", sa.String(length=255), nullable=True),
        sa.Column("default_collection", sa.String(length=255), nullable=True),
        sa.Column("archive_formats", sa.JSON(), nullable=False),
        sa.Column("image_formats", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("scan_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("root_path"),
    )
    op.create_index(
        op.f("ix_library_sources_name"), "library_sources", ["name"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_library_sources_name"), table_name="library_sources")
    op.drop_table("library_sources")
