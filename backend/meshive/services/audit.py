from sqlalchemy.orm import Session

from meshive.models.audit import AuditEvent
from meshive.models.user import User


class AuditAction:
    ROLE_CREATED = "role.created"; ROLE_UPDATED = "role.updated"; ROLE_DELETED = "role.deleted"
    USER_CREATED = "user.created"; USER_UPDATED = "user.updated"; USER_DELETED = "user.deleted"
    USER_ROLE_CHANGED = "user.role_changed"; USER_SOURCE_ACCESS_CHANGED = "user.source_access_changed"
    USER_STATUS_CHANGED = "user.status_changed"; USER_PASSWORD_CHANGED = "user.password_changed"
    USER_REQUIRE_PASSWORD_CHANGE_CHANGED = "user.require_password_change_changed"
    SOURCE_CREATED = "source.created"
    SOURCE_UPDATED = "source.updated"
    SOURCE_DELETED = "source.deleted"
    SCAN_STARTED = "scan.started"
    SCAN_PAUSE_REQUESTED = "scan.pause_requested"
    SCAN_RESUME_REQUESTED = "scan.resume_requested"
    SCAN_CANCEL_REQUESTED = "scan.cancel_requested"


def log_event(
    session: Session,
    actor: User,
    action: str,
    target_type: str,
    target_label: str,
    *,
    target_id: int | None = None,
    library_source_id: int | None = None,
    details: dict[str, object] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=getattr(actor, "id", None),
        actor_username=getattr(actor, "username", "Unknown"),
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        library_source_id=library_source_id,
        details=details,
    )
    session.add(event)
    return event
