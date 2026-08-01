"""Add image thumbnail metadata.

Revision ID: 20260730_04
Revises: 20260730_03
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_04"
down_revision: str | Sequence[str] | None = "20260730_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.add_column(sa.Column("thumbnail_key", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "thumbnail_status",
                sa.String(length=30),
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(sa.Column("thumbnail_error", sa.Text(), nullable=True))
        batch.create_index(
            op.f("ix_model_images_thumbnail_status"),
            ["thumbnail_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.drop_index(op.f("ix_model_images_thumbnail_status"))
        batch.drop_column("thumbnail_error")
        batch.drop_column("thumbnail_status")
        batch.drop_column("thumbnail_key")
