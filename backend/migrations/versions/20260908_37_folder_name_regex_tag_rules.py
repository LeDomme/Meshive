"""Add folder-name regex tag rules and provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_37"
down_revision: str | Sequence[str] | None = "20260906_36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_tags",
        sa.Column("is_folder_name_regex", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "folder_name_regex_tag_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=255), nullable=False),
        sa.Column("pattern_key", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tag_id", "pattern_key"),
    )
    op.create_index(op.f("ix_folder_name_regex_tag_rules_tag_id"), "folder_name_regex_tag_rules", ["tag_id"])
    op.create_index(op.f("ix_folder_name_regex_tag_rules_enabled"), "folder_name_regex_tag_rules", ["enabled"])
    op.create_table(
        "folder_name_regex_tag_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("folder_name_regex_tag_rule_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["folder_name_regex_tag_rule_id"], ["folder_name_regex_tag_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["library_models.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("folder_name_regex_tag_rule_id", "model_id"),
    )
    op.create_index(op.f("ix_folder_name_regex_tag_matches_folder_name_regex_tag_rule_id"), "folder_name_regex_tag_matches", ["folder_name_regex_tag_rule_id"])
    op.create_index(op.f("ix_folder_name_regex_tag_matches_model_id"), "folder_name_regex_tag_matches", ["model_id"])


def downgrade() -> None:
    op.drop_table("folder_name_regex_tag_matches")
    op.drop_table("folder_name_regex_tag_rules")
    op.drop_column("model_tags", "is_folder_name_regex")
