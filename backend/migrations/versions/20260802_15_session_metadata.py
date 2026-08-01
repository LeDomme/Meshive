"""Add privacy-conscious client metadata to user sessions.

Revision ID: 20260802_15
Revises: 20260801_14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_15"
down_revision: str | Sequence[str] | None = "20260801_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.add_column(sa.Column("browser", sa.String(80), nullable=True))
        batch_op.add_column(
            sa.Column("operating_system", sa.String(80), nullable=True)
        )
        batch_op.add_column(sa.Column("device_type", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_column("device_type")
        batch_op.drop_column("operating_system")
        batch_op.drop_column("browser")
