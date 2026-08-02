from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource


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
    app.dependency_overrides[get_current_user] = lambda: object()
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
