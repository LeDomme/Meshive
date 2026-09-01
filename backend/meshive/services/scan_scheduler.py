import logging
import threading
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from meshive.database import SessionLocal
from meshive.models.catalog import ScanRun
from meshive.models.library_source import LibrarySource
from meshive.services.scanner import (
    create_scan_run,
    dispatch_pending_scans,
    has_queued_or_running_scan,
)

_stop = threading.Event()
_thread: threading.Thread | None = None
_reported_invalid_timezones: set[tuple[int, str]] = set()
_last_check_at: datetime | None = None
_last_success_at: datetime | None = None
_last_error_at: datetime | None = None
_last_error: str | None = None

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _recover_interrupted_scans()
    dispatch_pending_scans()
    _stop.clear()
    _thread = threading.Thread(
        target=_loop,
        name="meshive-source-scans",
        daemon=True,
    )
    _thread.start()


def _recover_interrupted_scans() -> None:
    with SessionLocal() as session:
        if not inspect(session.get_bind()).has_table(ScanRun.__tablename__):
            return
        session.execute(
            update(ScanRun)
            .where(ScanRun.status == "running")
            .values(
                status="failed",
                finished_at=datetime.now(UTC),
                error_message="Scan interrupted by an application restart",
            )
        )
        session.commit()


def stop_scheduler() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=5)


def _loop() -> None:
    global _last_check_at, _last_success_at, _last_error_at, _last_error
    while not _stop.wait(5):
        _last_check_at = datetime.now(UTC)
        try:
            _start_due_scans()
            _last_success_at = datetime.now(UTC)
            _last_error = None
        except Exception:
            # A single malformed source schedule must not stop the web process.
            logger.exception("Scheduled scan evaluation failed")
            _last_error_at = datetime.now(UTC)
            _last_error = "Scheduled scan evaluation failed"
            continue


def diagnostics_status() -> dict[str, object]:
    return {
        "thread_alive": bool(_thread and _thread.is_alive()),
        "last_check_at": _last_check_at,
        "last_success_at": _last_success_at,
        "last_error_at": _last_error_at,
        "last_error": _last_error,
    }


def _start_due_scans() -> None:
    with SessionLocal() as session:
        sources = list(
            session.scalars(
                select(LibrarySource).where(
                    LibrarySource.is_active.is_(True),
                    LibrarySource.scan_enabled.is_(True),
                    LibrarySource.auto_scan_enabled.is_(True),
                )
            )
        )
        for source in sources:
            if not _is_due(session, source):
                continue
            if has_queued_or_running_scan(session, source.id):
                continue
            create_scan_run(session, source.id, trigger="scheduled")
    dispatch_pending_scans()


def _is_due(
    session: Session,
    source: LibrarySource,
    now: datetime | None = None,
) -> bool:
    try:
        timezone = ZoneInfo(source.auto_scan_timezone)
    except ZoneInfoNotFoundError:
        key = (source.id, source.auto_scan_timezone)
        if key not in _reported_invalid_timezones:
            _reported_invalid_timezones.add(key)
            logger.warning(
                "Skipping scheduled scan for source %s (%s): unknown timezone %r",
                source.id,
                source.name,
                source.auto_scan_timezone,
            )
        return False
    local_now = now.astimezone(timezone) if now else datetime.now(timezone)
    scheduled = _latest_occurrence(source, local_now)
    latest = session.scalar(
        select(ScanRun)
        .where(ScanRun.library_source_id == source.id)
        .order_by(ScanRun.created_at.desc())
        .limit(1)
    )
    previous = latest.created_at if latest else source.updated_at
    if previous is None:
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=UTC)
    return previous.astimezone(timezone) < scheduled


def _latest_occurrence(source: LibrarySource, now: datetime) -> datetime:
    hour, minute = (int(part) for part in source.auto_scan_time.split(":", 1))
    if source.auto_scan_frequency == "hourly":
        candidate = now.replace(minute=minute, second=0, microsecond=0)
        return candidate if candidate <= now else candidate - timedelta(hours=1)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if source.auto_scan_frequency == "weekly":
        candidate -= timedelta(
            days=(candidate.weekday() - source.auto_scan_weekday) % 7
        )
        return candidate if candidate <= now else candidate - timedelta(days=7)
    return candidate if candidate <= now else candidate - timedelta(days=1)
