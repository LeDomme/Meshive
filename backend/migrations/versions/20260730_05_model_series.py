"""Add model series metadata.

Revision ID: 20260730_05
Revises: 20260730_04
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_05"
down_revision: str | Sequence[str] | None = "20260730_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("library_models") as batch:
        batch.add_column(sa.Column("series", sa.String(length=255), nullable=True))
        batch.create_index(
            op.f("ix_library_models_series"), ["series"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("library_models") as batch:
        batch.drop_index(op.f("ix_library_models_series"))
        batch.drop_column("series")
