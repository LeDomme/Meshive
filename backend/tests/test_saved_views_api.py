from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.user import User


@contextmanager
def saved_views_client(
    user_id: int = 1,
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add_all(
            [
                User(
                    id=1,
                    username="One",
                    normalized_username="one",
                    password_hash="unused",
                    role="admin",
                    all_sources=True,
                ),
                User(
                    id=2,
                    username="Two",
                    normalized_username="two",
                    password_hash="unused",
                    role="admin",
                    all_sources=True,
                ),
            ]
        )
        session.commit()

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id,
        all_sources=True,
        role_id=None,
        role_definition=SimpleNamespace(is_superuser=True),
    )
    client = TestClient(app)
    try:
        yield client, sessions
    finally:
        client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def saved_state(**overrides: str) -> dict[str, str]:
    return {
        "search": "",
        "model": "",
        "creator": "",
        "creator_profile_id": "",
        "franchise": "",
        "series": "",
        "collection": "",
        "source_id": "",
        "tag_id": "",
        "status": "",
        "sort": "name_asc",
        **overrides,
    }


def test_saved_views_create_load_rename_delete_and_persist() -> None:
    with saved_views_client() as (client, _sessions):
        created = client.post(
            "/api/saved-views",
            json={
                "name": "Printed figures",
                "state": saved_state(
                    search="dragon",
                    franchise="Fantasy",
                    source_id="7",
                    tag_id="4",
                    sort="files_oldest",
                ),
            },
        )
        assert created.status_code == 201
        view = created.json()
        assert view["state"]["source_id"] == "7"
        assert view["state"]["sort"] == "files_oldest"

        listed = client.get("/api/saved-views")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [view["id"]]

        loaded = client.get(f"/api/saved-views/{view['id']}")
        assert loaded.status_code == 200
        assert loaded.json()["state"] == view["state"]

        renamed = client.put(f"/api/saved-views/{view['id']}", json={"name": "Fantasy prints"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Fantasy prints"

        deleted = client.delete(f"/api/saved-views/{view['id']}")
        assert deleted.status_code == 204
        assert client.get("/api/saved-views").json() == []


def test_saved_views_are_isolated_by_user() -> None:
    with saved_views_client() as (client, _sessions):
        created = client.post(
            "/api/saved-views",
            json={"name": "Private", "state": saved_state(source_id="3")},
        )
        assert created.status_code == 201
        view_id = created.json()["id"]

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=2,
            all_sources=True,
            role_id=None,
            role_definition=SimpleNamespace(is_superuser=True),
        )
        assert client.get("/api/saved-views").json() == []
        assert client.get(f"/api/saved-views/{view_id}").status_code == 404
        assert (
            client.put(f"/api/saved-views/{view_id}", json={"name": "Changed"}).status_code == 404
        )
        assert client.delete(f"/api/saved-views/{view_id}").status_code == 404


def test_saved_views_require_catalogue_permission() -> None:
    with saved_views_client() as (client, _sessions):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1,
            all_sources=True,
            role_id=None,
            role_definition=SimpleNamespace(is_superuser=False, permission_keys=frozenset()),
        )
        assert client.get("/api/saved-views").status_code == 403
