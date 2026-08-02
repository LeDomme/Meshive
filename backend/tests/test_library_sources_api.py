from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import require_admin
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.catalog import LibraryModel


def allow_admin() -> None:
    return None


@contextmanager
def build_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with test_session() as session:
            yield session

    app.dependency_overrides[require_admin] = allow_admin
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, test_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def source_payload() -> dict:
    return {
        "name": "Bulkamancer",
        "root_path": "/models/bulkamancer",
        "directory_pattern": "{creator_folder}/{franchise}/{model_folder}",
        "model_pattern": "{franchise} - {model} - by {creator}",
    }


def test_admin_routes_require_authentication() -> None:
    response = TestClient(app).get("/api/admin/library-sources")

    assert response.status_code == 401


def test_create_list_update_and_delete_source() -> None:
    with build_client() as (client, sessions):
        created = client.post("/api/admin/library-sources", json=source_payload())
        assert created.status_code == 201
        source_id = created.json()["id"]
        assert created.json()["archive_formats"] == ["7z", "zip", "rar"]

        listed = client.get("/api/admin/library-sources")
        assert listed.status_code == 200
        assert [source["name"] for source in listed.json()] == ["Bulkamancer"]

        update = source_payload()
        update["name"] = "Bulkamancer Sculpts"
        updated = client.put(f"/api/admin/library-sources/{source_id}", json=update)
        assert updated.status_code == 200
        assert updated.json()["name"] == "Bulkamancer Sculpts"

        with sessions() as session:
            session.add(
                LibraryModel(
                    library_source_id=source_id,
                    relative_path="Example/Example model",
                    name="Example model",
                    status="available",
                )
            )
            session.commit()

        deleted = client.delete(f"/api/admin/library-sources/{source_id}")
        assert deleted.status_code == 204
        assert client.get("/api/admin/library-sources").json() == []
        with sessions() as session:
            assert session.query(LibraryModel).count() == 0


def test_preview_endpoint_parses_confirmed_layout() -> None:
    with build_client() as (client, _sessions):
        response = client.post(
            "/api/admin/library-sources/preview",
            json={
                "directory_pattern": "{franchise}/{model_folder}",
                "model_pattern": "{franchise} - {model} - by {creator}",
                "relative_path": "Animal Crossing/Animal Crossing - Ankha - by Rubim",
            },
        )

        assert response.status_code == 200
        assert response.json()["values"]["model"] == "Ankha"
        assert response.json()["warnings"] == []


def test_preview_endpoint_returns_variant_and_ambiguity_warning() -> None:
    with build_client() as (client, _sessions):
        response = client.post(
            "/api/admin/library-sources/preview",
            json={
                "directory_pattern": "{franchise}/{model_folder}",
                "model_pattern": (
                    "{franchise} - {series} - {model} - by {creator}\n"
                    "{franchise} - {model} - {variant} - by {creator}"
                ),
                "relative_path": "Marvel/Marvel - Psylocke - Chibi - by Example",
            },
        )

        assert response.status_code == 200
        assert response.json()["values"] == {
            "franchise": "Marvel",
            "model_folder": "Marvel - Psylocke - Chibi - by Example",
            "series": "Psylocke",
            "model": "Chibi",
            "creator": "Example",
        }
        assert len(response.json()["warnings"]) == 1
