"""Remove catalogue rows left behind by deleted sources.

Revision ID: 20260730_06
Revises: 20260730_05
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260730_06"
down_revision: str | Sequence[str] | None = "20260730_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM scan_issues
        WHERE scan_run_id NOT IN (SELECT id FROM scan_runs)
           OR model_id IN (
               SELECT id FROM library_models
               WHERE library_source_id NOT IN (SELECT id FROM library_sources)
           )
        """
    )
    op.execute(
        """
        DELETE FROM archive_entries
        WHERE archive_id IN (
            SELECT archives.id
            FROM archives
            JOIN library_models ON library_models.id = archives.model_id
            WHERE library_models.library_source_id
                  NOT IN (SELECT id FROM library_sources)
        )
        """
    )
    op.execute(
        """
        DELETE FROM model_images
        WHERE model_id IN (
            SELECT id FROM library_models
            WHERE library_source_id NOT IN (SELECT id FROM library_sources)
        )
        """
    )
    op.execute(
        """
        DELETE FROM archives
        WHERE model_id IN (
            SELECT id FROM library_models
            WHERE library_source_id NOT IN (SELECT id FROM library_sources)
        )
        """
    )
    op.execute(
        """
        DELETE FROM library_models
        WHERE library_source_id NOT IN (SELECT id FROM library_sources)
        """
    )
    op.execute(
        """
        DELETE FROM scan_issues
        WHERE scan_run_id IN (
            SELECT id FROM scan_runs
            WHERE library_source_id NOT IN (SELECT id FROM library_sources)
        )
        """
    )
    op.execute(
        """
        DELETE FROM scan_runs
        WHERE library_source_id NOT IN (SELECT id FROM library_sources)
        """
    )


def downgrade() -> None:
    # Deleted derived catalogue data cannot and should not be reconstructed.
    pass
