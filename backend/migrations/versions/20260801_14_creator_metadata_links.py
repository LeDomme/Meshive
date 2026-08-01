"""Allow multiple typed metadata links per creator.

Revision ID: 20260801_14
Revises: 20260801_13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260801_14"
down_revision: str | Sequence[str] | None = "20260801_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creator_metadata_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "creator_name",
            sa.String(255, collation="NOCASE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column(
            "label",
            sa.String(80, collation="NOCASE"),
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
        sa.UniqueConstraint("creator_name", "kind", "label"),
    )
    op.create_index(
        op.f("ix_creator_metadata_links_creator_name"),
        "creator_metadata_links",
        ["creator_name"],
    )
    op.execute(
        sa.text(
            "INSERT INTO creator_metadata_links "
            "(creator_name, kind, label, url, created_at, updated_at) "
            "SELECT creator_name, 'website', 'Website', url, created_at, updated_at "
            "FROM creator_links"
        )
    )
    op.drop_table("creator_links")


def downgrade() -> None:
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
    op.execute(
        sa.text(
            "INSERT INTO creator_links (creator_name, url, created_at, updated_at) "
            "SELECT creator_name, MIN(url), MIN(created_at), MAX(updated_at) "
            "FROM creator_metadata_links GROUP BY creator_name"
        )
    )
    op.drop_table("creator_metadata_links")
