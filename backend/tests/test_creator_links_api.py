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


def test_creator_links_are_managed_and_exposed_on_model_details() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Creator model",
                name="Creator model",
                creator="Aoae",
                status="available",
            )
            session.add(model)
            session.commit()

        with TestClient(app) as client:
            initial = client.get("/api/admin/creator-links")
            assert initial.status_code == 200
            assert initial.json() == [
                {"name": "Aoae", "model_count": 1, "links": []}
            ]

            invalid = client.post(
                "/api/admin/creator-links",
                json={
                    "creator_name": "Aoae",
                    "kind": "website",
                    "url": "javascript:alert(1)",
                },
            )
            assert invalid.status_code == 422

            unknown = client.post(
                "/api/admin/creator-links",
                json={
                    "creator_name": "Unknown",
                    "kind": "website",
                    "url": "https://example.com/unknown",
                },
            )
            assert unknown.status_code == 404

            website = client.post(
                "/api/admin/creator-links",
                json={
                    "creator_name": "aoae",
                    "kind": "website",
                    "url": "https://example.com/aoae",
                },
            )
            assert website.status_code == 201
            assert website.json()["label"] == "Website"

            patreon = client.post(
                "/api/admin/creator-links",
                json={
                    "creator_name": "Aoae",
                    "kind": "patreon",
                    "url": "https://patreon.com/aoae",
                },
            )
            assert patreon.status_code == 201

            missing_other_label = client.post(
                "/api/admin/creator-links",
                json={
                    "creator_name": "Aoae",
                    "kind": "other",
                    "url": "https://example.com/store",
                },
            )
            assert missing_other_label.status_code == 422

            duplicate = client.post(
                "/api/admin/creator-links",
                json={
                    "creator_name": "Aoae",
                    "kind": "website",
                    "url": "https://example.com/second",
                },
            )
            assert duplicate.status_code == 409

            detail = client.get(f"/api/models/{model.id}")
            assert detail.status_code == 200
            assert detail.json()["creator_url"] == "https://example.com/aoae"
            assert [link["label"] for link in detail.json()["creator_links"]] == [
                "Patreon",
                "Website",
            ]

            updated = client.put(
                f"/api/admin/creator-links/{patreon.json()['id']}",
                json={
                    "kind": "cults3d",
                    "url": "https://cults3d.com/en/users/aoae",
                },
            )
            assert updated.status_code == 200
            assert updated.json()["label"] == "Cults3D"

            removed = client.delete(
                f"/api/admin/creator-links/{website.json()['id']}"
            )
            assert removed.status_code == 204
            remaining_detail = client.get(f"/api/models/{model.id}").json()
            assert [link["label"] for link in remaining_detail["creator_links"]] == [
                "Cults3D"
            ]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
