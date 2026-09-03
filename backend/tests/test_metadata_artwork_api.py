from collections.abc import Generator
from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.authorization import UserLibrarySource
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.metadata import MetadataArtwork
from meshive.models.user import User
from meshive.repositories.roles import get_system_role_for_legacy_role


def _png(width: int = 2000, height: int = 1000) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "#22d3ee").save(output, format="PNG")
    return output.getvalue()


def test_metadata_artwork_is_validated_stored_and_served() -> None:
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
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role_id=None, role_definition=SimpleNamespace(is_superuser=True), all_sources=True
    )
    app.dependency_overrides[require_admin] = lambda: None
    try:
        with sessions() as session:
            source = LibrarySource(
                name="Metadata",
                root_path="/models/metadata",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            session.add_all(
                [
                    LibraryModel(
                        library_source_id=source.id,
                        relative_path="Marvel/Psylocke",
                        name="Psylocke",
                        creator="E.S Monster",
                        franchise="Marvel",
                        collection="Paid",
                        status="available",
                    ),
                    LibraryModel(
                        library_source_id=source.id,
                        relative_path="Marvel/Storm",
                        name="Storm",
                        creator="E.S Monster",
                        franchise="Marvel",
                        collection="Paid",
                        status="available",
                    ),
                ]
            )
            session.commit()

        with TestClient(app) as client:
            entities = client.get("/api/admin/metadata")
            assert entities.status_code == 200
            creator = next(
                item
                for item in entities.json()
                if item["entity_type"] == "creator"
            )
            assert creator == {
                "entity_type": "creator",
                "value": "E.S Monster",
                "model_count": 2,
                "artwork_url": None,
            }

            unknown = client.put(
                "/api/admin/metadata/artwork",
                data={"entity_type": "creator", "value": "Unknown"},
                files={"image": ("creator.png", _png(), "image/png")},
            )
            assert unknown.status_code == 404

            invalid = client.put(
                "/api/admin/metadata/artwork",
                data={"entity_type": "creator", "value": "E.S Monster"},
                files={"image": ("creator.txt", b"not an image", "text/plain")},
            )
            assert invalid.status_code == 422

            uploaded = client.put(
                "/api/admin/metadata/artwork",
                data={"entity_type": "creator", "value": "e.s monster"},
                files={"image": ("creator.png", _png(), "image/png")},
            )
            assert uploaded.status_code == 200
            assert uploaded.json()["value"] == "E.S Monster"
            assert uploaded.json()["width"] == 1600
            assert uploaded.json()["height"] == 800
            artwork_url = uploaded.json()["artwork_url"]

            artwork = client.get(artwork_url)
            assert artwork.status_code == 200
            assert artwork.headers["content-type"] == "image/webp"
            assert artwork.headers["etag"]
            assert Image.open(BytesIO(artwork.content)).format == "WEBP"

            refreshed = client.get("/api/admin/metadata").json()
            refreshed_creator = next(
                item
                for item in refreshed
                if item["entity_type"] == "creator"
            )
            assert refreshed_creator["artwork_url"] == artwork_url

            deleted = client.delete(
                "/api/admin/metadata/artwork",
                params={"entity_type": "creator", "value": "E.S Monster"},
            )
            assert deleted.status_code == 204
            assert client.get(artwork_url).status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_metadata_artwork_is_scoped_to_visible_model_sources() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with sessions() as session:
            source_a = LibrarySource(name="A", root_path="/a", directory_pattern="{model}")
            source_b = LibrarySource(name="B", root_path="/b", directory_pattern="{model}")
            session.add_all([source_a, source_b])
            session.flush()
            session.add_all([
                LibraryModel(library_source_id=source_a.id, relative_path="A", name="A", creator="Only A", franchise="Shared", status="available"),
                LibraryModel(library_source_id=source_b.id, relative_path="B", name="B", creator="Only B", franchise="Shared", status="available"),
            ])
            artworks = [
                MetadataArtwork(entity_type="creator", entity_value="Only A", entity_key="only a", content=b"a", content_type="image/webp", width=1, height=1, etag="a" * 64),
                MetadataArtwork(entity_type="creator", entity_value="Only B", entity_key="only b", content=b"b", content_type="image/webp", width=1, height=1, etag="b" * 64),
                MetadataArtwork(entity_type="franchise", entity_value="Shared", entity_key="shared", content=b"s", content_type="image/webp", width=1, height=1, etag="c" * 64),
            ]
            a_only = User(username="A", normalized_username="a", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=False, is_active=True)
            all_sources = User(username="All", normalized_username="all", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=True, is_active=True)
            no_grant = User(username="None", normalized_username="none", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=False, is_active=True)
            session.add_all([*artworks, a_only, all_sources, no_grant])
            session.flush()
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_a.id))
            session.commit()
        with TestClient(app) as client:
            app.dependency_overrides[get_current_user] = lambda: a_only
            assert client.get(f"/api/metadata/artwork/{artworks[0].id}").status_code == 200
            shared = client.get(f"/api/metadata/artwork/{artworks[2].id}")
            assert shared.status_code == 200
            hidden = client.get(f"/api/metadata/artwork/{artworks[1].id}")
            assert hidden.status_code == 404
            assert hidden.content != artworks[1].content and "etag" not in hidden.headers
            app.dependency_overrides[get_current_user] = lambda: no_grant
            assert client.get(f"/api/metadata/artwork/{artworks[0].id}").status_code == 404
            app.dependency_overrides[get_current_user] = lambda: all_sources
            assert client.get(f"/api/metadata/artwork/{artworks[1].id}").status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
