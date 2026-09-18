"""Persist catalogue navigation mode."""

import sqlalchemy as sa
from alembic import op

revision = "20260918_46"
down_revision = "20260918_45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("catalogue_navigation_mode", sa.String(length=20), nullable=False, server_default="pagination"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("catalogue_navigation_mode")
