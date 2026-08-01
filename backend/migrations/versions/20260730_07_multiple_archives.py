"""Allow multiple archives per model.

Revision ID: 20260730_07
Revises: 20260730_06
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260730_07"
down_revision: str | Sequence[str] | None = "20260730_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_archives_model_id"), table_name="archives")
    op.create_index(
        op.f("ix_archives_model_id"),
        "archives",
        ["model_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_archives_model_id"), table_name="archives")
    op.execute(
        """
        DELETE FROM archive_entries
        WHERE archive_id IN (
            SELECT duplicate.id
            FROM archives AS duplicate
            WHERE duplicate.id NOT IN (
                SELECT MIN(kept.id) FROM archives AS kept GROUP BY kept.model_id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM archives
        WHERE id NOT IN (
            SELECT MIN(kept.id) FROM archives AS kept GROUP BY kept.model_id
        )
        """
    )
    op.create_index(
        op.f("ix_archives_model_id"),
        "archives",
        ["model_id"],
        unique=True,
    )
