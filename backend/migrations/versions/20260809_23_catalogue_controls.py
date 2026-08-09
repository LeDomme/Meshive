"""Remove legacy source defaults and add catalogue filter preferences.

Revision ID: 20260809_23
Revises: 20260808_22
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_23"
down_revision: str | None = "20260808_22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("library_sources") as batch:
        batch.drop_column("default_creator")
        batch.drop_column("default_franchise")
        batch.drop_column("default_collection")
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("catalogue_filter_order", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("catalogue_filter_order")
    with op.batch_alter_table("library_sources") as batch:
        batch.add_column(sa.Column("default_creator", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("default_franchise", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("default_collection", sa.String(length=255), nullable=True))
