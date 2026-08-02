"""Add automatic tag rules and provenance.

Revision ID: 20260802_20
Revises: 20260802_19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_20"
down_revision: str | Sequence[str] | None = "20260802_19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_tags",
        sa.Column(
            "is_automatic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "scan_runs",
        sa.Column(
            "automatic_tag_matches",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "scan_runs",
        sa.Column(
            "automatic_tags_added",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "scan_runs",
        sa.Column(
            "automatic_tags_removed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "automatic_tag_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=255), nullable=False),
        sa.Column("pattern_key", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tag_id", "pattern_key"),
    )
    op.create_index(
        op.f("ix_automatic_tag_rules_tag_id"),
        "automatic_tag_rules",
        ["tag_id"],
    )
    op.create_index(
        op.f("ix_automatic_tag_rules_enabled"),
        "automatic_tag_rules",
        ["enabled"],
    )

    op.create_table(
        "automatic_tag_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("automatic_tag_rule_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("matched_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["automatic_tag_rule_id"],
            ["automatic_tag_rules.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["model_id"], ["library_models.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("automatic_tag_rule_id", "model_id"),
    )
    op.create_index(
        op.f("ix_automatic_tag_matches_automatic_tag_rule_id"),
        "automatic_tag_matches",
        ["automatic_tag_rule_id"],
    )
    op.create_index(
        op.f("ix_automatic_tag_matches_model_id"),
        "automatic_tag_matches",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_table("automatic_tag_matches")
    op.drop_table("automatic_tag_rules")
    op.drop_column("scan_runs", "automatic_tags_removed")
    op.drop_column("scan_runs", "automatic_tags_added")
    op.drop_column("scan_runs", "automatic_tag_matches")
    op.drop_column("model_tags", "is_automatic")
