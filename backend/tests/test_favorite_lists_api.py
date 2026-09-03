from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from meshive.auth.dependencies import get_current_user
from meshive.database import Base, create_database_engine, get_session
from meshive.main import app
from meshive.models.authorization import UserLibrarySource
from meshive.models.catalog import LibraryModel, ModelImage
from meshive.models.favorite import FavoriteListItem
from meshive.models.library_source import LibrarySource
from meshive.models.metadata import MetadataArtwork
from meshive.models.tag import ModelTag, Tag
from meshive.models.user import User
from meshive.repositories.roles import get_system_role_for_legacy_role


@contextmanager
def favorite_client(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'favorites.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    current_user = {"id": 1}

    with sessions() as session:
        session.add_all(
            [
                User(
                    id=1,
                    username="Owner",
                    normalized_username="owner",
                    password_hash="unused",
                    role="user",
                    is_active=True,
                ),
                User(
                    id=2,
                    username="Other",
                    normalized_username="other",
                    password_hash="unused",
                    role="user",
                    is_active=True,
                ),
            ]
        )
        session.commit()

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=current_user["id"],
        role_id=None,
        role_definition=SimpleNamespace(is_superuser=True),
        all_sources=True,
    )
    try:
        with TestClient(app) as client:
            yield client, sessions, current_user
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_favorite_lists_are_private_and_resolve_catalogue_targets(tmp_path) -> None:
    with favorite_client(tmp_path) as (client, sessions, current_user):
        with sessions() as session:
            source = LibrarySource(
                name="Favorites",
                root_path="/models/favorites",
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
                relative_path="Marvel/Psylocke Chibi",
                name="Psylocke",
                variant="Chibi",
                creator="E.S Monster",
                franchise="Marvel",
                series="X-Men",
                collection="Paid",
                status="available",
            )
            tag = Tag(name="Bust", color="#00aaff")
            session.add_all([model, tag])
            session.flush()
            session.add(ModelTag(model_id=model.id, tag_id=tag.id))
            session.add(
                MetadataArtwork(
                    entity_type="creator",
                    entity_value="E.S Monster",
                    entity_key="e.s monster",
                    content=b"webp",
                    content_type="image/webp",
                    width=32,
                    height=32,
                    etag="a" * 64,
                )
            )
            session.add(
                ModelImage(
                    model_id=model.id,
                    filename="psylocke.jpg",
                    relative_path="Marvel/Psylocke Chibi/psylocke.jpg",
                    format="jpg",
                    size_bytes=1234,
                    modified_ns=1,
                    is_primary=True,
                    is_available=True,
                    thumbnail_key="favorites/psylocke.webp",
                    thumbnail_status="ready",
                )
            )
            session.commit()
            model_id = model.id
            tag_id = tag.id
            image_id = session.scalar(
                select(ModelImage.id).where(ModelImage.model_id == model_id)
            )

        created = client.post("/api/favorite-lists", json={"name": "Print next"})
        assert created.status_code == 201
        favorite_list_id = created.json()["id"]
        assert created.json()["item_count"] == 0

        duplicate_name = client.post(
            "/api/favorite-lists", json={"name": "  PRINT NEXT  "}
        )
        assert duplicate_name.status_code == 409

        current_user["id"] = 2
        assert client.get(f"/api/favorite-lists/{favorite_list_id}").status_code == 404
        assert client.post(
            f"/api/favorite-lists/{favorite_list_id}/items",
            json={"entity_type": "model", "model_id": model_id},
        ).status_code == 404
        current_user["id"] = 1

        payloads = [
            {"entity_type": "model", "model_id": model_id},
            {"entity_type": "creator", "value": "e.s monster"},
            {"entity_type": "franchise", "value": "Marvel"},
            {"entity_type": "series", "value": "X-Men"},
            {"entity_type": "collection", "value": "Paid"},
            {"entity_type": "tag", "tag_id": tag_id},
        ]
        for payload in payloads:
            response = client.post(
                f"/api/favorite-lists/{favorite_list_id}/items", json=payload
            )
            assert response.status_code == 201

        memberships = client.get(
            "/api/favorite-lists/model-memberships",
            params=[("model_ids", model_id)],
        )
        assert memberships.status_code == 200
        membership_data = memberships.json()
        assert membership_data[0]["model_id"] == model_id
        assert [
            (item["id"], item["name"]) for item in membership_data[0]["lists"]
        ] == [(favorite_list_id, "Print next")]
        assert isinstance(membership_data[0]["lists"][0]["item_id"], int)
        current_user["id"] = 2
        assert client.get(
            "/api/favorite-lists/model-memberships",
            params=[("model_ids", model_id)],
        ).json() == []
        current_user["id"] = 1

        duplicate_item = client.post(
            f"/api/favorite-lists/{favorite_list_id}/items",
            json={"entity_type": "model", "model_id": model_id},
        )
        assert duplicate_item.status_code == 409

        detail = client.get(f"/api/favorite-lists/{favorite_list_id}")
        assert detail.status_code == 200
        assert detail.json()["item_count"] == 6
        items = {item["entity_type"]: item for item in detail.json()["items"]}
        assert items["model"]["label"] == "Psylocke — Chibi"
        assert items["model"]["url"] == f"/models/{model_id}"
        assert items["model"]["model_id"] == model_id
        assert items["model"]["thumbnail_url"] == (
            f"/api/models/{model_id}/thumbnail?v={image_id}"
        )
        assert items["model"]["variant"] == "Chibi"
        assert items["model"]["creator"] == "E.S Monster"
        assert items["creator"]["label"] == "E.S Monster"
        assert items["creator"]["url"] == "/?creator=E.S+Monster"
        assert items["creator"]["artwork_url"].startswith("/api/metadata/artwork/")
        assert items["franchise"]["artwork_url"] is None
        assert items["tag"]["url"] == f"/?tag_id={tag_id}"
        assert all(item["is_available"] for item in items.values())

        renamed = client.put(
            f"/api/favorite-lists/{favorite_list_id}", json={"name": "Later"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Later"
        assert client.get("/api/favorite-lists").json()[0]["item_count"] == 6

        with sessions() as session:
            session.delete(session.get(LibraryModel, model_id))
            session.delete(session.get(Tag, tag_id))
            session.commit()

        unavailable = client.get(f"/api/favorite-lists/{favorite_list_id}").json()
        assert unavailable["item_count"] == 1
        assert len(unavailable["items"]) == 1
        assert unavailable["items"][0]["entity_type"] == "model"
        assert unavailable["items"][0]["url"] is None

        deleted = client.delete(f"/api/favorite-lists/{favorite_list_id}")
        assert deleted.status_code == 204
        assert client.get("/api/favorite-lists").json() == []


def test_favorite_item_payload_requires_matching_reference(tmp_path) -> None:
    with favorite_client(tmp_path) as (client, _sessions, _current_user):
        favorite = client.post("/api/favorite-lists", json={"name": "Test"})
        favorite_list_id = favorite.json()["id"]

        missing_model = client.post(
            f"/api/favorite-lists/{favorite_list_id}/items",
            json={"entity_type": "model"},
        )
        assert missing_model.status_code == 422

        empty_value = client.post(
            f"/api/favorite-lists/{favorite_list_id}/items",
            json={"entity_type": "creator", "value": "   "},
        )
        assert empty_value.status_code == 422

        mixed_reference = client.post(
            f"/api/favorite-lists/{favorite_list_id}/items",
            json={"entity_type": "model", "model_id": 1, "value": "Psylocke"},
        )
        assert mixed_reference.status_code == 422


def test_model_favorites_hide_revoked_sources_without_deleting_them(tmp_path) -> None:
    with favorite_client(tmp_path) as (client, sessions, _current_user):
        with sessions() as session:
            source_a = LibrarySource(name="A", root_path="/models/a", directory_pattern="{model}")
            source_b = LibrarySource(name="B", root_path="/models/b", directory_pattern="{model}")
            session.add_all([source_a, source_b])
            session.flush()
            model_a = LibraryModel(library_source_id=source_a.id, relative_path="A", name="A", status="available")
            model_b = LibraryModel(library_source_id=source_b.id, relative_path="B", name="B", status="available")
            a_only = User(username="A only", normalized_username="a only", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=False, is_active=True)
            all_sources = User(username="All", normalized_username="all", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=True, is_active=True)
            no_grant = User(username="None", normalized_username="none", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=False, is_active=True)
            session.add_all([model_a, model_b, a_only, all_sources, no_grant])
            session.flush()
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_a.id))
            session.commit()

        app.dependency_overrides[get_current_user] = lambda: a_only
        favorite_id = client.post("/api/favorite-lists", json={"name": "Models"}).json()["id"]
        assert client.post(f"/api/favorite-lists/{favorite_id}/items", json={"entity_type": "model", "model_id": model_a.id}).status_code == 201
        assert client.post(f"/api/favorite-lists/{favorite_id}/items", json={"entity_type": "model", "model_id": model_b.id}).status_code == 404
        assert client.get(f"/api/favorite-lists/{favorite_id}").json()["item_count"] == 1
        with sessions() as session:
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_b.id))
            session.commit()
        added_b = client.post(f"/api/favorite-lists/{favorite_id}/items", json={"entity_type": "model", "model_id": model_b.id})
        assert added_b.status_code == 201
        b_item_id = added_b.json()["id"]
        memberships = client.get("/api/favorite-lists/model-memberships", params=[("model_ids", model_a.id), ("model_ids", model_b.id)]).json()
        assert [entry["model_id"] for entry in memberships] == [model_a.id, model_b.id]
        with sessions() as session:
            session.delete(session.get(UserLibrarySource, (a_only.id, source_b.id)))
            session.commit()
        assert client.get(f"/api/favorite-lists/{favorite_id}").json()["item_count"] == 1
        assert client.get("/api/favorite-lists/model-memberships", params=[("model_ids", model_a.id), ("model_ids", model_b.id)]).json() == [memberships[0]]
        assert client.delete(f"/api/favorite-lists/{favorite_id}/items/{b_item_id}").status_code == 404
        app.dependency_overrides[get_current_user] = lambda: no_grant
        no_grant_list = client.post("/api/favorite-lists", json={"name": "Empty"}).json()["id"]
        assert client.get(f"/api/favorite-lists/{no_grant_list}").json()["items"] == []
        app.dependency_overrides[get_current_user] = lambda: all_sources
        all_list = client.post("/api/favorite-lists", json={"name": "All models"}).json()["id"]
        for model in (model_a, model_b):
            assert client.post(f"/api/favorite-lists/{all_list}/items", json={"entity_type": "model", "model_id": model.id}).status_code == 201
        assert client.get(f"/api/favorite-lists/{all_list}").json()["item_count"] == 2
        app.dependency_overrides[get_current_user] = lambda: a_only
        with sessions() as session:
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_b.id))
            session.commit()
        assert client.get(f"/api/favorite-lists/{favorite_id}").json()["item_count"] == 2


def test_non_model_favorites_are_scoped_by_visible_sources(tmp_path) -> None:
    with favorite_client(tmp_path) as (client, sessions, _current_user):
        with sessions() as session:
            source_a = LibrarySource(name="A", root_path="/models/a", directory_pattern="{model}")
            source_b = LibrarySource(name="B", root_path="/models/b", directory_pattern="{model}")
            session.add_all([source_a, source_b])
            session.flush()
            model_a = LibraryModel(
                library_source_id=source_a.id,
                relative_path="A",
                name="A",
                creator="Creator A",
                franchise="Franchise A",
                series="Shared series",
                collection="Collection A",
                status="available",
            )
            model_b = LibraryModel(
                library_source_id=source_b.id,
                relative_path="B",
                name="B",
                creator="Creator B",
                franchise="Franchise B",
                series="Shared series",
                collection="Collection B",
                status="available",
            )
            tag_a, tag_b, tag_shared = Tag(name="Tag A"), Tag(name="Tag B"), Tag(name="Tag shared")
            a_only = User(
                username="A only",
                normalized_username="a only",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=False,
                is_active=True,
            )
            no_grant = User(
                username="No grant",
                normalized_username="no grant",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=False,
                is_active=True,
            )
            all_sources = User(
                username="All sources",
                normalized_username="all sources",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=True,
                is_active=True,
            )
            session.add_all([
                model_a, model_b, tag_a, tag_b, tag_shared, a_only, no_grant, all_sources,
            ])
            session.flush()
            session.add_all([
                UserLibrarySource(user_id=a_only.id, library_source_id=source_a.id),
                ModelTag(model_id=model_a.id, tag_id=tag_a.id),
                ModelTag(model_id=model_a.id, tag_id=tag_shared.id),
                ModelTag(model_id=model_b.id, tag_id=tag_b.id),
                ModelTag(model_id=model_b.id, tag_id=tag_shared.id),
                MetadataArtwork(
                    entity_type="creator",
                    entity_value="Creator B",
                    entity_key="creator b",
                    content=b"webp",
                    content_type="image/webp",
                    width=1,
                    height=1,
                    etag="b" * 64,
                ),
            ])
            session.commit()

        app.dependency_overrides[get_current_user] = lambda: a_only
        favorite_id = client.post("/api/favorite-lists", json={"name": "Scoped"}).json()["id"]
        for payload in (
            {"entity_type": "tag", "tag_id": tag_b.id},
            {"entity_type": "creator", "value": "Creator B"},
            {"entity_type": "franchise", "value": "Franchise B"},
            {"entity_type": "collection", "value": "Collection B"},
        ):
            assert client.post(f"/api/favorite-lists/{favorite_id}/items", json=payload).status_code == 404
        for payload in (
            {"entity_type": "tag", "tag_id": tag_a.id},
            {"entity_type": "tag", "tag_id": tag_shared.id},
            {"entity_type": "creator", "value": "Creator A"},
            {"entity_type": "series", "value": "Shared series"},
        ):
            assert client.post(f"/api/favorite-lists/{favorite_id}/items", json=payload).status_code == 201

        with sessions() as session:
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_b.id))
            session.commit()
        hidden_tag_item = client.post(
            f"/api/favorite-lists/{favorite_id}/items",
            json={"entity_type": "tag", "tag_id": tag_b.id},
        ).json()["id"]
        hidden_creator_item = client.post(
            f"/api/favorite-lists/{favorite_id}/items",
            json={"entity_type": "creator", "value": "Creator B"},
        ).json()["id"]
        assert client.post(
            f"/api/favorite-lists/{favorite_id}/items",
            json={"entity_type": "franchise", "value": "Franchise B"},
        ).status_code == 201

        with sessions() as session:
            session.delete(session.get(UserLibrarySource, (a_only.id, source_b.id)))
            session.commit()
        hidden = client.get(f"/api/favorite-lists/{favorite_id}").json()
        assert hidden["item_count"] == 4
        assert {item["label"] for item in hidden["items"]} == {
            "Tag A", "Tag shared", "Creator A", "Shared series"
        }
        assert all(item["artwork_url"] is None for item in hidden["items"])
        assert all("Creator+B" not in (item["url"] or "") for item in hidden["items"])
        assert client.get("/api/favorite-lists").json()[0]["item_count"] == 4
        assert client.delete(
            f"/api/favorite-lists/{favorite_id}/items/{hidden_creator_item}"
        ).status_code == 404
        with sessions() as session:
            assert session.get(FavoriteListItem, hidden_creator_item) is not None
            assert session.get(FavoriteListItem, hidden_tag_item) is not None

        with sessions() as session:
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_b.id))
            session.commit()
        restored = client.get(f"/api/favorite-lists/{favorite_id}").json()
        assert restored["item_count"] == 7
        restored_creator = next(item for item in restored["items"] if item["id"] == hidden_creator_item)
        assert restored_creator["label"] == "Creator B"
        assert restored_creator["artwork_url"].startswith("/api/metadata/artwork/")
        assert client.delete(
            f"/api/favorite-lists/{favorite_id}/items/{hidden_creator_item}"
        ).status_code == 204

        app.dependency_overrides[get_current_user] = lambda: no_grant
        empty_id = client.post("/api/favorite-lists", json={"name": "Empty"}).json()["id"]
        assert client.post(
            f"/api/favorite-lists/{empty_id}/items",
            json={"entity_type": "tag", "tag_id": tag_a.id},
        ).status_code == 404
        assert client.get(f"/api/favorite-lists/{empty_id}").json()["items"] == []

        app.dependency_overrides[get_current_user] = lambda: all_sources
        all_id = client.post("/api/favorite-lists", json={"name": "All"}).json()["id"]
        assert client.post(
            f"/api/favorite-lists/{all_id}/items",
            json={"entity_type": "tag", "tag_id": tag_b.id},
        ).status_code == 201
