"""Add derived archive browse nodes and bounded backfill.

Revision ID: 20260911_39
Revises: 20260910_38

The projection is rebuildable from archive_entries. Downgrade intentionally
removes only this derived data; it never alters physical archive listings.
"""

from collections.abc import Sequence
from pathlib import PurePosixPath

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_39"
down_revision: str | Sequence[str] | None = "20260910_38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH_SIZE = 500


def upgrade() -> None:
    op.create_table(
        "archive_browse_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("archive_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("parent_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("name_sort_key", sa.Text(), nullable=False),
        sa.Column("path_sort_key", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("is_directory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archive_entry_id", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("compressed_size_bytes", sa.Integer(), nullable=True),
        sa.Column("modified_at", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["archive_entry_id"], ["archive_entries.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("archive_id", "path"),
        sa.UniqueConstraint("archive_entry_id"),
    )
    op.create_index(
        "ix_archive_browse_nodes_children",
        "archive_browse_nodes",
        [
            "archive_id",
            "parent_path",
            sa.text("is_directory DESC"),
            "name_sort_key",
            "path",
        ],
    )
    op.create_index("ix_archive_browse_nodes_archive_id", "archive_browse_nodes", ["archive_id"])
    _backfill_existing_entries()


def downgrade() -> None:
    op.drop_index("ix_archive_browse_nodes_archive_id", table_name="archive_browse_nodes")
    op.drop_index("ix_archive_browse_nodes_children", table_name="archive_browse_nodes")
    op.drop_table("archive_browse_nodes")


def _backfill_existing_entries() -> None:
    """Keyset/batch projection; safe to restart after an interrupted upgrade."""
    connection = op.get_bind()
    archive_id = 0
    while True:
        archive_ids = [
            row.id
            for row in connection.execute(
                sa.text(
                    "SELECT id FROM archives WHERE id > :archive_id ORDER BY id LIMIT :limit"
                ),
                {"archive_id": archive_id, "limit": _BATCH_SIZE},
            )
        ]
        if not archive_ids:
            return
        for current_archive_id in archive_ids:
            _backfill_archive(connection, current_archive_id)
        archive_id = archive_ids[-1]


def _backfill_archive(connection: sa.Connection, archive_id: int) -> None:
    synthetic_rows: list[dict[str, object]] = []
    physical_rows: list[dict[str, object]] = []
    entries = connection.execute(
        sa.text(
            "SELECT id, path, is_directory, size_bytes, compressed_size_bytes, modified_at "
            "FROM archive_entries WHERE archive_id = :archive_id ORDER BY id"
        ),
        {"archive_id": archive_id},
    ).mappings()
    for entry in entries:
        path = _canonical_path(str(entry["path"]))
        if not path:
            continue
        parts = PurePosixPath(path).parts
        for depth in range(1, len(parts)):
            synthetic_rows.append(
                _node(
                    archive_id,
                    "/".join(parts[:depth]),
                    "/".join(parts[: depth - 1]),
                    parts[depth - 1],
                    depth,
                    True,
                )
            )
            if len(synthetic_rows) + len(physical_rows) >= _BATCH_SIZE:
                _flush(connection, synthetic_rows, physical_rows)
                synthetic_rows.clear()
                physical_rows.clear()
        physical_rows.append(
            _node(
                archive_id,
                path,
                "/".join(parts[:-1]),
                parts[-1],
                len(parts),
                bool(entry["is_directory"]),
                archive_entry_id=int(entry["id"]),
                size_bytes=entry["size_bytes"],
                compressed_size_bytes=entry["compressed_size_bytes"],
                modified_at=entry["modified_at"],
            )
        )
        if len(synthetic_rows) + len(physical_rows) >= _BATCH_SIZE:
            _flush(connection, synthetic_rows, physical_rows)
            synthetic_rows.clear()
            physical_rows.clear()
    _flush(connection, synthetic_rows, physical_rows)


def _canonical_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix().lstrip("/")
    return "" if normalized == "." else normalized.rstrip("/")


def _node(
    archive_id: int,
    path: str,
    parent_path: str,
    name: str,
    depth: int,
    is_directory: bool,
    *,
    archive_entry_id: int | None = None,
    size_bytes: object = None,
    compressed_size_bytes: object = None,
    modified_at: object = None,
) -> dict[str, object]:
    return {
        "archive_id": archive_id,
        "path": path,
        "parent_path": parent_path,
        "name": name,
        "name_sort_key": name.casefold(),
        "path_sort_key": path.casefold(),
        "depth": depth,
        "is_directory": is_directory,
        "archive_entry_id": archive_entry_id,
        "size_bytes": size_bytes,
        "compressed_size_bytes": compressed_size_bytes,
        "modified_at": modified_at,
    }


def _flush(
    connection: sa.Connection,
    synthetic_rows: list[dict[str, object]],
    physical_rows: list[dict[str, object]],
) -> None:
    if synthetic_rows:
        connection.execute(
            sa.text(
                "INSERT OR IGNORE INTO archive_browse_nodes "
                "(archive_id, path, parent_path, name, name_sort_key, path_sort_key, depth, "
                "is_directory, archive_entry_id, size_bytes, compressed_size_bytes, modified_at) "
                "VALUES (:archive_id, :path, :parent_path, :name, :name_sort_key, :path_sort_key, "
                ":depth, :is_directory, :archive_entry_id, :size_bytes, :compressed_size_bytes, "
                ":modified_at)"
            ),
            synthetic_rows,
        )
    if physical_rows:
        connection.execute(
            sa.text(
                "INSERT INTO archive_browse_nodes "
                "(archive_id, path, parent_path, name, name_sort_key, path_sort_key, depth, "
                "is_directory, archive_entry_id, size_bytes, compressed_size_bytes, modified_at) "
                "VALUES (:archive_id, :path, :parent_path, :name, :name_sort_key, :path_sort_key, "
                ":depth, :is_directory, :archive_entry_id, :size_bytes, :compressed_size_bytes, "
                ":modified_at) "
                "ON CONFLICT(archive_id, path) DO UPDATE SET "
                "parent_path=excluded.parent_path, name=excluded.name, "
                "name_sort_key=excluded.name_sort_key, path_sort_key=excluded.path_sort_key, "
                "depth=excluded.depth, is_directory=excluded.is_directory, "
                "archive_entry_id=excluded.archive_entry_id, size_bytes=excluded.size_bytes, "
                "compressed_size_bytes=excluded.compressed_size_bytes, modified_at=excluded.modified_at"
            ),
            physical_rows,
        )
