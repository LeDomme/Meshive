"""Build the derived, bounded-memory archive browse-node projection."""

from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from meshive.models.catalog import ArchiveBrowseNode, ArchiveEntry

DEFAULT_BATCH_SIZE = 500


def canonical_archive_path(path: str) -> str:
    """Use the reader's POSIX form for stable browse paths and synthetic parents."""
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix().lstrip("/")
    return "" if normalized == "." else normalized.rstrip("/")


def rebuild_archive_browse_nodes(
    session: Session, archive_id: int, *, batch_size: int = DEFAULT_BATCH_SIZE
) -> None:
    """Replace one archive projection without loading all entries into Python."""
    session.execute(delete(ArchiveBrowseNode).where(ArchiveBrowseNode.archive_id == archive_id))
    entries = session.execute(
        select(
            ArchiveEntry.id,
            ArchiveEntry.path,
            ArchiveEntry.name,
            ArchiveEntry.is_directory,
            ArchiveEntry.size_bytes,
            ArchiveEntry.compressed_size_bytes,
            ArchiveEntry.modified_at,
        )
        .where(ArchiveEntry.archive_id == archive_id)
        .order_by(ArchiveEntry.id)
    ).mappings()
    _write_nodes(session, archive_id, entries, batch_size=batch_size)


def _write_nodes(
    session: Session,
    archive_id: int,
    entries: Iterable[Mapping[str, object]],
    *,
    batch_size: int,
) -> None:
    synthetic_rows: list[dict[str, object]] = []
    physical_rows: list[dict[str, object]] = []
    for entry in entries:
        path = canonical_archive_path(str(entry["path"]))
        if not path:
            continue
        parts = PurePosixPath(path).parts
        for depth in range(1, len(parts)):
            parent_path = "/".join(parts[: depth - 1])
            directory_path = "/".join(parts[:depth])
            synthetic_rows.append(
                _node_row(
                    archive_id,
                    directory_path,
                    parent_path,
                    parts[depth - 1],
                    depth,
                    True,
                )
            )
            if len(synthetic_rows) + len(physical_rows) >= batch_size:
                _flush_nodes(session, synthetic_rows, physical_rows)
                synthetic_rows.clear()
                physical_rows.clear()
        physical_rows.append(
            _node_row(
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
        if len(synthetic_rows) + len(physical_rows) >= batch_size:
            _flush_nodes(session, synthetic_rows, physical_rows)
            synthetic_rows.clear()
            physical_rows.clear()
    _flush_nodes(session, synthetic_rows, physical_rows)


def _node_row(
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


def _flush_nodes(
    session: Session,
    synthetic_rows: list[dict[str, object]],
    physical_rows: list[dict[str, object]],
) -> None:
    if synthetic_rows:
        session.execute(insert(ArchiveBrowseNode).prefix_with("OR IGNORE"), synthetic_rows)
    if physical_rows:
        node_insert = insert(ArchiveBrowseNode)
        statement = node_insert.on_conflict_do_update(
            index_elements=["archive_id", "path"],
            set_={
                "parent_path": node_insert.excluded.parent_path,
                "name": node_insert.excluded.name,
                "name_sort_key": node_insert.excluded.name_sort_key,
                "path_sort_key": node_insert.excluded.path_sort_key,
                "depth": node_insert.excluded.depth,
                "is_directory": node_insert.excluded.is_directory,
                "archive_entry_id": node_insert.excluded.archive_entry_id,
                "size_bytes": node_insert.excluded.size_bytes,
                "compressed_size_bytes": node_insert.excluded.compressed_size_bytes,
                "modified_at": node_insert.excluded.modified_at,
            },
        )
        session.execute(statement, physical_rows)
