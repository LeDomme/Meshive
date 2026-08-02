from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from meshive.auth.dependencies import get_current_user
from meshive.database import Base, create_database_engine, get_session
from meshive.main import app
from meshive.models.catalog import LibraryModel, ModelImage
from meshive.models.library_source import LibrarySource
from meshive.models.tag import Tag
from meshive.models.user import User


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
        id=current_user["id"]
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
        assert items["model"]["thumbnail_url"] == f"/api/models/{model_id}/thumbnail"
        assert items["model"]["variant"] == "Chibi"
        assert items["model"]["creator"] == "E.S Monster"
        assert items["creator"]["label"] == "E.S Monster"
        assert items["creator"]["url"] == "/?creator=E.S+Monster"
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
        unavailable_items = {
            item["entity_type"]: item for item in unavailable["items"]
        }
        assert unavailable_items["model"]["label"] == "Psylocke — Chibi"
        assert unavailable_items["model"]["url"] is None
        assert unavailable_items["model"]["is_available"] is False
        assert unavailable_items["tag"]["label"] == "Bust"
        assert unavailable_items["tag"]["is_available"] is False

        model_item_id = unavailable_items["model"]["id"]
        removed = client.delete(
            f"/api/favorite-lists/{favorite_list_id}/items/{model_item_id}"
        )
        assert removed.status_code == 204
        assert client.get(f"/api/favorite-lists/{favorite_list_id}").json()[
            "item_count"
        ] == 5

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
