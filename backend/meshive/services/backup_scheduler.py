import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.backup import (
    cleanup_orphaned_backup_sidecars,
    create_backup,
    delete_backup_files,
)
from meshive.config import get_settings
from meshive.database import SessionLocal
from meshive.models.backup import BackupRun, BackupSchedule
from meshive.models.user import User
from meshive.services.audit import AuditAction, log_event

_stop = threading.Event()
_thread: threading.Thread | None = None
logger = logging.getLogger(__name__)
_history_lock = threading.Lock()


def safe_destination(value: str) -> Path:
    relative = PurePosixPath(value.strip().replace("\\", "/"))
    if (
        not value.strip()
        or relative.is_absolute()
        or any(part in {".", ".."} for part in relative.parts)
    ):
        raise ValueError("Destination must be a safe path relative to the backup root")
    root = get_settings().backup_dir.resolve()
    destination = root.joinpath(*relative.parts).resolve()
    if root not in destination.parents:
        raise ValueError("Destination must be inside the backup root")
    return destination


def run_backup(trigger: str = "manual", *, actor: User | None = None) -> BackupRun:
    with SessionLocal() as session:
        schedule = session.get(BackupSchedule, 1)
        destination = get_settings().backup_dir.resolve() / (
            "scheduled" if trigger == "scheduled" else "manual"
        )
        run = BackupRun(
            status="running",
            trigger=trigger,
            started_at=datetime.now(UTC),
        )
        session.add(run)
        if trigger == "manual" and actor is not None:
            session.flush()
            log_event(
                session,
                actor,
                AuditAction.BACKUP_STARTED,
                "backup",
                "Manual backup",
                target_id=run.id,
            )
            session.commit()
        try:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            prefix = "meshive-auto" if trigger == "scheduled" else "meshive-manual"
            path = create_backup(destination / f"{prefix}-{stamp}.zip")
            run.status = "completed"
            run.path = str(path)
            run.size_bytes = path.stat().st_size
            run.finished_at = datetime.now(UTC)
            if schedule:
                apply_retention(schedule, session)
            if trigger == "manual" and actor is not None:
                log_event(
                    session,
                    actor,
                    AuditAction.BACKUP_COMPLETED,
                    "backup",
                    "Manual backup",
                    target_id=run.id,
                )
            session.commit()
        except (OSError, RuntimeError, sqlite3.Error) as error:
            run.status = "failed"
            run.error_message = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
            if trigger == "manual" and actor is not None:
                log_event(
                    session,
                    actor,
                    AuditAction.BACKUP_FAILED,
                    "backup",
                    "Manual backup",
                    target_id=run.id,
                )
            session.commit()
        session.refresh(run)
        return run


def apply_retention(schedule: BackupSchedule, session: Session) -> None:
    destination = get_settings().backup_dir.resolve() / "scheduled"
    files = sorted(
        [
            *destination.glob("meshive-auto-*.zip"),
            *destination.glob("meshive-auto-*.sqlite3"),
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    cutoff = datetime.now(UTC).timestamp() - schedule.retention_days * 86400
    for index, path in enumerate(files):
        if index >= schedule.retention_count or path.stat().st_mtime < cutoff:
            resolved = str(path.resolve())
            delete_backup_files(path)
            for run in session.scalars(select(BackupRun).where(BackupRun.path == resolved)):
                run.status = "deleted"
                run.path = None
                run.size_bytes = None
    session.commit()


def sync_backup_history(session: Session) -> int:
    """Import backup files which survived a database restore into its history."""
    root = get_settings().backup_dir.resolve()

    with _history_lock:
        cleanup_orphaned_backup_sidecars(root)
        changed = False
        interrupted = list(
            session.scalars(
                select(BackupRun).where(
                    BackupRun.status == "running",
                    BackupRun.path.is_(None),
                )
            )
        )
        for run in interrupted:
            session.delete(run)
            changed = True

        if not root.is_dir():
            if changed:
                session.commit()
            return 0

        known_paths = {
            str(Path(path).resolve())
            for path in session.scalars(
                select(BackupRun.path).where(BackupRun.path.is_not(None))
            )
            if path
        }
        imported = 0
        candidates = [*root.rglob("*.zip"), *root.rglob("*.sqlite3")]
        for candidate in candidates:
            path = candidate.resolve()
            if root != path.parent and root not in path.parents:
                continue
            trigger = _backup_trigger(path.name)
            if trigger is None or str(path) in known_paths:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            session.add(
                BackupRun(
                    status="completed",
                    trigger=trigger,
                    path=str(path),
                    size_bytes=path.stat().st_size,
                    started_at=modified,
                    finished_at=modified,
                )
            )
            known_paths.add(str(path))
            imported += 1
        if imported or changed:
            session.commit()
        return imported


def _backup_trigger(filename: str) -> str | None:
    if filename.startswith("meshive-auto-"):
        return "scheduled"
    if filename.startswith(("meshive-manual-", "meshive-")):
        return "manual"
    if filename.startswith("pre-restore-"):
        return "pre_restore"
    return None


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="meshive-backups", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=5)


def _loop() -> None:
    while not _stop.is_set():
        try:
            if _is_due():
                run = run_backup("scheduled")
                if run.status == "failed":
                    logger.error("Scheduled backup failed: %s", run.error_message)
        except Exception:
            # A malformed schedule must not terminate the web process.
            logger.exception("Automatic backup scheduler check failed")
        if _stop.wait(30):
            break


def _is_due() -> bool:
    with SessionLocal() as session:
        sync_backup_history(session)
        schedule = session.get(BackupSchedule, 1)
        if not schedule or not schedule.enabled:
            return False
        try:
            timezone = ZoneInfo(schedule.timezone)
        except ZoneInfoNotFoundError:
            return False
        local_now = datetime.now(timezone)
        occurrence = _latest_occurrence(schedule, local_now)
        latest = session.scalar(
            select(BackupRun)
            .where(
                BackupRun.trigger == "scheduled",
                BackupRun.status.in_(("completed", "deleted")),
            )
            .order_by(BackupRun.started_at.desc())
            .limit(1)
        )
        if latest and latest.started_at:
            started = latest.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            if started >= occurrence.astimezone(UTC):
                return False
        elif occurrence.date() < local_now.date():
            # A newly configured schedule starts at its next regular occurrence.
            return False
        return True


def _latest_occurrence(schedule: BackupSchedule, local_now: datetime) -> datetime:
    hour, minute = (int(part) for part in schedule.time_of_day.split(":", 1))
    occurrence = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if schedule.frequency == "weekly":
        occurrence -= timedelta(days=(occurrence.weekday() - schedule.weekday) % 7)
    if occurrence > local_now:
        occurrence -= timedelta(days=7 if schedule.frequency == "weekly" else 1)
    return occurrence
