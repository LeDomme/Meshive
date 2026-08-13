"""Track the technical archive-listing parser policy.

Revision ID: 20260813_31
Revises: 20260812_30
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260813_31"
down_revision = "20260812_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "archives",
        sa.Column("listing_policy_key", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("archives", "listing_policy_key")
