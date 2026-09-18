"""Persist catalogue action control order.

Revision ID: 20260918_45
Revises: 20260918_44
"""

import sqlalchemy as sa
from alembic import op

revision = "20260918_45"
down_revision = "20260918_44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("catalogue_action_order", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("catalogue_action_order")
