"""Add live scan progress fields.

Revision ID: 20260812_30
Revises: 20260812_29
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_30"
down_revision: str | Sequence[str] | None = "20260812_29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        batch.add_column(sa.Column("current_model_name", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("models_total", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch:
        batch.drop_column("models_total")
        batch.drop_column("current_model_name")