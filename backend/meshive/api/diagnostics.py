import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from meshive import __version__
from meshive.auth.dependencies import require_admin
from meshive.config import get_settings
from meshive.database import get_session
from meshive.models.catalog import Archive, LibraryModel, ScanRun
from meshive.services import scan_scheduler

router = APIRouter(
    prefix="/admin/diagnostics",
    tags=["diagnostics"],
    dependencies=[Depends(require_admin)],
)


def _storage_status(path: Path) -> dict[str, object]:
    """Return bounded root-level storage information without traversal."""
    result: dict[str, object] = {"configured": True, "path": path.as_posix()}
    try:
        if not path.is_dir():
            raise OSError()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.close(descriptor)
        result["readable"] = True
    except OSError:
        result.update(readable=False, writable=False, error="Storage is unavailable")
        return result

    probe_path: str | None = None
    try:
        descriptor, probe_path = tempfile.mkstemp(prefix=".meshive-diagnostics-", dir=path)
        os.close(descriptor)
        result["writable"] = True
    except OSError:
        result["writable"] = False
    finally:
        if probe_path is not None:
            try:
                os.unlink(probe_path)
            except OSError:
                result["writable"] = False

    try:
        usage = shutil.disk_usage(path)
        result.update(total_bytes=usage.total, free_bytes=usage.free)
    except OSError:
        result["error"] = "Storage capacity is unavailable"
    return result


@router.get("")
def diagnostics(session: Session = Depends(get_session)) -> dict[str, object]:  # noqa: B008
    settings = get_settings()
    database: dict[str, object] = {"backend": "sqlite", "reachable": True}
    try:
        session.execute(select(1))
        database_path = settings.data_dir / "meshive.db"
        database["size_bytes"] = database_path.stat().st_size if database_path.is_file() else 0
    except (OSError, SQLAlchemyError):
        database.update(reachable=False, error="Database is unavailable")

    def count(statement) -> int | None:
        try:
            return session.scalar(statement) or 0
        except SQLAlchemyError:
            return None

    return {
        "application": {"version": __version__, "environment": settings.environment},
        "database": database,
        "storage": {
            "data": _storage_status(settings.data_dir),
            "cache": _storage_status(settings.cache_dir),
            "backup": _storage_status(settings.backup_dir),
        },
        "archive_backend": {
            "command": settings.archive_command,
            "available": shutil.which(settings.archive_command) is not None,
        },
        "scanner": {
            "max_concurrent_scans": settings.max_concurrent_scans,
            "running": count(select(func.count()).select_from(ScanRun).where(ScanRun.status == "running")),
            "pending": count(select(func.count()).select_from(ScanRun).where(ScanRun.status == "pending")),
        },
        "scheduler": scan_scheduler.diagnostics_status(),
        "catalogue": {
            "models_total": count(select(func.count()).select_from(LibraryModel)),
            "models_available": count(select(func.count()).select_from(LibraryModel).where(LibraryModel.status == "available")),
            "models_incomplete": count(select(func.count()).select_from(LibraryModel).where(LibraryModel.status == "incomplete")),
            "models_error": count(select(func.count()).select_from(LibraryModel).where(LibraryModel.status == "error")),
            "models_missing": count(select(func.count()).select_from(LibraryModel).where(LibraryModel.status == "missing")),
            "archives_total": count(select(func.count()).select_from(Archive)),
            "archives_error": count(select(func.count()).select_from(Archive).where(Archive.status == "error")),
        },
    }
