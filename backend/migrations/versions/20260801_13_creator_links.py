"""Add optional external links for creators.

Revision ID: 20260801_13
Revises: 20260731_12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260801_13"
down_revision: str | Sequence[str] | None = "20260731_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creator_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "creator_name",
            sa.String(255, collation="NOCASE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("creator_name"),
    )
    op.create_index(
        op.f("ix_creator_links_creator_name"),
        "creator_links",
        ["creator_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("creator_links")
