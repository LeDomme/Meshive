"""Add the live scan phase.

Revision ID: 20260901_32
Revises: 20260813_31
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_32"
down_revision = "20260813_31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_runs", sa.Column("current_phase", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("scan_runs", "current_phase")
