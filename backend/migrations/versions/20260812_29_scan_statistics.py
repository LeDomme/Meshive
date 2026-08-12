"""Add scan progress statistics.

Revision ID: 20260812_29
Revises: 20260812_28
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_29"
down_revision: str | Sequence[str] | None = "20260812_28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "models_skipped",
    "archive_images_reused",
    "archive_images_generated",
    "archive_images_removed",
)


def upgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        for column in _COLUMNS:
            batch.add_column(
                sa.Column(column, sa.Integer(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        for column in reversed(_COLUMNS):
            batch.drop_column(column)