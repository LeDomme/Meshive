from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.passwords import hash_password
from meshive.auth.permissions import CATALOGUE_SHARE_LINKS_MANAGE_OWN, CATALOGUE_VIEW
from meshive.auth.rate_limit import catalogue_share_link_limiter, login_limiter, recovery_limiter
from meshive.auth.sessions import utc_now
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission
from meshive.models.catalogue_share_link import CatalogueShareLink
from meshive.models.user import User

PASSWORD = "correct horse battery staple"


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


def add_user(session: Session, permissions: set[str]) -> User:
    role = Role(name="Link role", normalized_name="link role")
    role.permissions = [RolePermission(permission_key=key) for key in permissions]
    user = User(
        username="Reader",
        normalized_username="reader",
        password_hash=hash_password(PASSWORD),
        role="user",
        role_definition=role,
        all_sources=True,
        is_active=True,
    )
    session.add_all([role, user])
    session.flush()
    return user


def login(client: TestClient) -> None:
    assert (
        client.post(
            "/api/auth/login", json={"username": "Reader", "password": PASSWORD}
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
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 404


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
        assert client.get(f"/api/share/catalogue/{token}/models").status_code == 404
        created = create_link(client)
        assert (
            client.delete(f"/api/account/catalogue-share-links/{created['id']}").status_code == 204
        )
        assert client.get(f"/api/share/catalogue/{created['token']}/models").status_code == 404
