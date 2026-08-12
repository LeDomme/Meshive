from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.dependencies import require_admin
from meshive.database import get_session
from meshive.models.catalog import ScanIssue, ScanRun
from meshive.models.library_source import LibrarySource
from meshive.schemas.scan import (
    ScanDetail,
    ScanIssueRead,
    ScanQueueItem,
    ScanRunRead,
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
    dependencies=[Depends(require_admin)],
)


@router.post(
    "/library-sources/{source_id}/scan",
    response_model=ScanRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_source_scan(
    source_id: int,
    session: Session = Depends(get_session),
    payload: ScanStartRequest | None = None,
) -> ScanRun:
    source = session.get(LibrarySource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
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
        mode=payload.mode if payload is not None else "full",
    )
    dispatch_pending_scans()
    return scan


@router.get(
    "/library-sources/{source_id}/scans",
    response_model=list[ScanRunRead],
)
def list_source_scans(
    source_id: int, session: Session = Depends(get_session)
) -> list[ScanRun]:
    if session.get(LibrarySource, source_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    statement = (
        select(ScanRun)
        .where(ScanRun.library_source_id == source_id)
        .order_by(ScanRun.id.desc())
        .limit(20)
    )
    return list(session.scalars(statement))


@router.get("/scans/queue", response_model=list[ScanQueueItem])
def scan_queue(session: Session = Depends(get_session)) -> list[ScanQueueItem]:
    rows = session.execute(
        select(ScanRun, LibrarySource.name)
        .join(LibrarySource, LibrarySource.id == ScanRun.library_source_id)
        .where(ScanRun.status.in_(("pending", "running")))
        .order_by(
            ScanRun.started_at.is_(None),
            ScanRun.started_at,
            ScanRun.created_at,
            ScanRun.id,
        )
    ).all()
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
                trigger=scan.trigger,
                position=position,
                created_at=scan.created_at,
                started_at=scan.started_at,
            )
        )
    return result


@router.get("/scans/{scan_id}", response_model=ScanDetail)
def get_scan(scan_id: int, session: Session = Depends(get_session)) -> ScanDetail:
    scan = session.get(ScanRun, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
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
