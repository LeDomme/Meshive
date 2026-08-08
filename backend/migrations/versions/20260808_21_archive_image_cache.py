"""Store cached images derived from archive entries.

Revision ID: 20260808_21
Revises: 20260802_20
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260808_21"
down_revision: str | Sequence[str] | None = "20260802_20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.add_column(
            sa.Column(
                "storage_kind",
                sa.String(length=20),
                nullable=False,
                server_default="source",
            )
        )
        batch.add_column(sa.Column("archive_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("archive_entry_path", sa.Text(), nullable=True))
        batch.add_column(sa.Column("cache_key", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_model_images_archive_id_archives",
            "archives",
            ["archive_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_model_images_archive_id", ["archive_id"], unique=False)
        batch.create_index("ix_model_images_storage_kind", ["storage_kind"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("model_images") as batch:
        batch.drop_index("ix_model_images_storage_kind")
        batch.drop_index("ix_model_images_archive_id")
        batch.drop_constraint("fk_model_images_archive_id_archives", type_="foreignkey")
        batch.drop_column("cache_key")
        batch.drop_column("archive_entry_path")
        batch.drop_column("archive_id")
        batch.drop_column("storage_kind")
