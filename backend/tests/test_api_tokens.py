from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.passwords import hash_password
from meshive.auth.permissions import (
    ALL_PERMISSION_KEYS,
    API_TOKENS_MANAGE_OWN,
    CATALOGUE_VIEW,
    SYSTEM_ROLE_DEFINITIONS,
)
from meshive.auth.rate_limit import login_limiter, recovery_limiter, setup_limiter
from meshive.auth.sessions import utc_now
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.api_token import ApiToken
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.catalog import LibraryModel, ModelVariant
from meshive.models.library_source import LibrarySource
from meshive.models.user import User

PASSWORD = "correct horse battery staple"


@contextmanager
def api_token_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    login_limiter.reset()
    recovery_limiter.reset()
    setup_limiter.reset()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE model_search USING fts5("
            "model_id UNINDEXED, name, variant, creator, franchise, series, "
            "collection, tags)"
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
        login_limiter.reset()
        recovery_limiter.reset()
        setup_limiter.reset()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_role(session: Session, name: str, permissions: set[str]) -> Role:
    role = Role(name=name, normalized_name=name.casefold())
    role.permissions = [RolePermission(permission_key=key) for key in permissions]
    session.add(role)
    session.flush()
    return role


def add_user(
    session: Session,
    username: str,
    role: Role,
    *,
    all_sources: bool = True,
    must_change_password: bool = False,
) -> User:
    user = User(
        username=username,
        normalized_username=username.casefold(),
        password_hash=hash_password(PASSWORD),
        role="user",
        role_definition=role,
        all_sources=all_sources,
        is_active=True,
        must_change_password=must_change_password,
    )
    session.add(user)
    session.flush()
    return user


def login(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200


def create_token(client: TestClient, *, seconds: int | None = 3600) -> dict[str, object]:
    response = client.post(
        "/api/account/tokens",
        json={
            "name": "Automation reader",
            "expires_in_seconds": seconds,
            "current_password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_api_token_permission_is_administrator_only_by_default() -> None:
    assert API_TOKENS_MANAGE_OWN in ALL_PERMISSION_KEYS
    permissions = {role.name: role.permission_keys for role in SYSTEM_ROLE_DEFINITIONS}
    assert API_TOKENS_MANAGE_OWN in permissions["Administrator"]
    for role_name in ("Viewer", "Member", "Curator", "Operator"):
        assert API_TOKENS_MANAGE_OWN not in permissions[role_name]


def test_token_management_requires_permission_password_and_valid_ttl() -> None:
    with api_token_client() as (client, sessions):
        with sessions() as session:
            no_tokens = add_role(session, "Catalogue only", {CATALOGUE_VIEW})
            allowed = add_role(session, "API reader", {API_TOKENS_MANAGE_OWN})
            add_user(session, "NoTokens", no_tokens)
            add_user(session, "Allowed", allowed)
            add_user(session, "Forced", allowed, must_change_password=True)
            session.commit()

        login(client, "NoTokens")
        assert client.get("/api/account/tokens").status_code == 403
        assert client.post(
            "/api/account/tokens",
            json={"name": "Denied", "expires_in_seconds": 300, "current_password": PASSWORD},
        ).status_code == 403
        assert client.delete("/api/account/tokens/1").status_code == 403
        client.post("/api/auth/logout")

        login(client, "Allowed")
        wrong_password = client.post(
            "/api/account/tokens",
            json={"name": "Wrong", "expires_in_seconds": 300, "current_password": "wrong"},
        )
        assert wrong_password.status_code == 400
        for invalid_seconds in (59, 365 * 24 * 60 * 60 + 1):
            assert client.post(
                "/api/account/tokens",
                json={
                    "name": "Invalid",
                    "expires_in_seconds": invalid_seconds,
                    "current_password": PASSWORD,
                },
            ).status_code == 422

        before = utc_now()
        created = create_token(client, seconds=300)
        assert str(created["token"]).startswith("msh_pat_")
        assert created["name"] == "Automation reader"
        with sessions() as session:
            stored = session.scalar(select(ApiToken))
            assert stored is not None
            assert stored.token_hash != created["token"]
            assert created["token"] not in stored.token_hash
            assert before + timedelta(minutes=4, seconds=59) <= stored.expires_at
            assert stored.expires_at <= before + timedelta(minutes=5, seconds=2)
            events = list(session.scalars(select(AuditEvent)))
            assert [event.action for event in events] == ["api_token.created"]
            assert created["token"] not in str(events[0].details)

        listed = client.get("/api/account/tokens")
        assert listed.status_code == 200
        assert "token" not in listed.json()[0]
        assert "token_hash" not in listed.json()[0]
        assert listed.json()[0]["token_prefix"].endswith("...")

        never = create_token(client, seconds=None)
        assert never["expires_at"] is None

        client.post("/api/auth/logout")
        login(client, "Forced")
        assert client.get("/api/account/tokens").status_code == 403
        assert client.post(
            "/api/account/tokens",
            json={"name": "Forced", "expires_in_seconds": 300, "current_password": PASSWORD},
        ).status_code == 403


def test_bearer_token_uses_current_permissions_sources_and_user_state() -> None:
    with api_token_client() as (client, sessions):
        with sessions() as session:
            role = add_role(
                session,
                "API reader",
                {CATALOGUE_VIEW, API_TOKENS_MANAGE_OWN},
            )
            token_only_role = add_role(
                session,
                "Token only",
                {API_TOKENS_MANAGE_OWN},
            )
            user = add_user(session, "Reader", role, all_sources=False)
            visible_source = LibrarySource(
                name="Visible",
                root_path="/models/visible",
                directory_pattern="{model}",
            )
            hidden_source = LibrarySource(
                name="Hidden",
                root_path="/models/hidden",
                directory_pattern="{model}",
            )
            session.add_all([visible_source, hidden_source])
            session.flush()
            visible_model = LibraryModel(
                library_source_id=visible_source.id,
                relative_path="Magik",
                name="Magik",
                creator="Neko Figurines",
                franchise="Marvel",
                series="X-Men",
                status="available",
                variants=[
                    ModelVariant(value="Tokon", normalized_value="tokon", position=0)
                ],
            )
            hidden_model = LibraryModel(
                library_source_id=hidden_source.id,
                relative_path="Hidden",
                name="Hidden model",
                status="available",
            )
            session.add_all([visible_model, hidden_model])
            session.flush()
            session.add(
                UserLibrarySource(user_id=user.id, library_source_id=visible_source.id)
            )
            session.execute(
                text(
                    "INSERT INTO model_search "
                    "(model_id, name, variant, creator, franchise, series, collection, tags) "
                    "VALUES (:id, :name, :variant, :creator, :franchise, :series, '', '')"
                ),
                {
                    "id": visible_model.id,
                    "name": visible_model.name,
                    "creator": visible_model.creator,
                    "franchise": visible_model.franchise,
                    "series": visible_model.series,
                    "variant": "Tokon",
                },
            )
            session.commit()
            user_id = user.id
            role_id = role.id
            token_only_role_id = token_only_role.id
            visible_source_id = visible_source.id
            visible_model_id = visible_model.id

        login(client, "Reader")
        plaintext = str(create_token(client, seconds=900)["token"])
        client.cookies.clear()
        headers = {"Authorization": f"Bearer {plaintext}"}
        assert client.get(
            "/api/models",
            headers={"Authorization": "Bearer msh_pat_unknown"},
        ).status_code == 401

        for query in (
            "search=Magik",
            "model=Magik",
            "creator=Neko%20Figurines",
            "franchise=Marvel",
            "series=X-Men",
            "variant=Tokon",
        ):
            response = client.get(f"/api/models?{query}", headers=headers)
            assert response.status_code == 200
            assert [item["name"] for item in response.json()["items"]] == ["Magik"]

        assert client.get(
            f"/api/models/{visible_model_id}/archives/download-all", headers=headers
        ).status_code == 403
        for path in (
            "/api/auth/me",
            "/api/auth/sessions",
            "/api/auth/catalogue-preferences",
            "/api/account/tokens",
        ):
            assert client.get(path, headers=headers).status_code == 401
        assert client.post(
            "/api/account/tokens",
            headers=headers,
            json={"name": "Nested", "expires_in_seconds": 300, "current_password": PASSWORD},
        ).status_code == 401
        assert client.delete("/api/account/tokens/1", headers=headers).status_code == 401
        assert client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": PASSWORD, "new_password": f"new {PASSWORD}"},
        ).status_code == 401
        assert client.post(
            "/api/auth/email",
            headers=headers,
            json={"email": "reader@example.invalid", "current_password": PASSWORD},
        ).status_code == 401

        with sessions() as session:
            token = session.scalar(select(ApiToken))
            assert token is not None and token.last_used_at is not None
            first_used_at = token.last_used_at
        assert client.get("/api/models", headers=headers).status_code == 200
        with sessions() as session:
            assert session.scalar(select(ApiToken)).last_used_at == first_used_at

        with sessions() as session:
            grant = session.get(UserLibrarySource, (user_id, visible_source_id))
            session.delete(grant)
            session.commit()
        assert client.get("/api/models", headers=headers).json()["total"] == 0

        with sessions() as session:
            session.add(
                UserLibrarySource(user_id=user_id, library_source_id=visible_source_id)
            )
            user = session.get(User, user_id)
            user.role_id = token_only_role_id
            session.commit()
        assert client.get("/api/models", headers=headers).status_code == 403

        with sessions() as session:
            user = session.get(User, user_id)
            user.role_id = role_id
            permission = session.get(RolePermission, (role_id, CATALOGUE_VIEW))
            session.delete(permission)
            session.commit()
        assert client.get("/api/models", headers=headers).status_code == 403

        with sessions() as session:
            session.add(RolePermission(role_id=role_id, permission_key=CATALOGUE_VIEW))
            user = session.get(User, user_id)
            user.must_change_password = True
            session.commit()
        assert client.get("/api/models", headers=headers).status_code == 401

        with sessions() as session:
            user = session.get(User, user_id)
            user.must_change_password = False
            user.is_active = False
            session.commit()
        assert client.get("/api/models", headers=headers).status_code == 401

        with sessions() as session:
            user = session.get(User, user_id)
            user.is_active = True
            token = session.scalar(select(ApiToken))
            token.expires_at = utc_now() - timedelta(seconds=1)
            session.commit()
        assert client.get("/api/models", headers=headers).status_code == 401
        login(client, "Reader")
        assert client.get("/api/account/tokens").json()[0]["status"] == "expired"


def test_owner_can_revoke_but_cannot_revoke_another_users_token() -> None:
    with api_token_client() as (client, sessions):
        with sessions() as session:
            role = add_role(session, "Token users", {API_TOKENS_MANAGE_OWN})
            add_user(session, "First", role)
            add_user(session, "Second", role)
            session.commit()

        login(client, "First")
        first = create_token(client)
        client.post("/api/auth/logout")
        login(client, "Second")
        second = create_token(client)
        assert client.delete(f"/api/account/tokens/{first['id']}").status_code == 404
        client.post("/api/auth/logout")

        login(client, "First")
        assert client.delete(f"/api/account/tokens/{first['id']}").status_code == 204
        client.cookies.clear()
        assert client.get(
            "/api/models",
            headers={"Authorization": f"Bearer {first['token']}"},
        ).status_code == 401
        with sessions() as session:
            assert session.get(ApiToken, second["id"]) is not None
            revoked = session.scalar(
                select(AuditEvent).where(AuditEvent.action == "api_token.revoked")
            )
            assert revoked is not None
            assert first["token"] not in str(revoked.details)
