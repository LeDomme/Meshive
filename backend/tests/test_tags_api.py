from collections.abc import Generator
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.auth.permissions import CATALOGUE_VIEW, MODELS_TAGS
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import ModelTag, Tag
from meshive.models.user import User


def test_direct_and_recursive_tags_are_exposed_and_filterable() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role_id=None, role_definition=SimpleNamespace(is_superuser=True), all_sources=True
    )
    app.dependency_overrides[require_admin] = lambda: None
    try:
        with sessions() as session:
            source = LibrarySource(
                name="Test",
                root_path="/models/test",
                directory_pattern="{franchise}/{model_folder}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Marvel/X-Men/Wolverine",
                name="Wolverine",
                status="available",
            )
            session.add(model)
            session.commit()

        with TestClient(app) as client:
            created = client.post(
                "/api/admin/tags",
                json={"name": "Favourite", "color": "#ff0000"},
            )
            assert created.status_code == 201
            tag_id = created.json()["id"]
            assert client.put(f"/api/admin/models/{model.id}/tags/{tag_id}").status_code == 204
            updated = client.put(
                f"/api/admin/tags/{tag_id}",
                json={
                    "name": "Curated",
                    "color": "#123abc",
                    "description": "Reviewed by an administrator",
                },
            )
            assert updated.status_code == 200
            assert updated.json() == {
                "id": tag_id,
                "name": "Curated",
                "color": "#123abc",
                "description": "Reviewed by an administrator",
            }
            filtered = client.get("/api/models", params={"tag_id": tag_id})
            assert filtered.json()["total"] == 1

            inherited = client.post(
                "/api/admin/tags",
                json={"name": "Marvel", "color": "#00ff00"},
            ).json()
            rule = client.post(
                "/api/admin/folder-tag-rules",
                json={
                    "library_source_id": source.id,
                    "relative_path": "Marvel",
                    "tag_id": inherited["id"],
                    "recursive": True,
                },
            )
            assert rule.status_code == 201
            detail = client.get(f"/api/models/{model.id}").json()
            assert {tag["name"] for tag in detail["tags"]} == {"Curated", "Marvel"}
            conflict = client.put(
                f"/api/admin/tags/{tag_id}",
                json={"name": "Marvel", "color": None, "description": None},
            )
            assert conflict.status_code == 409
            assert {
                tag["name"] for tag in client.get(f"/api/models/{model.id}").json()["tags"]
            } == {"Curated", "Marvel"}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_tags_and_direct_model_actions_are_source_scoped() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_admin] = lambda: None
    try:
        with sessions() as session:
            a = LibrarySource(name="A", root_path="/a", directory_pattern="{model}")
            b = LibrarySource(name="B", root_path="/b", directory_pattern="{model}")
            tag_editor = Role(name="Tag editor", normalized_name="tag editor")
            no_tags_role = Role(name="No tags", normalized_name="no tags")
            session.add_all([a, b, tag_editor, no_tags_role]); session.flush()
            session.add_all([
                RolePermission(role_id=tag_editor.id, permission_key=CATALOGUE_VIEW),
                RolePermission(role_id=tag_editor.id, permission_key=MODELS_TAGS),
            ])
            model_a = LibraryModel(library_source_id=a.id, relative_path="A", name="A", status="available")
            model_b = LibraryModel(library_source_id=b.id, relative_path="B", name="B", status="available")
            tag_a, tag_b, tag_shared = Tag(name="A tag"), Tag(name="B tag"), Tag(name="Shared tag")
            a_only = User(username="A", normalized_username="a", password_hash="unused", role="user", role_definition=tag_editor, all_sources=False, is_active=True)
            all_sources = User(username="All", normalized_username="all", password_hash="unused", role="user", role_definition=tag_editor, all_sources=True, is_active=True)
            no_grant = User(username="None", normalized_username="none", password_hash="unused", role="user", role_definition=tag_editor, all_sources=False, is_active=True)
            no_tags = User(username="No tags", normalized_username="no tags", password_hash="unused", role="user", role_definition=no_tags_role, all_sources=False, is_active=True)
            session.add_all([model_a, model_b, tag_a, tag_b, tag_shared, a_only, all_sources, no_grant, no_tags]); session.flush()
            session.add_all([UserLibrarySource(user_id=a_only.id, library_source_id=a.id), UserLibrarySource(user_id=no_tags.id, library_source_id=a.id), ModelTag(model_id=model_a.id, tag_id=tag_a.id), ModelTag(model_id=model_a.id, tag_id=tag_shared.id), ModelTag(model_id=model_b.id, tag_id=tag_b.id), ModelTag(model_id=model_b.id, tag_id=tag_shared.id)])
            session.commit()
        with TestClient(app) as client:
            app.dependency_overrides[get_current_user] = lambda: a_only
            assert [tag["name"] for tag in client.get("/api/tags").json()] == ["A tag", "Shared tag"]
            assert client.put(f"/api/admin/models/{model_b.id}/tags/{tag_a.id}").status_code == 404
            with sessions() as session:
                assert session.scalar(select(ModelTag).where(ModelTag.model_id == model_b.id, ModelTag.tag_id == tag_a.id)) is None
            assert client.put(f"/api/admin/models/{model_a.id}/tags/999").status_code == 404
            assert client.delete(f"/api/admin/models/{model_b.id}/tags/{tag_b.id}").status_code == 404
            app.dependency_overrides[get_current_user] = lambda: no_tags
            assert client.get("/api/tags").status_code == 403
            assert client.put(f"/api/admin/models/{model_a.id}/tags/{tag_a.id}").status_code == 403
            assert client.delete(f"/api/admin/models/{model_b.id}/tags/{tag_b.id}").status_code == 404
            app.dependency_overrides[get_current_user] = lambda: no_grant
            assert client.get("/api/tags").json() == []
            app.dependency_overrides[get_current_user] = lambda: all_sources
            assert {tag["name"] for tag in client.get("/api/tags").json()} == {"A tag", "B tag", "Shared tag"}
            assert client.put(f"/api/admin/models/{model_a.id}/tags/{tag_b.id}").status_code == 204
    finally:
        app.dependency_overrides.clear(); Base.metadata.drop_all(engine); engine.dispose()
