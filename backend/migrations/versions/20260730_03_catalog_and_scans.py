"""Create catalogue and scan tables.

Revision ID: 20260730_03
Revises: 20260730_02
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_03"
down_revision: str | Sequence[str] | None = "20260730_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_source_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("models_found", sa.Integer(), nullable=False),
        sa.Column("models_added", sa.Integer(), nullable=False),
        sa.Column("models_updated", sa.Integer(), nullable=False),
        sa.Column("models_missing", sa.Integer(), nullable=False),
        sa.Column("issues_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_source_id"], ["library_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scan_runs_library_source_id"),
        "scan_runs",
        ["library_source_id"],
        unique=False,
    )
    op.create_index(op.f("ix_scan_runs_status"), "scan_runs", ["status"], unique=False)

    op.create_table(
        "library_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_source_id", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("creator", sa.String(length=255), nullable=True),
        sa.Column("franchise", sa.String(length=255), nullable=True),
        sa.Column("collection", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_seen_scan_id", sa.Integer(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_source_id"], ["library_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_scan_id"], ["scan_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("library_source_id", "relative_path"),
    )
    for column in ("collection", "creator", "franchise", "library_source_id", "name", "status"):
        op.create_index(
            op.f(f"ix_library_models_{column}"),
            "library_models",
            [column],
            unique=False,
        )

    op.create_table(
        "archives",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=1024), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("modified_ns", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("uncompressed_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["library_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_archives_model_id"), "archives", ["model_id"], unique=True)
    op.create_index(op.f("ix_archives_status"), "archives", ["status"], unique=False)

    op.create_table(
        "archive_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("archive_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("is_directory", sa.Boolean(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("compressed_size_bytes", sa.Integer(), nullable=True),
        sa.Column("crc", sa.String(length=64), nullable=True),
        sa.Column("modified_at", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("archive_id", "path"),
    )
    op.create_index(
        op.f("ix_archive_entries_archive_id"),
        "archive_entries",
        ["archive_id"],
        unique=False,
    )

    op.create_table(
        "model_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=1024), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("modified_ns", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["library_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "relative_path"),
    )
    op.create_index(
        op.f("ix_model_images_model_id"), "model_images", ["model_id"], unique=False
    )

    op.create_table(
        "scan_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_run_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["library_models.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["scan_run_id"], ["scan_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scan_issues_code"), "scan_issues", ["code"], unique=False
    )
    op.create_index(
        op.f("ix_scan_issues_scan_run_id"),
        "scan_issues",
        ["scan_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scan_issues_scan_run_id"), table_name="scan_issues")
    op.drop_index(op.f("ix_scan_issues_code"), table_name="scan_issues")
    op.drop_table("scan_issues")
    op.drop_index(op.f("ix_model_images_model_id"), table_name="model_images")
    op.drop_table("model_images")
    op.drop_index(op.f("ix_archive_entries_archive_id"), table_name="archive_entries")
    op.drop_table("archive_entries")
    op.drop_index(op.f("ix_archives_status"), table_name="archives")
    op.drop_index(op.f("ix_archives_model_id"), table_name="archives")
    op.drop_table("archives")
    for column in ("status", "name", "library_source_id", "franchise", "creator", "collection"):
        op.drop_index(op.f(f"ix_library_models_{column}"), table_name="library_models")
    op.drop_table("library_models")
    op.drop_index(op.f("ix_scan_runs_status"), table_name="scan_runs")
    op.drop_index(op.f("ix_scan_runs_library_source_id"), table_name="scan_runs")
    op.drop_table("scan_runs")
