"""Persist administrator-selected primary model images.

Revision ID: 20260808_22
Revises: 20260808_21
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260808_22"
down_revision: str | Sequence[str] | None = "20260808_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.add_column(
            sa.Column(
                "is_primary_override",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.drop_column("is_primary_override")
