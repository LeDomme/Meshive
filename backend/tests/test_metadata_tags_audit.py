from collections.abc import Generator
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user
from meshive.auth.passwords import hash_password
from meshive.auth.permissions import CATALOGUE_VIEW, MODELS_TAGS
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import Tag
from meshive.models.user import User
from meshive.repositories.roles import ensure_system_roles
from tests.test_auth import authenticated_test_client


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), "#22d3ee").save(output, format="PNG")
    return output.getvalue()


def _add_admin(sessions) -> None:
    with sessions() as session:
        ensure_system_roles(session)
        administrator = session.scalar(select(Role).where(Role.name == "Administrator"))
        assert administrator is not None
        session.add(
            User(
                username="Admin",
                normalized_username="admin",
                password_hash=hash_password("correct horse battery staple"),
                role="admin",
                role_definition=administrator,
                all_sources=True,
                is_active=True,
            )
        )
        session.commit()


def test_metadata_and_tag_mutations_are_audited_without_raw_values() -> None:
    with authenticated_test_client() as (client, sessions):
        _add_admin(sessions)
        with sessions() as session:
            source = LibrarySource(
                name="Source A",
                root_path="/private/library",
                directory_pattern="{private_pattern}",
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="private-folder/model",
                name="Model A",
                creator="Creator A",
                status="available",
            )
            session.add(model)
            session.commit()
            source_id, model_id = source.id, model.id

        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200
        tag = client.post(
            "/api/admin/tags",
            json={"name": "Audit tag", "color": "#112233", "description": "private text"},
        )
        assert tag.status_code == 201
        tag_id = tag.json()["id"]
        assert client.put(
            f"/api/admin/tags/{tag_id}",
            json={"name": "Audit tag renamed", "color": "#445566", "description": "secret description"},
        ).status_code == 200
        assert client.put(f"/api/admin/models/{model_id}/tags/{tag_id}").status_code == 204
        assert client.delete(f"/api/admin/models/{model_id}/tags/{tag_id}").status_code == 204

        rule = client.post(
            "/api/admin/folder-tag-rules",
            json={"library_source_id": source_id, "relative_path": "private-folder", "tag_id": tag_id, "recursive": True},
        )
        assert rule.status_code == 201
        rule_id = rule.json()["id"]
        assert client.put(
            f"/api/admin/folder-tag-rules/{rule_id}",
            json={"library_source_id": source_id, "relative_path": "other-private-folder", "tag_id": tag_id, "recursive": False},
        ).status_code == 200
        assert client.delete(f"/api/admin/folder-tag-rules/{rule_id}").status_code == 204

        automatic = client.post(
            "/api/admin/automatic-tag-rules",
            json={"tag_id": tag_id, "pattern": "secret-pattern", "enabled": True},
        )
        assert automatic.status_code == 201
        automatic_id = automatic.json()["id"]
        assert client.put(
            f"/api/admin/automatic-tag-rules/{automatic_id}",
            json={"tag_id": tag_id, "pattern": "other-secret-pattern", "enabled": False},
        ).status_code == 200
        assert client.delete(f"/api/admin/automatic-tag-rules/{automatic_id}").status_code == 204

        upload = client.put(
            "/api/admin/metadata/artwork",
            data={"entity_type": "creator", "value": "Creator A"},
            files={"image": ("private-image.png", _png(), "image/png")},
        )
        assert upload.status_code == 200
        assert client.put(
            "/api/admin/metadata/artwork",
            data={"entity_type": "creator", "value": "Creator A"},
            files={"image": ("replacement.png", _png(), "image/png")},
        ).status_code == 200
        assert client.delete(
            "/api/admin/metadata/artwork",
            params={"entity_type": "creator", "value": "Creator A"},
        ).status_code == 204

        link = client.post(
            "/api/admin/creator-links",
            json={"creator_name": "Creator A", "kind": "website", "url": "https://example.com/private"},
        )
        assert link.status_code == 201
        assert client.put(
            f"/api/admin/creator-links/{link.json()['id']}",
            json={"kind": "patreon", "url": "https://example.com/secret"},
        ).status_code == 200
        assert client.delete(f"/api/admin/creator-links/{link.json()['id']}").status_code == 204

        action_count_before_failure = 0
        with sessions() as session:
            action_count_before_failure = session.scalar(
                select(func.count()).select_from(AuditEvent)
            )
        assert client.post(
            "/api/admin/tags",
            json={"name": "Audit tag renamed", "color": None},
        ).status_code == 409
        assert client.delete(f"/api/admin/tags/{tag_id}").status_code == 204

        with sessions() as session:
            events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.id)))
            assert session.scalar(select(func.count()).select_from(AuditEvent)) == (
                action_count_before_failure + 1
            )
            actions = {event.action for event in events}
            assert {
                "metadata.created", "metadata.updated", "metadata.deleted",
                "tag.created", "tag.updated", "tag.deleted",
                "folder_tag_rule.created", "folder_tag_rule.updated", "folder_tag_rule.deleted",
                "automatic_tag_rule.created", "automatic_tag_rule.updated", "automatic_tag_rule.deleted",
                "model_tag.added", "model_tag.removed",
            } <= actions
            source_events = [
                event for event in events
                if event.action.startswith(("folder_tag_rule.", "model_tag."))
            ]
            assert source_events and all(event.library_source_id == source_id for event in source_events)
            assert all(event.library_source_id is None for event in events if event.action.startswith(("metadata.", "tag.", "automatic_tag_rule.")))
            serialized = " ".join(
                f"{event.target_label} {event.details}" for event in events
            )
            for forbidden in ("/private/library", "private-pattern", "secret-pattern", "secret description", "example.com", "private-image.png"):
                assert forbidden not in serialized


def test_hidden_or_forbidden_model_tag_changes_leave_no_audit_event() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
            source_a = LibrarySource(name="A", root_path="/a", directory_pattern="{model}")
            source_b = LibrarySource(name="B", root_path="/b", directory_pattern="{model}")
            editor_role = Role(name="Editor", normalized_name="editor")
            no_permission_role = Role(name="No permission", normalized_name="no permission")
            session.add_all([source_a, source_b, editor_role, no_permission_role])
            session.flush()
            session.add_all([
                RolePermission(role_id=editor_role.id, permission_key=CATALOGUE_VIEW),
                RolePermission(role_id=editor_role.id, permission_key=MODELS_TAGS),
            ])
            model_a = LibraryModel(library_source_id=source_a.id, relative_path="A", name="A", status="available")
            model_b = LibraryModel(library_source_id=source_b.id, relative_path="B", name="B", status="available")
            tag = Tag(name="Tag")
            editor = User(username="Editor", normalized_username="editor", password_hash="unused", role="user", role_definition=editor_role, all_sources=False, is_active=True)
            forbidden = User(username="Forbidden", normalized_username="forbidden", password_hash="unused", role="user", role_definition=no_permission_role, all_sources=False, is_active=True)
            session.add_all([model_a, model_b, tag, editor, forbidden])
            session.flush()
            session.add_all([UserLibrarySource(user_id=editor.id, library_source_id=source_a.id), UserLibrarySource(user_id=forbidden.id, library_source_id=source_a.id)])
            session.commit()
        with TestClient(app) as client:
            current_user[:] = [editor]
            assert client.put(f"/api/admin/models/{model_b.id}/tags/{tag.id}").status_code == 404
            current_user[:] = [forbidden]
            assert client.put(f"/api/admin/models/{model_a.id}/tags/{tag.id}").status_code == 403
        with sessions() as session:
            assert list(session.scalars(select(AuditEvent))) == []
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
