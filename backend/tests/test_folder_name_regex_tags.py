from collections.abc import Generator
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import TAG_RULES_MANAGE
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import FolderNameRegexTagMatch, FolderNameRegexTagRule, ModelTag, Tag
from meshive.models.user import User


def test_folder_name_regex_rules_match_segments_case_insensitively_and_preview() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="Admin", role_id=None, role_definition=SimpleNamespace(is_superuser=True), all_sources=True
    )
    try:
        with sessions() as session:
            source = LibrarySource(name="A", root_path="/a", directory_pattern="{model}")
            session.add(source)
            session.flush()
            session.add_all(
                [
                    LibraryModel(library_source_id=source.id, relative_path="sets/psup_p1/model", name="P1", status="available"),
                    LibraryModel(library_source_id=source.id, relative_path="sets/foo_p2/model", name="P2", status="available"),
                    LibraryModel(library_source_id=source.id, relative_path="sets/foo_p10/model", name="P10", status="available"),
                    LibraryModel(library_source_id=source.id, relative_path="sets/PSUP_P2/model", name="Upper", status="available"),
                ]
            )
            session.commit()
        with TestClient(app) as client:
            tag = client.post("/api/admin/tags", json={"name": "Variant", "color": "#112233"})
            assert tag.status_code == 201
            preview = client.post(
                "/api/admin/folder-name-tag-rules/preview",
                json={"pattern": "_p[12]$", "limit": 25},
            )
            assert preview.status_code == 200
            assert {item["model_name"] for item in preview.json()} == {"P1", "P2", "Upper"}
            with sessions() as session:
                assert session.scalar(select(func.count()).select_from(FolderNameRegexTagRule)) == 0
                assert session.scalar(select(func.count()).select_from(FolderNameRegexTagMatch)) == 0
            created = client.post(
                "/api/admin/folder-name-tag-rules",
                json={"tag_id": tag.json()["id"], "pattern": "_p[12]$", "enabled": True},
            )
            assert created.status_code == 201
            assert created.json()["match_count"] == 3
            assert client.post(
                "/api/admin/folder-name-tag-rules/preview", json={"pattern": "(", "limit": 25}
            ).status_code == 422
            assert client.put(
                f"/api/admin/folder-name-tag-rules/{created.json()['id']}",
                json={"tag_id": tag.json()["id"], "pattern": "foo_p2$", "enabled": True},
            ).status_code == 200
            assert client.delete(f"/api/admin/folder-name-tag-rules/{created.json()['id']}").status_code == 204
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(FolderNameRegexTagMatch)) == 0
            assert session.scalar(select(func.count()).select_from(ModelTag)) == 0
            actions = list(session.scalars(select(AuditEvent.action).order_by(AuditEvent.id)))
            assert actions[-3:] == [
                "folder_name_regex_tag_rule.created",
                "folder_name_regex_tag_rule.updated",
                "folder_name_regex_tag_rule.deleted",
            ]
            events = list(session.scalars(select(AuditEvent)))
            serialized = " ".join(
                f"{event.actor_username} {event.target_label} {event.details}"
                for event in events
            )
            assert "_p[12]$" not in serialized
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_folder_name_regex_rules_require_global_tag_rule_access() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with sessions() as session:
            rule_manager = Role(name="Rule manager", normalized_name="rule manager")
            no_permission = Role(name="No permission", normalized_name="no permission")
            session.add_all([rule_manager, no_permission])
            session.flush()
            session.add(RolePermission(role_id=rule_manager.id, permission_key=TAG_RULES_MANAGE))
            scoped_user = User(
                username="Scoped",
                normalized_username="scoped",
                password_hash="unused",
                role="user",
                role_definition=rule_manager,
                all_sources=False,
                is_active=True,
            )
            forbidden_user = User(
                username="Forbidden",
                normalized_username="forbidden",
                password_hash="unused",
                role="user",
                role_definition=no_permission,
                all_sources=True,
                is_active=True,
            )
            session.add_all([scoped_user, forbidden_user])
            session.add(Tag(name="Tag"))
            session.commit()
        with TestClient(app) as client:
            app.dependency_overrides[get_current_user] = lambda: scoped_user
            assert client.get("/api/admin/folder-name-tag-rules").status_code == 403
            assert client.post(
                "/api/admin/folder-name-tag-rules/preview", json={"pattern": "_p1$"}
            ).status_code == 403
            app.dependency_overrides[get_current_user] = lambda: forbidden_user
            assert client.get("/api/admin/folder-name-tag-rules").status_code == 403
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(FolderNameRegexTagRule)) == 0
            assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
