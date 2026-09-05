"""Add canonical assignment-rule provenance.

Revision ID: 20260910_38
Revises: 20260909_37
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_38"
down_revision: str | Sequence[str] | None = "20260909_37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_tags",
        sa.Column("is_assignment_rule", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("model_tags", "is_assignment_rule")
