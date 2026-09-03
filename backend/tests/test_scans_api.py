from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.authorization import Role, UserLibrarySource
from meshive.models.catalog import ScanRun
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.repositories.roles import ensure_system_roles


def test_reading_scans_is_scoped_by_source_and_permission() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    current_user: list[User] = []

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current_user[0]
    try:
        with sessions() as session:
            ensure_system_roles(session)
            roles = {role.name: role for role in session.query(Role)}
            source_a = LibrarySource(name="Source A", root_path="/a", directory_pattern="{model}")
            source_b = LibrarySource(name="Source B", root_path="/b", directory_pattern="{model}")
            admin = User(
                username="Admin",
                normalized_username="admin",
                password_hash="unused",
                role="admin",
                role_definition=roles["Administrator"],
                all_sources=True,
            )
            all_sources = User(
                username="All sources",
                normalized_username="all sources",
                password_hash="unused",
                role="user",
                role_definition=roles["Operator"],
                all_sources=True,
            )
            a_only = User(
                username="A only",
                normalized_username="a only",
                password_hash="unused",
                role="user",
                role_definition=roles["Operator"],
                all_sources=False,
            )
            no_grant = User(
                username="No grant",
                normalized_username="no grant",
                password_hash="unused",
                role="user",
                role_definition=roles["Operator"],
                all_sources=False,
            )
            viewer = User(
                username="Viewer",
                normalized_username="viewer",
                password_hash="unused",
                role="user",
                role_definition=roles["Viewer"],
                all_sources=False,
            )
            session.add_all([source_a, source_b, admin, all_sources, a_only, no_grant, viewer])
            session.flush()
            session.add_all(
                [
                    UserLibrarySource(user_id=a_only.id, library_source_id=source_a.id),
                    UserLibrarySource(user_id=viewer.id, library_source_id=source_a.id),
                    ScanRun(library_source_id=source_a.id, status="pending", mode="smart"),
                    ScanRun(library_source_id=source_a.id, status="completed", mode="smart"),
                    ScanRun(library_source_id=source_b.id, status="pending", mode="smart"),
                    ScanRun(library_source_id=source_b.id, status="completed", mode="smart"),
                ]
            )
            session.commit()
            scans = list(session.query(ScanRun).order_by(ScanRun.id))
            a_scan_ids = {scan.id for scan in scans if scan.library_source_id == source_a.id}
            b_scan_ids = {scan.id for scan in scans if scan.library_source_id == source_b.id}
            b_pending_id = next(
                scan.id
                for scan in scans
                if scan.library_source_id == source_b.id and scan.status == "pending"
            )
            a_pending_id = next(
                scan.id
                for scan in scans
                if scan.library_source_id == source_a.id and scan.status == "pending"
            )

        with TestClient(app) as client:
            current_user[:] = [admin]
            assert {scan["id"] for scan in client.get(f"/api/admin/library-sources/{source_a.id}/scans").json()} == a_scan_ids
            assert {scan["id"] for scan in client.get(f"/api/admin/library-sources/{source_b.id}/scans").json()} == b_scan_ids
            assert client.get("/api/admin/library-sources/999999/scans").status_code == 404
            assert {scan["id"] for scan in client.get("/api/admin/scans/queue").json()} == {
                a_pending_id,
                b_pending_id,
            }
            assert client.get(f"/api/admin/scans/{b_pending_id}").status_code == 200

            current_user[:] = [all_sources]
            assert {scan["id"] for scan in client.get("/api/admin/scans/queue").json()} == {
                a_pending_id,
                b_pending_id,
            }
            assert client.get(f"/api/admin/scans/{b_pending_id}").status_code == 200

            current_user[:] = [a_only]
            a_history = client.get(f"/api/admin/library-sources/{source_a.id}/scans")
            assert {scan["id"] for scan in a_history.json()} == a_scan_ids
            assert client.get(f"/api/admin/library-sources/{source_b.id}/scans").status_code == 404
            queue = client.get("/api/admin/scans/queue")
            assert {scan["id"] for scan in queue.json()} == {
                a_pending_id
            }
            assert all(scan["position"] == 1 for scan in queue.json())
            assert all(scan["library_source_id"] == source_a.id for scan in queue.json())
            assert client.get(f"/api/admin/scans/{a_pending_id}").status_code == 200
            assert client.get(f"/api/admin/scans/{b_pending_id}").status_code == 404

            current_user[:] = [no_grant]
            assert client.get(f"/api/admin/library-sources/{source_a.id}/scans").status_code == 404
            assert client.get(f"/api/admin/library-sources/{source_b.id}/scans").status_code == 404
            assert client.get("/api/admin/scans/queue").json() == []
            assert client.get(f"/api/admin/scans/{b_pending_id}").status_code == 404

            current_user[:] = [viewer]
            assert client.get(f"/api/admin/library-sources/{source_a.id}/scans").status_code == 403
            assert client.get(f"/api/admin/library-sources/{source_b.id}/scans").status_code == 404
            assert client.get("/api/admin/scans/queue").status_code == 403
            assert client.get(f"/api/admin/scans/{next(iter(a_scan_ids))}").status_code == 403
            assert client.get(f"/api/admin/scans/{b_pending_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_start_and_control_scans_require_visible_sources_and_permissions(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    current_user: list[User] = []

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current_user[0]
    monkeypatch.setattr("meshive.api.scans.dispatch_pending_scans", lambda: None)
    try:
        with sessions() as session:
            ensure_system_roles(session)
            roles = {role.name: role for role in session.query(Role)}
            source_a = LibrarySource(
                name="Source A",
                root_path="/a",
                directory_pattern="{model}",
                is_active=True,
                scan_enabled=True,
            )
            source_b = LibrarySource(
                name="Source B",
                root_path="/b",
                directory_pattern="{model}",
                is_active=True,
                scan_enabled=True,
            )
            users = {
                "admin": User(
                    username="Admin",
                    normalized_username="admin",
                    password_hash="unused",
                    role="admin",
                    role_definition=roles["Administrator"],
                    all_sources=True,
                ),
                "all_sources": User(
                    username="All sources",
                    normalized_username="all sources",
                    password_hash="unused",
                    role="user",
                    role_definition=roles["Operator"],
                    all_sources=True,
                ),
                "a_only": User(
                    username="A only",
                    normalized_username="a only",
                    password_hash="unused",
                    role="user",
                    role_definition=roles["Operator"],
                    all_sources=False,
                ),
                "no_grant": User(
                    username="No grant",
                    normalized_username="no grant",
                    password_hash="unused",
                    role="user",
                    role_definition=roles["Operator"],
                    all_sources=False,
                ),
                "viewer": User(
                    username="Viewer",
                    normalized_username="viewer",
                    password_hash="unused",
                    role="user",
                    role_definition=roles["Viewer"],
                    all_sources=False,
                ),
            }
            session.add_all([source_a, source_b, *users.values()])
            session.flush()
            session.add_all(
                [
                    UserLibrarySource(user_id=users["a_only"].id, library_source_id=source_a.id),
                    UserLibrarySource(user_id=users["viewer"].id, library_source_id=source_a.id),
                    ScanRun(library_source_id=source_a.id, status="pending", mode="smart"),
                    ScanRun(library_source_id=source_a.id, status="completed", mode="smart"),
                    ScanRun(library_source_id=source_b.id, status="completed", mode="smart"),
                ]
            )
            session.commit()
            scans = list(session.query(ScanRun).order_by(ScanRun.id))
            a_pending_id = next(
                scan.id
                for scan in scans
                if scan.library_source_id == source_a.id and scan.status == "pending"
            )
            a_completed_id = next(
                scan.id
                for scan in scans
                if scan.library_source_id == source_a.id and scan.status == "completed"
            )
            b_scan_id = next(scan.id for scan in scans if scan.library_source_id == source_b.id)

        with TestClient(app) as client:
            current_user[:] = [users["a_only"]]
            assert client.post(f"/api/admin/library-sources/{source_a.id}/scan").status_code == 409
            assert client.post(f"/api/admin/library-sources/{source_b.id}/scan").status_code == 404
            assert client.post(f"/api/admin/scans/{a_pending_id}/pause").status_code == 200
            assert client.post(f"/api/admin/scans/{a_pending_id}/resume").status_code == 200
            assert client.post(f"/api/admin/scans/{a_pending_id}/cancel").status_code == 200
            assert client.post(f"/api/admin/scans/{b_scan_id}/pause").status_code == 404
            assert client.post(f"/api/admin/scans/{a_completed_id}/pause").status_code == 409

            current_user[:] = [users["no_grant"]]
            assert client.post(f"/api/admin/library-sources/{source_a.id}/scan").status_code == 404
            assert client.post(f"/api/admin/library-sources/{source_b.id}/scan").status_code == 404
            assert client.post(f"/api/admin/scans/{b_scan_id}/cancel").status_code == 404

            current_user[:] = [users["viewer"]]
            assert client.post(f"/api/admin/library-sources/{source_a.id}/scan").status_code == 403
            assert client.post(f"/api/admin/scans/{a_completed_id}/pause").status_code == 403
            assert client.post(f"/api/admin/scans/{b_scan_id}/pause").status_code == 404

            current_user[:] = [users["all_sources"]]
            started = client.post(f"/api/admin/library-sources/{source_b.id}/scan")
            assert started.status_code == 202
            assert started.json()["mode"] == "smart"
            b_started_id = started.json()["id"]
            assert client.post(f"/api/admin/scans/{b_started_id}/pause").status_code == 200

            current_user[:] = [users["admin"]]
            assert client.post(f"/api/admin/scans/{b_started_id}/resume").status_code == 200

        with sessions() as session:
            b_scan = session.get(ScanRun, b_started_id)
            assert b_scan is not None
            assert b_scan.pause_requested is False
            assert b_scan.cancel_requested is False
            assert session.get(ScanRun, a_pending_id).status == "cancelled"
            assert session.get(ScanRun, a_completed_id).pause_requested is False
            assert session.get(ScanRun, b_scan_id).status == "completed"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
