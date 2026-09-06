import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import AUDIT_VIEW
from meshive.database import get_session
from meshive.models.audit import AuditEvent
from meshive.models.user import User
from meshive.services.audit import AuditAction, log_event

router = APIRouter(
    prefix="/admin/audit-events",
    tags=["audit"],
    dependencies=[Depends(require_global_permission(AUDIT_VIEW))],
)
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _filters(
    action: str | None,
    actor: str | None,
    from_at: datetime | None,
    to_at: datetime | None,
    source_id: int | None,
) -> list:
    filters = []
    if action: filters.append(AuditEvent.action == action)
    if actor: filters.append(AuditEvent.actor_username.ilike(f"%{actor}%"))
    if from_at: filters.append(AuditEvent.created_at >= from_at)
    if to_at: filters.append(AuditEvent.created_at <= to_at)
    if source_id: filters.append(AuditEvent.library_source_id == source_id)
    return filters


@router.get("")
def list_events(
    session: SessionDependency,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    action: str | None = None,
    actor: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    source_id: int | None = None,
) -> dict[str, object]:
    filters = _filters(action, actor, from_at, to_at, source_id)
    total = (
        session.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    )
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(*filters)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": event.id,
                "created_at": event.created_at,
                "actor_username": event.actor_username,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "target_label": event.target_label,
                "details": event.details,
                "library_source_id": event.library_source_id,
            }
            for event in events
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }

@router.get("/export")
def export_events(
    current_user: CurrentUser,
    session: SessionDependency,
    action: str | None = None,
    actor: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> StreamingResponse:
    limit = 10_000
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(*_filters(action, actor, from_at, to_at, None))
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit + 1)
        )
    )
    truncated = len(events) > limit
    events = events[:limit]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Actor", "Event", "Target"])
    for event in events:
        writer.writerow(
            [
                event.created_at.isoformat(),
                event.actor_username,
                event.action.replace(".", " "),
                f"{event.target_type} · {event.target_label}",
            ]
        )
    if truncated:
        writer.writerow(["", "", "Export truncated", f"Maximum {limit} events"])
    log_event(
        session,
        current_user,
        AuditAction.AUDIT_EXPORTED,
        "audit_export",
        "Audit log CSV",
        details={"row_count": len(events), "truncated": truncated},
    )
    session.commit()
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit-events.csv"},
    )
