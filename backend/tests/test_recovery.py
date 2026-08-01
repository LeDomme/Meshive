from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.action_tokens import PASSWORD_RESET, hash_action_token
from meshive.auth.passwords import hash_password
from meshive.auth.rate_limit import login_limiter, recovery_limiter, setup_limiter
from meshive.auth.sessions import utc_now
from meshive.config import Settings, get_settings
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.user import User
from meshive.models.user_token import UserActionToken


def recovery_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "public_url": "https://meshive.example",
        "smtp_host": "smtp.example",
        "smtp_port": 465,
        "smtp_username": "meshive@example.com",
        "smtp_password": "mailbox-password",
        "smtp_from": "meshive@example.com",
        "smtp_security": "ssl",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@contextmanager
def recovery_test_client(
    settings: Settings | None = None,
) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    login_limiter.reset()
    recovery_limiter.reset()
    setup_limiter.reset()
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

    app.dependency_overrides[get_session] = override_session
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client, test_session
    finally:
        login_limiter.reset()
        recovery_limiter.reset()
        setup_limiter.reset()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_recovery_user(
    session_factory: sessionmaker,
    *,
    email: str | None = None,
    verified: bool = False,
) -> User:
    with session_factory() as session:
        user = User(
            username="Viewer",
            normalized_username="viewer",
            email=email,
            normalized_email=email.casefold() if email else None,
            email_verified_at=utc_now() if verified else None,
            password_hash=hash_password("a sufficiently long password"),
            role="user",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "username": "Viewer",
            "password": "a sufficiently long password",
        },
    )
    assert response.status_code == 200


def test_recovery_status_requires_complete_email_configuration() -> None:
    with recovery_test_client(Settings(_env_file=None)) as (client, _sessions):
        assert client.get("/api/auth/password-recovery/status").json() == {
            "enabled": False
        }

    with recovery_test_client(recovery_settings()) as (client, _sessions):
        assert client.get("/api/auth/password-recovery/status").json() == {
            "enabled": True
        }


def test_user_can_verify_recovery_email(monkeypatch) -> None:
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "meshive.api.recovery.send_email_verification",
        lambda _settings, email, token: delivered.append((email, token)),
    )
    with recovery_test_client(recovery_settings()) as (client, sessions):
        add_recovery_user(sessions)
        login(client)

        wrong_password = client.post(
            "/api/auth/email",
            json={
                "email": "viewer@example.com",
                "current_password": "wrong password",
            },
        )
        assert wrong_password.status_code == 400

        changed = client.post(
            "/api/auth/email",
            json={
                "email": "Viewer@Example.com",
                "current_password": "a sufficiently long password",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["email"] == "Viewer@example.com"
        assert changed.json()["email_verified"] is False
        assert len(delivered) == 1

        verified = client.post(
            "/api/auth/email/verify", json={"token": delivered[0][1]}
        )
        assert verified.status_code == 200
        assert client.get("/api/auth/me").json()["email_verified"] is True
        assert client.post(
            "/api/auth/email/verify", json={"token": delivered[0][1]}
        ).status_code == 400


def test_password_recovery_is_neutral_and_reset_revokes_sessions(monkeypatch) -> None:
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "meshive.api.recovery.send_password_reset_email",
        lambda _settings, email, token: delivered.append((email, token)),
    )
    with recovery_test_client(recovery_settings()) as (client, sessions):
        add_recovery_user(
            sessions, email="viewer@example.com", verified=True
        )
        login(client)

        unknown = client.post(
            "/api/auth/password-recovery/request",
            json={"identifier": "missing@example.com"},
        )
        known = client.post(
            "/api/auth/password-recovery/request",
            json={"identifier": "viewer@example.com"},
        )
        assert unknown.status_code == 202
        assert known.status_code == 202
        assert unknown.json() == known.json()
        assert len(delivered) == 1
        raw_token = delivered[0][1]
        with sessions() as session:
            stored = session.scalar(
                select(UserActionToken).where(
                    UserActionToken.purpose == PASSWORD_RESET
                )
            )
            assert stored is not None
            assert stored.token_hash != raw_token

        reset = client.post(
            "/api/auth/password-recovery/reset",
            json={
                "token": raw_token,
                "new_password": "a completely different password",
            },
        )
        assert reset.status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        assert client.post(
            "/api/auth/password-recovery/reset",
            json={
                "token": raw_token,
                "new_password": "another completely new password",
            },
        ).status_code == 400
        assert client.post(
            "/api/auth/login",
            json={
                "username": "Viewer",
                "password": "a sufficiently long password",
            },
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={
                "username": "Viewer",
                "password": "a completely different password",
            },
        ).status_code == 200


def test_unverified_email_cannot_receive_password_reset(monkeypatch) -> None:
    delivered: list[str] = []
    monkeypatch.setattr(
        "meshive.api.recovery.send_password_reset_email",
        lambda _settings, _email, token: delivered.append(token),
    )
    with recovery_test_client(recovery_settings()) as (client, sessions):
        add_recovery_user(
            sessions, email="viewer@example.com", verified=False
        )

        by_username = client.post(
            "/api/auth/password-recovery/request",
            json={"identifier": "Viewer"},
        )
        by_email = client.post(
            "/api/auth/password-recovery/request",
            json={"identifier": "viewer@example.com"},
        )

        assert by_username.status_code == 202
        assert by_email.status_code == 202
        assert by_username.json() == by_email.json()
        assert delivered == []


def test_expired_password_reset_token_is_rejected() -> None:
    with recovery_test_client(recovery_settings()) as (client, sessions):
        user = add_recovery_user(
            sessions, email="viewer@example.com", verified=True
        )
        with sessions() as session:
            session.add(
                UserActionToken(
                    token_hash=hash_action_token("expired-token-value-1234567890123456"),
                    user_id=user.id,
                    purpose=PASSWORD_RESET,
                    expires_at=utc_now() - timedelta(minutes=1),
                )
            )
            session.commit()

        response = client.post(
            "/api/auth/password-recovery/reset",
            json={
                "token": "expired-token-value-1234567890123456",
                "new_password": "a completely different password",
            },
        )
        assert response.status_code == 400


def test_password_recovery_requests_are_rate_limited() -> None:
    settings = recovery_settings(
        auth_rate_limit_attempts=2,
        auth_rate_limit_window_seconds=60,
    )
    with recovery_test_client(settings) as (client, _sessions):
        payload = {"identifier": "missing@example.com"}
        assert client.post(
            "/api/auth/password-recovery/request", json=payload
        ).status_code == 202
        assert client.post(
            "/api/auth/password-recovery/request", json=payload
        ).status_code == 202
        blocked = client.post(
            "/api/auth/password-recovery/request", json=payload
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
