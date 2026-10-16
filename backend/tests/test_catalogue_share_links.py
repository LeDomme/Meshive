import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.passwords import hash_password
from meshive.auth.permissions import CATALOGUE_SHARE_LINKS_MANAGE_OWN, CATALOGUE_VIEW
from meshive.auth.rate_limit import (
    RequestRateLimiter,
    catalogue_share_link_limiter,
    login_limiter,
    recovery_limiter,
)
from meshive.auth.sessions import utc_now
from meshive.database import Base, get_session
from meshive.logging_utils import CatalogueShareAccessLogRedactionFilter
from meshive.main import app
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.catalog import LibraryModel
from meshive.models.catalogue_share_link import CatalogueShareLink
from meshive.models.library_source import LibrarySource
from meshive.models.user import User

PASSWORD = "correct horse battery staple"


def test_catalogue_share_access_log_redacts_capability_secret() -> None:
    from uvicorn.logging import AccessFormatter

    secret = "msh_share_do-not-log-this-capability-secret"
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(CatalogueShareAccessLogRedactionFilter())
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s'))
    logger = logging.getLogger("test.catalogue-share-access-log")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            '%s - "%s %s HTTP/%s" %s',
            "127.0.0.1",
            "GET",
            f"/api/share/catalogue/{secret}/models?search=Example",
            "1.1",
            "200",
        )
    finally:
        logger.handlers = []
    assert secret not in stream.getvalue()
    assert "/api/share/catalogue/<redacted>/models?search=Example" in stream.getvalue()


@contextmanager
def client_context() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    login_limiter.reset()
    recovery_limiter.reset()
    catalogue_share_link_limiter.reset()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE model_search USING fts5(model_id UNINDEXED, name, variant, creator, franchise, series, collection, tags)"
        )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app, base_url="https://testserver")
    try:
        yield client, sessions
    finally:
        client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_user(
    session: Session,
    permissions: set[str],
    *,
    username: str = "Reader",
    all_sources: bool = True,
) -> User:
    role = Role(name=f"{username} role", normalized_name=f"{username} role".casefold())
    role.permissions = [RolePermission(permission_key=key) for key in permissions]
    user = User(
        username=username,
        normalized_username=username.casefold(),
        password_hash=hash_password(PASSWORD),
        role="user",
        role_definition=role,
        all_sources=all_sources,
        is_active=True,
    )
    session.add_all([role, user])
    session.flush()
    return user


def login(client: TestClient, username: str = "Reader") -> None:
    assert (
        client.post(
            "/api/auth/login", json={"username": username, "password": PASSWORD}
        ).status_code
        == 200
    )


def create_link(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/account/catalogue-share-links",
        json={"name": "External lookup", "expires_in_seconds": 900, "current_password": PASSWORD},
    )
    assert response.status_code == 201
    return response.json()


def add_source_models(session: Session) -> tuple[LibrarySource, LibrarySource]:
    source_a = LibrarySource(name="Source A", root_path="/models/a", directory_pattern="{model}")
    source_b = LibrarySource(name="Source B", root_path="/models/b", directory_pattern="{model}")
    session.add_all([source_a, source_b])
    session.flush()
    session.add_all(
        [
            LibraryModel(
                library_source_id=source_a.id,
                relative_path="Visible model",
                name="Visible model",
                franchise="Visible franchise",
                status="available",
            ),
            LibraryModel(
                library_source_id=source_b.id,
                relative_path="Hidden model",
                name="Hidden model",
                franchise="Hidden franchise",
                status="available",
            ),
        ]
    )
    return source_a, source_b


def test_management_hashes_secret_and_audits_without_secret() -> None:
    with client_context() as (client, sessions):
        with sessions() as session:
            add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN})
            session.commit()
        login(client)
        created = create_link(client)
        assert str(created["token"]).startswith("msh_share_")
        assert (
            client.post(
                "/api/account/catalogue-share-links",
                json={"name": "Bad", "expires_in_seconds": 59, "current_password": PASSWORD},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/account/catalogue-share-links",
                json={"name": "Bad", "expires_in_seconds": 3601, "current_password": PASSWORD},
            ).status_code
            == 422
        )
        listed = client.get("/api/account/catalogue-share-links")
        assert (
            listed.status_code == 200
            and "token" not in listed.json()[0]
            and "token_hash" not in listed.json()[0]
        )
        with sessions() as session:
            link = session.scalar(select(CatalogueShareLink))
            assert (
                link
                and link.token_hash != created["token"]
                and str(created["token"]) not in link.token_hash
            )
            event = session.scalar(select(AuditEvent))
            assert (
                event
                and str(created["token"]) not in str(event.details)
                and link.token_hash not in str(event.details)
            )


def test_share_endpoint_inherits_owner_state_and_has_security_headers() -> None:
    with client_context() as (client, sessions):
        with sessions() as session:
            user = add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN})
            session.commit()
        login(client)
        created = create_link(client)
        token = str(created["token"])
        response = client.get(f"/api/share/catalogue/{token}/models")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, no-cache"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert (
            client.get("/api/models", headers={"Authorization": f"Bearer {token}"}).status_code
            == 401
        )
        with sessions() as session:
            user = session.get(User, user.id)
            user.is_active = False
            session.commit()
        unavailable = client.get(f"/api/share/catalogue/{token}/models")
        assert unavailable.status_code == 404
        assert unavailable.headers["cache-control"] == "no-store, no-cache"
        assert unavailable.headers["pragma"] == "no-cache"
        assert unavailable.headers["referrer-policy"] == "no-referrer"


def test_expired_and_revoked_links_are_unusable() -> None:
    with client_context() as (client, sessions):
        with sessions() as session:
            add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN})
            session.commit()
        login(client)
        created = create_link(client)
        token = str(created["token"])
        with sessions() as session:
            link = session.scalar(select(CatalogueShareLink))
            link.expires_at = utc_now() - timedelta(seconds=1)
            session.commit()
        unavailable = client.get(f"/api/share/catalogue/{token}/models")
        assert unavailable.status_code == 404
        assert unavailable.headers["cache-control"] == "no-store, no-cache"
        assert unavailable.headers["pragma"] == "no-cache"
        assert unavailable.headers["referrer-policy"] == "no-referrer"
        created = create_link(client)
        assert (
            client.delete(f"/api/account/catalogue-share-links/{created['id']}").status_code == 204
        )
        assert client.get(f"/api/share/catalogue/{created['token']}/models").status_code == 404


def test_share_link_uses_current_source_scope_for_models_and_filters() -> None:
    with client_context() as (client, sessions):
        with sessions() as session:
            owner = add_user(
                session,
                {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN},
                all_sources=False,
            )
            source_a, source_b = add_source_models(session)
            session.add(UserLibrarySource(user_id=owner.id, library_source_id=source_a.id))
            session.commit()
            owner_id, source_a_id, source_b_id = owner.id, source_a.id, source_b.id

        login(client)
        token = str(create_link(client)["token"])
        models = client.get(f"/api/share/catalogue/{token}/models")
        filters = client.get(f"/api/share/catalogue/{token}/filters")
        assert [item["name"] for item in models.json()["items"]] == ["Visible model"]
        assert [item["name"] for item in filters.json()["sources"]] == ["Source A"]
        assert "Hidden" not in str(filters.json())

        with sessions() as session:
            session.delete(session.get(UserLibrarySource, (owner_id, source_a_id)))
            session.add(UserLibrarySource(user_id=owner_id, library_source_id=source_b_id))
            session.commit()

        updated = client.get(f"/api/share/catalogue/{token}/models")
        assert [item["name"] for item in updated.json()["items"]] == ["Hidden model"]


def test_share_link_uses_current_catalogue_permission_and_password_state() -> None:
    with client_context() as (client, sessions):
        with sessions() as session:
            owner = add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN})
            session.commit()
            owner_id, role_id = owner.id, owner.role_id

        login(client)
        token = str(create_link(client)["token"])
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 200

        with sessions() as session:
            session.delete(session.get(RolePermission, (role_id, CATALOGUE_VIEW)))
            session.commit()
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 403

        with sessions() as session:
            session.add(RolePermission(role_id=role_id, permission_key=CATALOGUE_VIEW))
            session.commit()
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 200

        with sessions() as session:
            session.get(User, owner_id).must_change_password = True
            session.commit()
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 404


def test_share_link_cannot_be_revoked_by_another_user() -> None:
    with client_context() as (client, sessions):
        with sessions() as session:
            add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN}, username="Alice")
            add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN}, username="Bob")
            session.commit()

        login(client, "Bob")
        bob_link = create_link(client)
        assert client.post("/api/auth/logout").status_code == 204
        login(client, "Alice")
        assert (
            client.delete(f"/api/account/catalogue-share-links/{bob_link['id']}").status_code == 404
        )


def test_share_link_rate_limit_and_last_used_tracking() -> None:
    limiter = RequestRateLimiter()
    assert limiter.check_and_record("link", limit=2, window_seconds=60) is None
    assert limiter.check_and_record("link", limit=2, window_seconds=60) is None
    assert limiter.check_and_record("link", limit=2, window_seconds=60) is not None

    with client_context() as (client, sessions):
        with sessions() as session:
            add_user(session, {CATALOGUE_VIEW, CATALOGUE_SHARE_LINKS_MANAGE_OWN})
            session.commit()
        login(client)
        created = create_link(client)
        token, link_id = str(created["token"]), int(created["id"])
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 200
        with sessions() as session:
            first_used_at = session.get(CatalogueShareLink, link_id).last_used_at
        assert first_used_at is not None
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 200
        with sessions() as session:
            assert session.get(CatalogueShareLink, link_id).last_used_at == first_used_at
            session.get(CatalogueShareLink, link_id).last_used_at = utc_now() - timedelta(
                minutes=16
            )
            session.commit()
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 200
        with sessions() as session:
            assert session.get(CatalogueShareLink, link_id).last_used_at > first_used_at
            catalogue_share_link_limiter.reset()
            for _ in range(120):
                assert (
                    catalogue_share_link_limiter.check_and_record(
                        str(link_id), limit=120, window_seconds=60
                    )
                    is None
                )
        limited = client.get(f"/api/share/catalogue/{token}/models")
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1
