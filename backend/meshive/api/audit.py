from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.permissions import AUDIT_VIEW
from meshive.database import get_session
from meshive.models.audit import AuditEvent

router = APIRouter(prefix="/admin/audit-events", tags=["audit"], dependencies=[Depends(require_global_permission(AUDIT_VIEW))])
SessionDependency = Annotated[Session, Depends(get_session)]

@router.get("")
def list_events(session: SessionDependency, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), action: str | None = None, actor: str | None = None, from_at: datetime | None = None, to_at: datetime | None = None, source_id: int | None = None) -> dict[str, object]:
    filters = []
    if action: filters.append(AuditEvent.action == action)
    if actor: filters.append(AuditEvent.actor_username.ilike(f"%{actor}%"))
    if from_at: filters.append(AuditEvent.created_at >= from_at)
    if to_at: filters.append(AuditEvent.created_at <= to_at)
    if source_id: filters.append(AuditEvent.library_source_id == source_id)
    total = session.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    events = list(session.scalars(select(AuditEvent).where(*filters).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [{"id": e.id, "created_at": e.created_at, "actor_username": e.actor_username, "action": e.action, "target_type": e.target_type, "target_id": e.target_id, "target_label": e.target_label, "details": e.details, "library_source_id": e.library_source_id} for e in events], "page": page, "page_size": page_size, "total": total}
