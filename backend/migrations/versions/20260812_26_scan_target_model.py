"""Add target model details to scan activity.

Revision ID: 20260812_26
Revises: 20260812_25
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_26"
down_revision: str | Sequence[str] | None = "20260812_25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        batch.add_column(
            sa.Column("target_model_id", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("target_model_name", sa.String(length=512), nullable=True)
        )
        batch.create_index("ix_scan_runs_target_model_id", ["target_model_id"])


def downgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        batch.drop_index("ix_scan_runs_target_model_id")
        batch.drop_column("target_model_name")
        batch.drop_column("target_model_id")