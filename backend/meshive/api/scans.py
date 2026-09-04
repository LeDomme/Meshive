from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.access import (
    AccessContext,
    get_access_context,
    get_operable_source_or_404,
    get_visible_scan_or_404,
    get_visible_source_ids,
    require_access_permission,
    require_any_permission,
    require_permission,
    scope_scan_runs,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import SCANS_CONTROL, SCANS_START, SCANS_VIEW
from meshive.auth.sessions import utc_now
from meshive.database import get_session
from meshive.models.catalog import ScanIssue, ScanRun
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.schemas.scan import (
    ScanDetail,
    ScanIssueRead,
    ScanQueueItem,
    ScanRunRead,
    ScanSourcePickerRead,
    ScanStartRequest,
)
from meshive.services.scanner import (
    create_scan_run,
    dispatch_pending_scans,
    has_queued_or_running_scan,
)

router = APIRouter(
    prefix="/admin",
    tags=["scans"],
)
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]
ScansViewAccess = Annotated[AccessContext, Depends(require_permission(SCANS_VIEW))]
ScansAccess = Annotated[
    AccessContext,
    Depends(require_any_permission({SCANS_VIEW, SCANS_START, SCANS_CONTROL})),
]


@router.get("/scans/library-sources", response_model=list[ScanSourcePickerRead])
def list_scan_sources(
    access: ScansAccess,
    session: SessionDependency,
) -> list[ScanSourcePickerRead]:
    statement = select(LibrarySource.id, LibrarySource.name).order_by(LibrarySource.name)
    source_ids = get_visible_source_ids(access)
    if source_ids is not None:
        statement = statement.where(LibrarySource.id.in_(source_ids))
    return [ScanSourcePickerRead(id=source_id, name=name) for source_id, name in session.execute(statement)]


@router.post(
    "/library-sources/{source_id}/scan",
    response_model=ScanRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_scan(
    source_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: ScanStartRequest | None = None,
) -> ScanRun:
    access = get_access_context(session, current_user)
    source = get_operable_source_or_404(session, access, source_id)
    require_access_permission(access, SCANS_START)
    if not source.is_active or not source.scan_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scanning is disabled for this source",
        )
    if has_queued_or_running_scan(session, source_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scan is already queued or running for this source",
        )
    scan = create_scan_run(
        session,
        source_id,
        trigger="manual",
        mode=payload.mode if payload is not None else "smart",
    )
    dispatch_pending_scans()
    return scan


@router.get(
    "/library-sources/{source_id}/scans",
    response_model=list[ScanRunRead],
)
def list_source_scans(
    source_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> list[ScanRun]:
    access = get_access_context(session, current_user)
    get_operable_source_or_404(session, access, source_id)
    require_access_permission(access, SCANS_VIEW)
    statement = (
        select(ScanRun)
        .where(ScanRun.library_source_id == source_id)
        .order_by(ScanRun.id.desc())
        .limit(20)
    )
    return list(session.scalars(statement))


@router.get("/scans/queue", response_model=list[ScanQueueItem])
def scan_queue(
    access: ScansViewAccess,
    session: SessionDependency,
) -> list[ScanQueueItem]:
    statement = (
        select(ScanRun, LibrarySource.name)
        .join(LibrarySource, LibrarySource.id == ScanRun.library_source_id)
        .where(ScanRun.status.in_(("pending", "running")))
        .order_by(
            ScanRun.started_at.is_(None),
            ScanRun.started_at,
            ScanRun.created_at,
            ScanRun.id,
        )
    )
    rows = session.execute(scope_scan_runs(statement, access)).all()
    queued_position = 0
    result = []
    for scan, source_name in rows:
        position = None
        if scan.status == "pending":
            queued_position += 1
            position = queued_position
        result.append(
            ScanQueueItem(
                id=scan.id,
                library_source_id=scan.library_source_id,
                source_name=source_name,
                status=scan.status,
                cancel_requested=scan.cancel_requested,
                pause_requested=scan.pause_requested,
                mode=scan.mode,
                trigger=scan.trigger,
                target_model_id=scan.target_model_id,
                target_model_name=scan.target_model_name,
                current_model_name=scan.current_model_name,
                current_phase=scan.current_phase,
                models_total=scan.models_total,
                models_found=scan.models_found,
                models_skipped=scan.models_skipped,
                position=position,
                created_at=scan.created_at,
                started_at=scan.started_at,
            )
        )
    return result


@router.post("/scans/{scan_id}/cancel", response_model=ScanRunRead)
def cancel_scan(
    scan_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanRun:
    access = get_access_context(session, current_user)
    scan = get_visible_scan_or_404(session, access, scan_id)
    require_access_permission(access, SCANS_CONTROL)
    if scan.status not in ("pending", "running"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan is not active")
    scan.cancel_requested = True
    scan.pause_requested = False
    if scan.status == "pending":
        scan.status = "cancelled"
        scan.finished_at = utc_now()
    session.commit()
    return scan

@router.post("/scans/{scan_id}/pause", response_model=ScanRunRead)
def pause_scan(
    scan_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanRun:
    access = get_access_context(session, current_user)
    scan = get_visible_scan_or_404(session, access, scan_id)
    require_access_permission(access, SCANS_CONTROL)
    if scan.status not in ("pending", "running"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan is not active")
    scan.pause_requested = True
    session.commit()
    return scan


@router.post("/scans/{scan_id}/resume", response_model=ScanRunRead)
def resume_scan(
    scan_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanRun:
    access = get_access_context(session, current_user)
    scan = get_visible_scan_or_404(session, access, scan_id)
    require_access_permission(access, SCANS_CONTROL)
    if scan.status not in ("pending", "running"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan is not active")
    scan.pause_requested = False
    session.commit()
    return scan

@router.get("/scans/{scan_id}", response_model=ScanDetail)
def get_scan(
    scan_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanDetail:
    access = get_access_context(session, current_user)
    scan = get_visible_scan_or_404(session, access, scan_id)
    require_access_permission(access, SCANS_VIEW)
    issues = list(
        session.scalars(
            select(ScanIssue)
            .where(ScanIssue.scan_run_id == scan_id)
            .order_by(ScanIssue.id)
        )
    )
    return ScanDetail(
        **ScanRunRead.model_validate(scan).model_dump(),
        issues=[ScanIssueRead.model_validate(issue) for issue in issues],
    )
