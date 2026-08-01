"""Add mandatory password change state.

Revision ID: 20260730_09
Revises: 20260730_08
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260730_09"
down_revision: str | Sequence[str] | None = "20260730_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("must_change_password")
