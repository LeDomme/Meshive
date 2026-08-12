"""Add explicit scan modes.

Revision ID: 20260812_25
Revises: 20260812_24
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_25"
down_revision: str | Sequence[str] | None = "20260812_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        batch.add_column(
            sa.Column("mode", sa.String(length=32), nullable=False, server_default="full")
        )
        batch.create_index("ix_scan_runs_mode", ["mode"])


def downgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        batch.drop_index("ix_scan_runs_mode")
        batch.drop_column("mode")