"""Add direct and inherited custom tags.

Revision ID: 20260730_08
Revises: 20260730_07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_08"
down_revision: str | Sequence[str] | None = "20260730_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_tags_name"), "tags", ["name"], unique=True)
    op.create_table(
        "model_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("is_direct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_inherited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["model_id"], ["library_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("model_id", "tag_id"),
    )
    op.create_index(op.f("ix_model_tags_model_id"), "model_tags", ["model_id"])
    op.create_index(op.f("ix_model_tags_tag_id"), "model_tags", ["tag_id"])
    op.create_table(
        "folder_tag_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("library_source_id", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("recursive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["library_source_id"], ["library_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("library_source_id", "relative_path", "tag_id"),
    )
    op.create_index(op.f("ix_folder_tag_rules_library_source_id"), "folder_tag_rules", ["library_source_id"])
    op.create_index(op.f("ix_folder_tag_rules_tag_id"), "folder_tag_rules", ["tag_id"])


def downgrade() -> None:
    op.drop_table("folder_tag_rules")
    op.drop_table("model_tags")
    op.drop_table("tags")
