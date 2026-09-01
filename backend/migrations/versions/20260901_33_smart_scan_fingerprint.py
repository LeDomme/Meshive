"""Add persisted Smart Scan fingerprints.

Revision ID: 20260901_33
Revises: 20260901_32
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_33"
down_revision = "20260901_32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "library_models", sa.Column("scan_fingerprint", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "library_models", sa.Column("scan_policy_key", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("library_models", "scan_policy_key")
    op.drop_column("library_models", "scan_fingerprint")
