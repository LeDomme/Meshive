import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from meshive.auth.passwords import hash_password
from meshive.database import SessionLocal
from meshive.models.user import User
from meshive.repositories.users import normalize_username
from meshive.backup import create_backup, restore_backup


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
    try:
        request = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("Invalid restore request")
        backup_path = request["path"]
        safety = restore_backup(
            Path(backup_path),
            confirmed_stopped=True,
        )
        payload = {
            "status": "completed",
            "backup": backup_path,
            "safety_backup": str(safety) if safety else None,
        }
        print(f"Restore completed from {backup_path}.")
    except Exception as error:
        payload = {
            "status": "failed",
            "backup": backup_path,
            "error": str(error),
        }
        print(f"Restore failed: {error}", file=sys.stderr)
    finally:
        result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        marker.unlink(missing_ok=True)


def _create_admin(username: str, password_stdin: bool) -> None:
    username = username.strip()
    if not username:
        raise SystemExit("Username cannot be blank")

    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")

    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")

    with SessionLocal() as session:
        user = User(
            username=username,
            normalized_username=normalize_username(username),
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise SystemExit(f"User {username!r} already exists") from error

    print(f"Administrator {username!r} created.")


if __name__ == "__main__":
    main()
