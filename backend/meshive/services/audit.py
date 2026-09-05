from datetime import datetime

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
    BACKUP_STARTED = "backup.started"
    BACKUP_COMPLETED = "backup.completed"
    BACKUP_FAILED = "backup.failed"
    BACKUP_RESTORE_STARTED = "backup.restore_started"
    BACKUP_RESTORE_COMPLETED = "backup.restore_completed"
    BACKUP_RESTORE_FAILED = "backup.restore_failed"
    METADATA_CREATED = "metadata.created"
    METADATA_UPDATED = "metadata.updated"
    METADATA_DELETED = "metadata.deleted"
    TAG_CREATED = "tag.created"
    TAG_UPDATED = "tag.updated"
    TAG_DELETED = "tag.deleted"
    FOLDER_TAG_RULE_CREATED = "folder_tag_rule.created"
    FOLDER_TAG_RULE_UPDATED = "folder_tag_rule.updated"
    FOLDER_TAG_RULE_DELETED = "folder_tag_rule.deleted"
    AUTOMATIC_TAG_RULE_CREATED = "automatic_tag_rule.created"
    AUTOMATIC_TAG_RULE_UPDATED = "automatic_tag_rule.updated"
    AUTOMATIC_TAG_RULE_DELETED = "automatic_tag_rule.deleted"
    MODEL_TAG_ADDED = "model_tag.added"
    MODEL_TAG_REMOVED = "model_tag.removed"
    FOLDER_NAME_REGEX_TAG_RULE_CREATED = "folder_name_regex_tag_rule.created"
    FOLDER_NAME_REGEX_TAG_RULE_UPDATED = "folder_name_regex_tag_rule.updated"
    FOLDER_NAME_REGEX_TAG_RULE_DELETED = "folder_name_regex_tag_rule.deleted"


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
    created_at: datetime | None = None,
) -> AuditEvent:
    return log_event_snapshot(
        session,
        actor_user_id=getattr(actor, "id", None),
        actor_username=getattr(actor, "username", "Unknown"),
        action=action,
        target_type=target_type,
        target_label=target_label,
        target_id=target_id,
        library_source_id=library_source_id,
        details=details,
        created_at=created_at,
    )


def log_event_snapshot(
    session: Session,
    *,
    actor_user_id: int | None,
    actor_username: str,
    action: str,
    target_type: str,
    target_label: str,
    target_id: int | None = None,
    library_source_id: int | None = None,
    details: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        library_source_id=library_source_id,
        details=details,
    )
    if created_at is not None:
        event.created_at = created_at
    session.add(event)
    return event
