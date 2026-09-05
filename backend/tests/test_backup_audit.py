from pathlib import Path

from sqlalchemy import select

from meshive import cli, config
from meshive.api import backups as backup_api
from meshive.auth.passwords import hash_password
from meshive.config import Settings
from meshive.models.audit import AuditEvent
from meshive.models.backup import BackupRun
from meshive.models.user import User
from meshive.repositories.roles import get_system_role_for_legacy_role
from meshive.services import backup_scheduler
from tests.test_auth import authenticated_test_client


def _add_user(sessions, username: str, role: str) -> None:
    with sessions() as session:
        session.add(
            User(
                username=username,
                normalized_username=username.casefold(),
                password_hash=hash_password("correct horse battery staple"),
                role=role,
                role_definition=get_system_role_for_legacy_role(session, role),
                all_sources=True,
                is_active=True,
            )
        )
        session.commit()


def _event_actions(sessions) -> list[str]:
    with sessions() as session:
        return list(session.scalars(select(AuditEvent.action).order_by(AuditEvent.id)))


def test_manual_backup_audits_success_failure_and_not_scheduler(tmp_path, monkeypatch) -> None:
    with authenticated_test_client() as (client, sessions):
        settings = Settings(data_dir=tmp_path / "data", backup_dir=tmp_path / "backups")
        monkeypatch.setattr(backup_scheduler, "SessionLocal", sessions)
        monkeypatch.setattr(backup_scheduler, "get_settings", lambda: settings)
        monkeypatch.setattr(backup_api, "get_settings", lambda: settings)
        _add_user(sessions, "Admin", "admin")
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200

        def create_success(path: Path) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"backup")
            return path

        monkeypatch.setattr(backup_scheduler, "create_backup", create_success)
        assert client.post("/api/admin/backups/run").status_code == 200
        assert _event_actions(sessions) == ["backup.started", "backup.completed"]

        def create_failure(_path: Path) -> Path:
            raise RuntimeError("failed at /sensitive/meshive-manual-secret.zip")

        monkeypatch.setattr(backup_scheduler, "create_backup", create_failure)
        assert client.post("/api/admin/backups/run").status_code == 500
        assert _event_actions(sessions) == [
            "backup.started",
            "backup.completed",
            "backup.started",
            "backup.failed",
        ]

        backup_scheduler.run_backup("scheduled")
        assert _event_actions(sessions) == [
            "backup.started",
            "backup.completed",
            "backup.started",
            "backup.failed",
        ]
        with sessions() as session:
            events = session.query(AuditEvent).order_by(AuditEvent.id).all()
            assert all(event.target_type == "backup" for event in events)
            assert all(event.target_label == "Manual backup" for event in events)
            serialized = " ".join(
                f"{event.target_label} {event.details}" for event in events
            )
            assert "/sensitive" not in serialized
            assert "meshive-manual-secret.zip" not in serialized


def test_restore_audits_success_and_failure_without_sensitive_details(
    tmp_path, monkeypatch
) -> None:
    with authenticated_test_client() as (client, sessions):
        settings = Settings(data_dir=tmp_path / "data", backup_dir=tmp_path / "backups")
        settings.data_dir.mkdir(parents=True)
        backup_path = settings.backup_dir / "manual" / "backup.zip"
        backup_path.parent.mkdir(parents=True)
        backup_path.write_bytes(b"backup")
        monkeypatch.setattr(backup_api, "get_settings", lambda: settings)
        monkeypatch.setattr(backup_api, "validate_backup", lambda _path: None)
        monkeypatch.setattr(backup_api, "_restart_process", lambda: None)
        monkeypatch.setattr(config, "get_settings", lambda: settings)
        monkeypatch.setattr(cli, "SessionLocal", sessions)
        _add_user(sessions, "Admin", "admin")
        with sessions() as session:
            run = BackupRun(status="completed", trigger="manual", path=str(backup_path))
            session.add(run)
            session.commit()
            run_id = run.id
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200

        monkeypatch.setattr(cli, "restore_backup", lambda *_args, **_kwargs: None)
        assert client.post(
            f"/api/admin/backups/restore/{run_id}", json={"confirmation": "RESTORE"}
        ).status_code == 202
        cli._restore_pending()
        assert _event_actions(sessions) == [
            "backup.restore_started",
            "backup.restore_completed",
        ]

        assert client.post(
            f"/api/admin/backups/restore/{run_id}", json={"confirmation": "RESTORE"}
        ).status_code == 202
        monkeypatch.setattr(
            cli,
            "restore_backup",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("failure at /sensitive/restore.zip")
            ),
        )
        cli._restore_pending()
        assert _event_actions(sessions) == [
            "backup.restore_started",
            "backup.restore_completed",
            "backup.restore_started",
            "backup.restore_failed",
        ]
        with sessions() as session:
            events = session.query(AuditEvent).order_by(AuditEvent.id).all()
            assert all(event.target_label == "Database restore" for event in events)
            assert all(event.details is None for event in events)


def test_backup_permission_failure_creates_no_audit_event(tmp_path, monkeypatch) -> None:
    with authenticated_test_client() as (client, sessions):
        settings = Settings(data_dir=tmp_path / "data", backup_dir=tmp_path / "backups")
        monkeypatch.setattr(backup_scheduler, "SessionLocal", sessions)
        monkeypatch.setattr(backup_scheduler, "get_settings", lambda: settings)
        _add_user(sessions, "Member", "user")
        assert client.post(
            "/api/auth/login",
            json={"username": "member", "password": "correct horse battery staple"},
        ).status_code == 200
        assert client.post("/api/admin/backups/run").status_code == 403
        assert client.post(
            "/api/admin/backups/restore/1", json={"confirmation": "RESTORE"}
        ).status_code == 403
        assert _event_actions(sessions) == []
