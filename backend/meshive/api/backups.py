import json
import os
import signal
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import BACKUPS_MANAGE
from meshive.backup import delete_backup_files, validate_backup
from meshive.config import get_settings
from meshive.database import get_session
from meshive.models.backup import BackupRun, BackupSchedule
from meshive.models.user import User
from meshive.schemas.backup import (
    BackupRestoreRequest,
    BackupRunRead,
    BackupScheduleData,
    BackupScheduleRead,
)
from meshive.services.audit import AuditAction, log_event
from meshive.services.backup_scheduler import (
    run_backup,
    sync_backup_history,
)

router = APIRouter(
    prefix="/admin/backups",
    tags=["backup administration"],
    dependencies=[Depends(require_global_permission(BACKUPS_MANAGE))],
)
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/schedule", response_model=BackupScheduleRead)
def get_schedule(session: SessionDependency) -> BackupSchedule:
    return _schedule(session)


@router.put("/schedule", response_model=BackupScheduleRead)
def update_schedule(
    payload: BackupScheduleData, session: SessionDependency
) -> BackupSchedule:
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    schedule = _schedule(session)
    for key, value in payload.model_dump().items():
        setattr(schedule, key, value)
    session.commit()
    session.refresh(schedule)
    return schedule


@router.post("/run", response_model=BackupRunRead)
def backup_now(current_user: CurrentUser) -> BackupRun:
    run = run_backup("manual", actor=current_user)
    if run.status == "failed":
        raise HTTPException(status_code=500, detail=run.error_message or "Backup failed")
    return run


@router.get("", response_model=list[BackupRunRead])
def backup_history(session: SessionDependency) -> list[BackupRun]:
    sync_backup_history(session)
    return list(
        session.scalars(
            select(BackupRun)
            .where(BackupRun.status != "deleted")
            .order_by(BackupRun.started_at.desc())
        )
    )


@router.get("/restore-result")
def restore_result() -> dict[str, str | None]:
    path = get_settings().data_dir / "restore-result.json"
    if not path.is_file():
        return {"status": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status": "failed", "error": "The restore result could not be read"}


@router.delete("/restore-result", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_restore_result() -> Response:
    (get_settings().data_dir / "restore-result.json").unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/restore/{run_id}", status_code=status.HTTP_202_ACCEPTED)
def request_restore(
    run_id: int,
    payload: BackupRestoreRequest,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict[str, str]:
    if payload.confirmation != "RESTORE":
        raise HTTPException(status_code=422, detail='Enter "RESTORE" to confirm')
    run = session.get(BackupRun, run_id)
    if run is None or run.status != "completed" or not run.path:
        raise HTTPException(status_code=404, detail="Completed backup not found")
    root = get_settings().backup_dir.resolve()
    path = Path(run.path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=422, detail="Backup file is unavailable")
    try:
        validate_backup(path)
    except (OSError, RuntimeError, sqlite3.DatabaseError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    marker = get_settings().data_dir / "restore-request.json"
    temporary = marker.with_suffix(".tmp")
    started_at = datetime.now(UTC)
    event = log_event(
        session,
        current_user,
        AuditAction.BACKUP_RESTORE_STARTED,
        "backup",
        "Database restore",
        target_id=run.id,
        created_at=started_at,
    )
    session.flush()
    temporary.write_text(
        json.dumps(
            {
                "path": str(path),
                "actor_user_id": current_user.id,
                "actor_username": current_user.username,
                "audit_started_at": started_at.isoformat(),
                "audit_event_id": event.id,
                "run_id": run.id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    session.commit()
    os.replace(temporary, marker)
    (get_settings().data_dir / "restore-result.json").unlink(missing_ok=True)
    threading.Thread(target=_restart_process, daemon=True).start()
    return {"status": "restart_pending"}


@router.delete("/{run_id}", status_code=204)
def delete_backup(run_id: int, current_user: CurrentUser, session: SessionDependency) -> Response:
    run = session.get(BackupRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backup record not found")
    if run.path:
        root = get_settings().backup_dir.resolve()
        path = Path(run.path).resolve()
        if root == path or root in path.parents:
            delete_backup_files(path)
    if run.trigger == "scheduled":
        # Preserve an invisible marker so deleting a file does not cause the
        # scheduler to repeat an occurrence which has already completed.
        run.status = "deleted"
        run.path = None
        run.size_bytes = None
        run.error_message = None
    else:
        session.delete(run)
    log_event(
        session,
        current_user,
        AuditAction.BACKUP_DELETED,
        "backup",
        "Manual backup" if run.trigger == "manual" else "Scheduled backup",
        target_id=run.id,
    )
    session.commit()
    return Response(status_code=204)


def _restart_process() -> None:
    time.sleep(2)
    os.kill(os.getpid(), signal.SIGTERM)


def _schedule(session: Session) -> BackupSchedule:
    schedule = session.get(BackupSchedule, 1)
    if schedule is None:
        schedule = BackupSchedule(id=1)
        session.add(schedule)
        session.commit()
        session.refresh(schedule)
    return schedule
