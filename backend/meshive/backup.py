import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from meshive.config import get_settings

_MANIFEST_MAX_BYTES = 64 * 1024
_COPY_BLOCK_BYTES = 1024 * 1024


def database_path() -> Path:
    url = get_settings().effective_database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise RuntimeError("Backup and restore currently require a SQLite database")
    return Path(url.removeprefix(prefix)).resolve()


def create_backup(output: Path | None = None) -> Path:
    source = database_path()
    if not source.is_file():
        raise RuntimeError(f"Database not found: {source}")
    if output is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = get_settings().backup_dir / "manual" / f"meshive-manual-{timestamp}.zip"
    output = output.resolve()
    if output == source:
        raise RuntimeError("Backup output must differ from the live database")
    if output.suffix.lower() == ".zip":
        return _create_zip_backup(source, output)
    return _create_legacy_sqlite_backup(source, output)


def _create_zip_backup(source: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = output.with_name(f".{output.name}.tmp")
    temporary_archive.unlink(missing_ok=True)
    temporary_root = get_settings().data_dir / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="backup-", dir=temporary_root) as work:
            snapshot = Path(work) / "meshive.sqlite3"
            _create_sqlite_snapshot(source, snapshot)
            _validate_backup_size(snapshot.stat().st_size)
            manifest = {
                "format": "meshive-backup-v1",
                "created_at": datetime.now(UTC).isoformat(),
                "database_file": snapshot.name,
                "size_bytes": snapshot.stat().st_size,
                "sha256": _sha256(snapshot),
            }
            with zipfile.ZipFile(
                temporary_archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.write(snapshot, snapshot.name)
                archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        os.replace(temporary_archive, output)
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise
    return output


def _create_legacy_sqlite_backup(source: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    _remove_sqlite_file(temporary)

    try:
        _create_sqlite_snapshot(source, temporary)
        _validate_backup_size(temporary.stat().st_size)
        os.replace(temporary, output)
    except Exception:
        _remove_sqlite_file(temporary)
        raise

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "database_file": output.name,
        "size_bytes": output.stat().st_size,
        "sha256": _sha256(output),
    }
    output.with_suffix(f"{output.suffix}.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return output


def _create_sqlite_snapshot(source: Path, output: Path) -> None:
    with (
        closing(sqlite3.connect(source)) as live,
        closing(sqlite3.connect(output)) as snapshot,
    ):
        live.backup(snapshot)
        snapshot.execute("PRAGMA journal_mode=DELETE")
    _validate_sqlite_database(output)
    _remove_sqlite_sidecars(output)


def delete_backup_files(path: Path) -> None:
    """Remove a backup, its manifest, and temporary SQLite sidecar files."""
    path = path.resolve()
    _remove_sqlite_file(path)
    path.with_suffix(f"{path.suffix}.json").unlink(missing_ok=True)
    _remove_sqlite_file(path.with_name(f".{path.name}.tmp"))


def cleanup_orphaned_backup_sidecars(root: Path, *, minimum_age: int = 300) -> int:
    """Remove stale temporary WAL/SHM files left by an interrupted backup."""
    root = root.resolve()
    if not root.is_dir():
        return 0
    cutoff = time.time() - minimum_age
    removed = 0
    for pattern in ("*.tmp-wal", "*.tmp-shm"):
        for candidate in root.rglob(pattern):
            path = candidate.resolve()
            if root not in path.parents or path.stat().st_mtime > cutoff:
                continue
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def restore_backup(input_path: Path, *, confirmed_stopped: bool) -> Path | None:
    if not confirmed_stopped:
        raise RuntimeError(
            "Restore requires --confirm-stopped after the regular Meshive container is stopped"
        )
    source = input_path.resolve()
    if not source.is_file():
        raise RuntimeError(f"Backup not found: {source}")
    target = database_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    with _backup_database(source) as backup_database:
        _validate_restore_space(
            target.parent, backup_database.stat().st_size, additional_copies=1
        )
        _validate_sqlite_database(backup_database)
        safety_backup = None
        if target.is_file():
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            safety_backup = create_backup(
                get_settings().backup_dir
                / "pre-restore"
                / f"pre-restore-{timestamp}.zip"
            )

        temporary = target.with_name(f".{target.name}.restore")
        _remove_sqlite_file(temporary)
        try:
            with (
                closing(sqlite3.connect(backup_database)) as backup,
                closing(sqlite3.connect(temporary)) as restored,
            ):
                backup.backup(restored)
            _validate_sqlite_database(temporary)
            _remove_sqlite_sidecars(temporary)
            _remove_sqlite_sidecars(target)
            os.replace(temporary, target)
        except Exception:
            _remove_sqlite_file(temporary)
            raise
    return safety_backup


def validate_backup(path: Path) -> None:
    with _backup_database(path.resolve()) as backup_database:
        _validate_sqlite_database(backup_database)


@contextmanager
def _backup_database(source: Path) -> Iterator[Path]:
    if source.suffix.lower() != ".zip":
        _validate_backup_size(source.stat().st_size)
        manifest_path = source.with_suffix(f"{source.suffix}.json")
        if manifest_path.is_file():
            manifest = _read_json_file(manifest_path)
            if manifest.get("sha256") != _sha256(source):
                raise RuntimeError("Backup checksum does not match its manifest")
        yield source
        return

    temporary_root = get_settings().data_dir / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=temporary_root) as work:
        extracted = Path(work) / "meshive.sqlite3"
        try:
            with zipfile.ZipFile(source, mode="r") as archive:
                members = archive.infolist()
                if len(members) != 2 or {item.filename for item in members} != {
                    "meshive.sqlite3",
                    "manifest.json",
                }:
                    raise RuntimeError("Backup archive has an invalid file structure")
                manifest_info = archive.getinfo("manifest.json")
                if manifest_info.file_size > _MANIFEST_MAX_BYTES:
                    raise RuntimeError("Backup manifest exceeds the size limit")
                manifest = json.loads(archive.read(manifest_info))
                if not isinstance(manifest, dict):
                    raise RuntimeError("Backup archive has an invalid manifest")
                if (
                    manifest.get("format") != "meshive-backup-v1"
                    or manifest.get("database_file") != "meshive.sqlite3"
                ):
                    raise RuntimeError("Backup archive has an invalid manifest")
                declared_size = manifest.get("size_bytes")
                if isinstance(declared_size, bool) or not isinstance(declared_size, int):
                    raise RuntimeError("Backup manifest has an invalid database size")
                _validate_backup_size(declared_size)
                database_info = archive.getinfo("meshive.sqlite3")
                if database_info.file_size != declared_size:
                    raise RuntimeError(
                        "Backup database size does not match its ZIP metadata"
                    )
                _validate_restore_space(temporary_root, declared_size)
                with (
                    archive.open(database_info) as source_file,
                    extracted.open("wb") as target,
                ):
                    _copy_backup_database(source_file, target, declared_size)
        except (
            KeyError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            zipfile.BadZipFile,
        ) as error:
            raise RuntimeError("Backup archive is invalid") from error
        if manifest.get("size_bytes") != extracted.stat().st_size:
            raise RuntimeError("Backup database size does not match its manifest")
        if manifest.get("sha256") != _sha256(extracted):
            raise RuntimeError("Backup checksum does not match its manifest")
        yield extracted


def _validate_backup_size(size_bytes: int) -> None:
    maximum = get_settings().backup_max_restore_bytes
    if size_bytes <= 0:
        raise RuntimeError("Backup database is empty")
    if size_bytes > maximum:
        raise RuntimeError(
            f"Backup database exceeds the configured {maximum} byte limit"
        )


def _validate_restore_space(
    temporary_root: Path, database_size: int, *, additional_copies: int = 2
) -> None:
    settings = get_settings()
    required = (
        database_size * additional_copies
        + settings.backup_restore_min_free_bytes
    )
    available = shutil.disk_usage(temporary_root).free
    if available < required:
        raise RuntimeError(
            "Insufficient free space for restore: "
            f"{required} bytes required, {available} bytes available"
        )


def _copy_backup_database(source, target, expected_size: int) -> None:
    copied = 0
    while block := source.read(min(_COPY_BLOCK_BYTES, expected_size - copied + 1)):
        copied += len(block)
        if copied > expected_size:
            raise RuntimeError("Backup database exceeds its declared size")
        target.write(block)
    if copied != expected_size:
        raise RuntimeError("Backup database size does not match its manifest")


def _read_json_file(path: Path) -> dict:
    if path.stat().st_size > _MANIFEST_MAX_BYTES:
        raise RuntimeError("Backup manifest exceeds the size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("Backup manifest is invalid") from error
    if not isinstance(value, dict):
        raise RuntimeError("Backup manifest is invalid")
    return value


def _validate_sqlite_database(path: Path) -> None:
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {path}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        required = {"alembic_version", "users", "library_sources", "library_models"}
        missing = required - tables
        if missing:
            raise RuntimeError(
                f"Backup is not a valid Meshive database; missing: {', '.join(sorted(missing))}"
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _remove_sqlite_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    _remove_sqlite_sidecars(path)


def _remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
