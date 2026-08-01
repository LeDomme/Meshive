"""Add automatic backup schedule and history.

Revision ID: 20260731_11
Revises: 20260730_10
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260731_11"
down_revision: str | Sequence[str] | None = "20260730_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("time_of_day", sa.String(5), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("retention_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("INSERT INTO backup_schedule(id, enabled, frequency, time_of_day, weekday, timezone, destination, retention_days, retention_count) VALUES (1, 0, 'daily', '03:00', 0, 'Europe/Berlin', 'automatic', 30, 14)")
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_backup_runs_status"), "backup_runs", ["status"])


def downgrade() -> None:
    op.drop_table("backup_runs")
    op.drop_table("backup_schedule")
