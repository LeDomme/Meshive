"""Add per-source automatic scan schedules.

Revision ID: 20260731_12
Revises: 20260731_11
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260731_12"
down_revision: str | Sequence[str] | None = "20260731_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "library_sources",
        sa.Column(
            "auto_scan_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "library_sources",
        sa.Column(
            "auto_scan_frequency",
            sa.String(10),
            nullable=False,
            server_default="daily",
        ),
    )
    op.add_column(
        "library_sources",
        sa.Column(
            "auto_scan_time",
            sa.String(5),
            nullable=False,
            server_default="02:00",
        ),
    )
    op.add_column(
        "library_sources",
        sa.Column(
            "auto_scan_weekday",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "library_sources",
        sa.Column(
            "auto_scan_timezone",
            sa.String(64),
            nullable=False,
            server_default="Europe/Berlin",
        ),
    )
    op.add_column(
        "scan_runs",
        sa.Column(
            "trigger",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
    )


def downgrade() -> None:
    op.drop_column("scan_runs", "trigger")
    op.drop_column("library_sources", "auto_scan_timezone")
    op.drop_column("library_sources", "auto_scan_weekday")
    op.drop_column("library_sources", "auto_scan_time")
    op.drop_column("library_sources", "auto_scan_frequency")
    op.drop_column("library_sources", "auto_scan_enabled")
