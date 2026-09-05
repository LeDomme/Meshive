from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.permissions import AUDIT_VIEW
from meshive.database import get_session
from meshive.models.audit import AuditEvent

router = APIRouter(prefix="/admin/audit-events", tags=["audit"], dependencies=[Depends(require_global_permission(AUDIT_VIEW))])
SessionDependency = Annotated[Session, Depends(get_session)]

@router.get("")
def list_events(session: SessionDependency, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), action: str | None = None, actor: str | None = None, from_at: datetime | None = None, to_at: datetime | None = None, source_id: int | None = None) -> dict[str, object]:
    statement = select(AuditEvent)
    if action: statement = statement.where(AuditEvent.action == action)
    if actor: statement = statement.where(AuditEvent.actor_username.ilike(f"%{actor}%"))
    if from_at: statement = statement.where(AuditEvent.created_at >= from_at)
    if to_at: statement = statement.where(AuditEvent.created_at <= to_at)
    if source_id: statement = statement.where(AuditEvent.library_source_id == source_id)
    total = len(list(session.scalars(statement)))
    events = list(session.scalars(statement.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [{"id": e.id, "created_at": e.created_at, "actor_username": e.actor_username, "action": e.action, "target_type": e.target_type, "target_id": e.target_id, "target_label": e.target_label, "details": e.details, "library_source_id": e.library_source_id} for e in events], "page": page, "page_size": page_size, "total": total}
