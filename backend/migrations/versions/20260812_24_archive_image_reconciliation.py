"""Add stable archive-image reconciliation metadata.

Revision ID: 20260812_24
Revises: 20260809_23
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_24"
down_revision: str | Sequence[str] | None = "20260809_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("library_models") as batch:
        batch.add_column(
            sa.Column("archive_image_policy_key", sa.String(length=64), nullable=True)
        )
    with op.batch_alter_table("model_images") as batch:
        batch.add_column(
            sa.Column(
                "archive_entry_fingerprint", sa.String(length=64), nullable=True
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.drop_column("archive_entry_fingerprint")
    with op.batch_alter_table("library_models") as batch:
        batch.drop_column("archive_image_policy_key")