import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from meshive import backup
from meshive.config import Settings
from meshive.models.backup import BackupRun, BackupSchedule
from meshive.services import backup_scheduler


def create_meshive_database(path, marker: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num TEXT);
            CREATE TABLE users (id INTEGER, username TEXT);
            CREATE TABLE library_sources (id INTEGER);
            CREATE TABLE library_models (id INTEGER);
            """
        )
        connection.execute(
            "INSERT INTO users(id, username) VALUES (1, ?)", (marker,)
        )


def test_backup_and_restore_with_safety_copy(tmp_path, monkeypatch) -> None:
    live = tmp_path / "meshive.db"
    create_meshive_database(live, "before")
    settings = Settings(
        database_url=f"sqlite:///{live.as_posix()}",
        data_dir=tmp_path / "data",
        backup_dir=tmp_path / "external-backups",
    )
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    saved = backup.create_backup(tmp_path / "saved.sqlite3")
    assert saved.is_file()
    assert saved.with_suffix(".sqlite3.json").is_file()

    with sqlite3.connect(live) as connection:
        connection.execute("UPDATE users SET username = 'after'")
        connection.commit()

    safety = backup.restore_backup(saved, confirmed_stopped=True)
    assert safety.name.startswith("pre-restore-")
    assert safety.parent == settings.backup_dir / "pre-restore"
    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT username FROM users").fetchone()[0] == "before"


def test_restore_invalidates_sessions_and_action_tokens(tmp_path, monkeypatch) -> None:
    live = tmp_path / "meshive.db"
    saved = tmp_path / "saved.sqlite3"
    for path in (live, saved):
        create_meshive_database(path, path.stem)
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE user_sessions (token_hash TEXT);
                CREATE TABLE user_action_tokens (token_hash TEXT);
                INSERT INTO user_sessions(token_hash) VALUES ('session-token');
                INSERT INTO user_action_tokens(token_hash) VALUES ('action-token');
                """
            )
    settings = Settings(
        database_url=f"sqlite:///{live.as_posix()}",
        data_dir=tmp_path / "data",
        backup_dir=tmp_path / "backups",
    )
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    backup.restore_backup(saved, confirmed_stopped=True)

    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM user_action_tokens"
        ).fetchone()[0] == 0


def test_zip_backup_is_single_file_and_cleans_data_tmp(tmp_path, monkeypatch) -> None:
    live = tmp_path / "meshive.db"
    create_meshive_database(live, "archive")
    data_dir = tmp_path / "data"
    settings = Settings(
        database_url=f"sqlite:///{live.as_posix()}",
        data_dir=data_dir,
        backup_dir=tmp_path / "backups",
    )
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    saved = backup.create_backup(settings.backup_dir / "meshive-manual-test.zip")

    assert saved.is_file()
    assert list(settings.backup_dir.iterdir()) == [saved]
    assert list((data_dir / "tmp").iterdir()) == []
    with zipfile.ZipFile(saved) as archive:
        assert set(archive.namelist()) == {"meshive.sqlite3", "manifest.json"}
    backup.validate_backup(saved)
    assert list((data_dir / "tmp").iterdir()) == []


def test_restore_rejects_declared_database_above_limit(tmp_path, monkeypatch) -> None:
    saved = tmp_path / "oversized.zip"
    maximum = 16 * 1024 * 1024
    manifest = {
        "format": "meshive-backup-v1",
        "database_file": "meshive.sqlite3",
        "size_bytes": maximum + 1,
        "sha256": "unused",
    }
    with zipfile.ZipFile(saved, "w") as archive:
        archive.writestr("meshive.sqlite3", b"x")
        archive.writestr("manifest.json", json.dumps(manifest))
    settings = Settings(
        data_dir=tmp_path / "data",
        backup_max_restore_bytes=maximum,
    )
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="exceeds the configured"):
        backup.validate_backup(saved)


def test_restore_rejects_zip_metadata_size_mismatch(tmp_path, monkeypatch) -> None:
    saved = tmp_path / "mismatch.zip"
    manifest = {
        "format": "meshive-backup-v1",
        "database_file": "meshive.sqlite3",
        "size_bytes": 2,
        "sha256": "unused",
    }
    with zipfile.ZipFile(saved, "w") as archive:
        archive.writestr("meshive.sqlite3", b"x")
        archive.writestr("manifest.json", json.dumps(manifest))
    settings = Settings(data_dir=tmp_path / "data")
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="ZIP metadata"):
        backup.validate_backup(saved)


def test_restore_copy_stops_at_declared_size() -> None:
    with pytest.raises(RuntimeError, match="exceeds its declared size"):
        backup._copy_backup_database(BytesIO(b"too large"), BytesIO(), 3)


def test_restore_checks_available_working_space(tmp_path, monkeypatch) -> None:
    settings = Settings(backup_restore_min_free_bytes=64 * 1024 * 1024)
    monkeypatch.setattr(backup, "get_settings", lambda: settings)
    monkeypatch.setattr(
        backup.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=10),
    )

    with pytest.raises(RuntimeError, match="Insufficient free space"):
        backup._validate_restore_space(tmp_path, 1024)


def test_deleting_backup_removes_manifest_and_sqlite_sidecars(tmp_path) -> None:
    saved = tmp_path / "meshive-auto.sqlite3"
    artifacts = [
        saved,
        saved.with_suffix(".sqlite3.json"),
        saved.with_name(saved.name + "-wal"),
        saved.with_name(saved.name + "-shm"),
        saved.with_name(f".{saved.name}.tmp-wal"),
        saved.with_name(f".{saved.name}.tmp-shm"),
    ]
    for artifact in artifacts:
        artifact.write_bytes(b"test")

    backup.delete_backup_files(saved)

    assert not any(artifact.exists() for artifact in artifacts)


def test_cleanup_removes_orphaned_temporary_sidecars(tmp_path) -> None:
    wal = tmp_path / ".meshive-auto.sqlite3.tmp-wal"
    shm = tmp_path / ".meshive-auto.sqlite3.tmp-shm"
    wal.write_bytes(b"stale")
    shm.write_bytes(b"stale")

    removed = backup.cleanup_orphaned_backup_sidecars(tmp_path, minimum_age=0)

    assert removed == 2
    assert not wal.exists()
    assert not shm.exists()


def test_restore_requires_explicit_stopped_confirmation(tmp_path, monkeypatch) -> None:
    live = tmp_path / "meshive.db"
    create_meshive_database(live, "live")
    settings = Settings(database_url=f"sqlite:///{live.as_posix()}")
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="confirm-stopped"):
        backup.restore_backup(live, confirmed_stopped=False)


def test_backup_destination_cannot_escape_configured_root(tmp_path, monkeypatch) -> None:
    settings = Settings(backup_dir=tmp_path / "backups")
    monkeypatch.setattr(backup_scheduler, "get_settings", lambda: settings)

    assert backup_scheduler.safe_destination("daily").parent == settings.backup_dir
    with pytest.raises(ValueError, match="relative"):
        backup_scheduler.safe_destination("../outside")


def test_existing_backup_files_are_imported_into_history(tmp_path, monkeypatch) -> None:
    backup_root = tmp_path / "backups"
    automatic = backup_root / "daily" / "meshive-auto-20260731T010000Z.sqlite3"
    safety = backup_root / "pre-restore-20260731T020000Z.sqlite3"
    automatic.parent.mkdir(parents=True)
    automatic.write_bytes(b"automatic")
    safety.write_bytes(b"safety")
    settings = Settings(backup_dir=backup_root)
    monkeypatch.setattr(backup_scheduler, "get_settings", lambda: settings)

    engine = create_engine("sqlite://")
    BackupRun.__table__.create(engine)
    with Session(engine) as session:
        assert backup_scheduler.sync_backup_history(session) == 2
        assert backup_scheduler.sync_backup_history(session) == 0
        triggers = list(session.scalars(select(BackupRun.trigger).order_by(BackupRun.trigger)))

    assert triggers == ["pre_restore", "scheduled"]


def test_history_sync_removes_interrupted_run_restored_from_backup(
    tmp_path, monkeypatch
) -> None:
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    settings = Settings(backup_dir=backup_root)
    monkeypatch.setattr(backup_scheduler, "get_settings", lambda: settings)

    engine = create_engine("sqlite://")
    BackupRun.__table__.create(engine)
    with Session(engine) as session:
        session.add(BackupRun(status="running", trigger="scheduled"))
        session.commit()

        backup_scheduler.sync_backup_history(session)

        assert session.scalar(select(BackupRun)) is None


def test_daily_schedule_uses_latest_due_occurrence() -> None:
    schedule = BackupSchedule(time_of_day="03:00", frequency="daily")

    occurrence = backup_scheduler._latest_occurrence(
        schedule, datetime(2026, 7, 31, 2, 0, tzinfo=UTC)
    )

    assert occurrence == datetime(2026, 7, 30, 3, 0, tzinfo=UTC)
