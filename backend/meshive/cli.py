import argparse
import getpass
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from meshive.auth.action_tokens import delete_user_action_tokens
from meshive.auth.passwords import hash_password
from meshive.backup import create_backup, restore_backup
from meshive.database import SessionLocal
from meshive.models.audit import AuditEvent
from meshive.models.session import UserSession
from meshive.models.user import User
from meshive.repositories.roles import get_system_role_for_legacy_role
from meshive.repositories.users import get_user_by_username, normalize_username
from meshive.services.audit import AuditAction, log_event_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(prog="meshive")
    commands = parser.add_subparsers(dest="command", required=True)

    create_admin = commands.add_parser(
        "create-admin", help="Create an initial administrator"
    )
    create_admin.add_argument("--username", required=True)
    create_admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting",
    )
    reset_password = commands.add_parser(
        "reset-password", help="Reset a local user's password and revoke all sessions"
    )
    reset_password.add_argument("--username", required=True)
    reset_password.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the new password from standard input instead of prompting",
    )
    backup = commands.add_parser("backup", help="Create a consistent online SQLite backup")
    backup.add_argument("--output", type=Path)
    restore = commands.add_parser("restore", help="Restore a validated SQLite backup")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--confirm-stopped", action="store_true")
    commands.add_parser(
        "restore-pending", help="Process a restore requested through the web interface"
    )

    arguments = parser.parse_args()
    if arguments.command == "create-admin":
        _create_admin(arguments.username, arguments.password_stdin)
    elif arguments.command == "reset-password":
        _reset_password(arguments.username, arguments.password_stdin)
    elif arguments.command == "backup":
        try:
            path = create_backup(arguments.output)
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
        print(f"Backup created: {path}")
    elif arguments.command == "restore":
        try:
            safety = restore_backup(
                arguments.input, confirmed_stopped=arguments.confirm_stopped
            )
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
        print("Restore completed.")
        if safety is not None:
            print(f"Pre-restore safety backup: {safety}")
    elif arguments.command == "restore-pending":
        _restore_pending()


def _restore_pending() -> None:
    from meshive.config import get_settings

    marker = get_settings().data_dir / "restore-request.json"
    result = get_settings().data_dir / "restore-result.json"
    if not marker.is_file():
        print("No pending restore.")
        return
    backup_path: str | None = None
    actor_user_id: int | None = None
    actor_username = "Unknown"
    audit_started_at: datetime | None = None
    run_id: int | None = None
    audit_event_id: int | None = None
    is_audited_request = False
    try:
        request = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise TypeError("Invalid restore request")
        backup_path = request["path"]
        if isinstance(request.get("actor_user_id"), int):
            actor_user_id = request["actor_user_id"]
        if isinstance(request.get("actor_username"), str):
            actor_username = request["actor_username"]
        if isinstance(request.get("audit_started_at"), str):
            audit_started_at = datetime.fromisoformat(request["audit_started_at"])
        if isinstance(request.get("run_id"), int):
            run_id = request["run_id"]
        if isinstance(request.get("audit_event_id"), int):
            audit_event_id = request["audit_event_id"]
        is_audited_request = audit_started_at is not None
        safety = restore_backup(
            Path(backup_path),
            confirmed_stopped=True,
        )
        if is_audited_request and not _restore_start_is_present(audit_event_id):
            _record_restore_audit(
                actor_user_id,
                actor_username,
                run_id,
                AuditAction.BACKUP_RESTORE_STARTED,
                created_at=audit_started_at,
            )
        if is_audited_request:
            _record_restore_audit(
                actor_user_id,
                actor_username,
                run_id,
                AuditAction.BACKUP_RESTORE_COMPLETED,
            )
        payload = {
            "status": "completed",
            "backup": backup_path,
            "safety_backup": str(safety) if safety else None,
        }
        print(f"Restore completed from {backup_path}.")
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError) as error:
        if is_audited_request:
            _record_restore_audit(
                actor_user_id,
                actor_username,
                run_id,
                AuditAction.BACKUP_RESTORE_FAILED,
            )
        payload = {
            "status": "failed",
            "backup": backup_path,
            "error": str(error),
        }
        print(f"Restore failed: {error}", file=sys.stderr)
    finally:
        result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        marker.unlink(missing_ok=True)


def _record_restore_audit(
    actor_user_id: int | None,
    actor_username: str,
    run_id: int | None,
    action: str,
    *,
    created_at: datetime | None = None,
) -> None:
    with SessionLocal() as session:
        actor = session.get(User, actor_user_id) if actor_user_id is not None else None
        log_event_snapshot(
            session,
            actor_user_id=actor.id if actor is not None else None,
            actor_username=actor_username,
            action=action,
            target_type="backup",
            target_label="Database restore",
            target_id=run_id,
            created_at=created_at,
        )
        session.commit()


def _restore_start_is_present(audit_event_id: int | None) -> bool:
    if audit_event_id is None:
        return False
    with SessionLocal() as session:
        return session.scalar(select(AuditEvent.id).where(AuditEvent.id == audit_event_id)) is not None


def _create_admin(username: str, password_stdin: bool) -> None:
    username = username.strip()
    if not username:
        raise SystemExit("Username cannot be blank")

    password = _read_password(password_stdin)

    with SessionLocal() as session:
        user = User(
            username=username,
            normalized_username=normalize_username(username),
            password_hash=hash_password(password),
            role="admin",
            role_definition=get_system_role_for_legacy_role(session, "admin"),
            all_sources=True,
            is_active=True,
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise SystemExit(f"User {username!r} already exists") from error

    print(f"Administrator {username!r} created.")


def _reset_password(username: str, password_stdin: bool) -> None:
    username = username.strip()
    if not username:
        raise SystemExit("Username cannot be blank")
    password = _read_password(password_stdin)

    with SessionLocal() as session:
        user = get_user_by_username(session, username)
        if user is None:
            raise SystemExit(f"User {username!r} was not found")
        user.password_hash = hash_password(password)
        user.must_change_password = False
        session.execute(delete(UserSession).where(UserSession.user_id == user.id))
        delete_user_action_tokens(session, user.id)
        session.commit()

    print(f"Password for {user.username!r} reset; all sessions were revoked.")


def _read_password(password_stdin: bool) -> str:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    return password


if __name__ == "__main__":
    main()
