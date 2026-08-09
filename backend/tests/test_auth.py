from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.passwords import hash_password
from meshive.auth.rate_limit import login_limiter, recovery_limiter, setup_limiter
from meshive.auth.sessions import hash_session_token
from meshive.auth.user_agents import parse_user_agent
from meshive.config import Settings, get_settings
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.user import User


@contextmanager
def authenticated_test_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
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


def add_user(
    session_factory: sessionmaker,
    *,
    username: str,
    password: str,
    role: str,
) -> User:
    with session_factory() as session:
        user = User(
            username=username,
            normalized_username=username.casefold(),
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_admin_can_login_access_admin_route_and_logout() -> None:
    with authenticated_test_client() as (client, sessions):
        add_user(
            sessions,
            username="Admin",
            password="correct horse battery staple",
            role="admin",
        )

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        )
        assert login.status_code == 200
        assert login.json()["role"] == "admin"
        assert "meshive_session" in login.cookies

        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/admin/library-sources").status_code == 200

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401


def test_login_rejects_wrong_password() -> None:
    with authenticated_test_client() as (client, sessions):
        add_user(
            sessions,
            username="Admin",
            password="correct horse battery staple",
            role="admin",
        )

        response = client.post(
            "/api/auth/login",
            json={"username": "Admin", "password": "not the password"},
        )

        assert response.status_code == 401
        assert "meshive_session" not in response.cookies


def test_login_rate_limits_repeated_failures() -> None:
    test_settings = Settings(
        environment="production",
        auth_rate_limit_attempts=2,
        auth_rate_limit_window_seconds=60,
    )
    with authenticated_test_client() as (client, sessions):
        app.dependency_overrides[get_settings] = lambda: test_settings
        add_user(
            sessions,
            username="Rate Limited User",
            password="correct horse battery staple",
            role="user",
        )
        payload = {"username": "Rate Limited User", "password": "wrong password"}

        assert client.post("/api/auth/login", json=payload).status_code == 401
        assert client.post("/api/auth/login", json=payload).status_code == 401
        blocked = client.post("/api/auth/login", json=payload)

        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1


def test_normal_user_cannot_access_admin_routes() -> None:
    with authenticated_test_client() as (client, sessions):
        add_user(
            sessions,
            username="Viewer",
            password="a sufficiently long password",
            role="user",
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "Viewer", "password": "a sufficiently long password"},
            ).status_code
            == 200
        )

        assert client.get("/api/admin/library-sources").status_code == 403


def test_last_active_admin_cannot_be_demoted() -> None:
    with authenticated_test_client() as (client, sessions):
        admin = add_user(
            sessions,
            username="Admin",
            password="correct horse battery staple",
            role="admin",
        )
        client.post(
            "/api/auth/login",
            json={"username": "Admin", "password": "correct horse battery staple"},
        )

        response = client.put(
            f"/api/admin/users/{admin.id}",
            json={
                "username": "Admin",
                "role": "user",
                "is_active": True,
                "password": None,
            },
        )

        assert response.status_code == 409


def test_admin_can_reset_password_and_delete_another_user() -> None:
    with authenticated_test_client() as (client, sessions):
        admin = add_user(
            sessions,
            username="Admin",
            password="correct horse battery staple",
            role="admin",
        )
        viewer = add_user(
            sessions,
            username="Viewer",
            password="a sufficiently long password",
            role="user",
        )
        client.post(
            "/api/auth/login",
            json={"username": "Admin", "password": "correct horse battery staple"},
        )

        updated = client.put(
            f"/api/admin/users/{viewer.id}",
            json={
                "username": "Viewer",
                "role": "user",
                "is_active": True,
                "must_change_password": True,
                "password": "a replacement password",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["must_change_password"] is True

        client.post("/api/auth/logout")
        viewer_login = client.post(
            "/api/auth/login",
            json={"username": "Viewer", "password": "a replacement password"},
        )
        assert viewer_login.status_code == 200
        assert viewer_login.json()["must_change_password"] is True
        client.post("/api/auth/logout")
        client.post(
            "/api/auth/login",
            json={"username": "Admin", "password": "correct horse battery staple"},
        )

        assert client.delete(f"/api/admin/users/{admin.id}").status_code == 409
        assert client.delete(f"/api/admin/users/{viewer.id}").status_code == 204
        with sessions() as session:
            assert session.get(User, viewer.id) is None


def test_initial_password_must_be_changed_before_catalogue_access() -> None:
    with authenticated_test_client() as (client, sessions):
        user = add_user(
            sessions,
            username="New User",
            password="temporary password 123",
            role="user",
        )
        with sessions() as session:
            stored = session.get(User, user.id)
            stored.must_change_password = True
            session.commit()

        login = client.post(
            "/api/auth/login",
            json={"username": "New User", "password": "temporary password 123"},
        )
        assert login.status_code == 200
        assert login.json()["must_change_password"] is True
        assert client.get("/api/models").status_code == 403

        changed = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "temporary password 123",
                "new_password": "a completely new password",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["must_change_password"] is False
        assert client.get("/api/models").status_code == 200


def test_password_change_revokes_other_sessions() -> None:
    with authenticated_test_client() as (first_client, sessions):
        add_user(
            sessions,
            username="Viewer",
            password="a sufficiently long password",
            role="user",
        )
        login_payload = {
            "username": "Viewer",
            "password": "a sufficiently long password",
        }
        assert first_client.post("/api/auth/login", json=login_payload).status_code == 200

        second_client = TestClient(app, base_url="https://testserver")
        try:
            assert second_client.post("/api/auth/login", json=login_payload).status_code == 200
            assert second_client.get("/api/auth/me").status_code == 200

            changed = first_client.post(
                "/api/auth/change-password",
                json={
                    "current_password": "a sufficiently long password",
                    "new_password": "a completely different password",
                },
            )

            assert changed.status_code == 200
            assert first_client.get("/api/auth/me").status_code == 200
            assert second_client.get("/api/auth/me").status_code == 401
        finally:
            second_client.close()


def test_session_list_describes_clients_and_revokes_one_session() -> None:
    firefox_windows = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    )
    chrome_android = (
        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
        "Chrome/127.0.0.0 Mobile Safari/537.36"
    )
    with authenticated_test_client() as (first_client, sessions):
        add_user(
            sessions,
            username="Viewer",
            password="a sufficiently long password",
            role="user",
        )
        login_payload = {
            "username": "Viewer",
            "password": "a sufficiently long password",
        }
        first_login = first_client.post(
            "/api/auth/login",
            json=login_payload,
            headers={"User-Agent": firefox_windows},
        )
        assert first_login.status_code == 200

        second_client = TestClient(app, base_url="https://testserver")
        try:
            second_login = second_client.post(
                "/api/auth/login",
                json=login_payload,
                headers={"User-Agent": chrome_android},
            )
            assert second_login.status_code == 200

            response = first_client.get("/api/auth/sessions")
            assert response.status_code == 200
            listed = response.json()
            assert len(listed) == 2
            current = next(item for item in listed if item["is_current"])
            other = next(item for item in listed if not item["is_current"])
            assert current["browser"] == "Mozilla Firefox"
            assert current["operating_system"] == "Windows"
            assert current["device_type"] == "Desktop"
            assert other["browser"] == "Google Chrome"
            assert other["operating_system"] == "Android"
            assert other["device_type"] == "Mobile"
            raw_token = first_client.cookies.get("meshive_session")
            assert raw_token is not None
            assert current["id"] != hash_session_token(raw_token)

            revoked = first_client.delete(f"/api/auth/sessions/{other['id']}")
            assert revoked.status_code == 204
            assert first_client.get("/api/auth/me").status_code == 200
            assert second_client.get("/api/auth/me").status_code == 401
        finally:
            second_client.close()


def test_sign_out_all_other_sessions_preserves_current_session() -> None:
    with authenticated_test_client() as (first_client, sessions):
        add_user(
            sessions,
            username="Viewer",
            password="a sufficiently long password",
            role="user",
        )
        login_payload = {
            "username": "Viewer",
            "password": "a sufficiently long password",
        }
        assert first_client.post("/api/auth/login", json=login_payload).status_code == 200

        second_client = TestClient(app, base_url="https://testserver")
        third_client = TestClient(app, base_url="https://testserver")
        try:
            assert second_client.post("/api/auth/login", json=login_payload).status_code == 200
            assert third_client.post("/api/auth/login", json=login_payload).status_code == 200

            revoked = first_client.delete("/api/auth/sessions/others")
            assert revoked.status_code == 200
            assert revoked.json() == {"revoked_count": 2}
            assert first_client.get("/api/auth/me").status_code == 200
            assert second_client.get("/api/auth/me").status_code == 401
            assert third_client.get("/api/auth/me").status_code == 401
        finally:
            second_client.close()
            third_client.close()


def test_user_cannot_revoke_another_users_session() -> None:
    with authenticated_test_client() as (first_client, sessions):
        add_user(
            sessions,
            username="First Viewer",
            password="first sufficiently long password",
            role="user",
        )
        add_user(
            sessions,
            username="Second Viewer",
            password="second sufficiently long password",
            role="user",
        )
        assert first_client.post(
            "/api/auth/login",
            json={
                "username": "First Viewer",
                "password": "first sufficiently long password",
            },
        ).status_code == 200

        second_client = TestClient(app, base_url="https://testserver")
        try:
            assert second_client.post(
                "/api/auth/login",
                json={
                    "username": "Second Viewer",
                    "password": "second sufficiently long password",
                },
            ).status_code == 200
            foreign_session = second_client.get("/api/auth/sessions").json()[0]

            response = first_client.delete(
                f"/api/auth/sessions/{foreign_session['id']}"
            )
            assert response.status_code == 404
            assert second_client.get("/api/auth/me").status_code == 200
        finally:
            second_client.close()


def test_current_session_can_sign_itself_out() -> None:
    with authenticated_test_client() as (client, sessions):
        add_user(
            sessions,
            username="Viewer",
            password="a sufficiently long password",
            role="user",
        )
        assert client.post(
            "/api/auth/login",
            json={
                "username": "Viewer",
                "password": "a sufficiently long password",
            },
        ).status_code == 200
        current = client.get("/api/auth/sessions").json()[0]

        response = client.delete(f"/api/auth/sessions/{current['id']}")

        assert response.status_code == 204
        assert client.get("/api/auth/me").status_code == 401


def test_user_agent_parser_does_not_require_raw_client_data() -> None:
    assert parse_user_agent(None).browser is None
    unknown = parse_user_agent("custom-client")
    assert unknown.browser is None
    assert unknown.operating_system is None
    assert unknown.device_type is None


def test_first_run_setup_creates_and_signs_in_initial_admin() -> None:
    test_settings = Settings(
        environment="production",
        setup_token="a-long-random-setup-token",
    )
    with authenticated_test_client() as (client, _sessions):
        app.dependency_overrides[get_settings] = lambda: test_settings

        status_response = client.get("/api/setup/status")
        assert status_response.status_code == 200
        assert status_response.json() == {"required": True, "enabled": True}

        created = client.post(
            "/api/setup",
            json={
                "setup_token": "a-long-random-setup-token",
                "username": "First Admin",
                "password": "correct horse battery staple",
            },
        )
        assert created.status_code == 201
        assert created.json()["role"] == "admin"
        assert client.get("/api/auth/me").status_code == 200

        assert client.get("/api/setup/status").json()["required"] is False
        second_attempt = client.post(
            "/api/setup",
            json={
                "setup_token": "a-long-random-setup-token",
                "username": "Second Admin",
                "password": "another sufficiently long password",
            },
        )
        assert second_attempt.status_code == 409


def test_first_run_setup_rejects_invalid_token() -> None:
    test_settings = Settings(environment="production", setup_token="correct-token")
    with authenticated_test_client() as (client, _sessions):
        app.dependency_overrides[get_settings] = lambda: test_settings

        response = client.post(
            "/api/setup",
            json={
                "setup_token": "wrong-token",
                "username": "Admin",
                "password": "correct horse battery staple",
            },
        )

        assert response.status_code == 403


def test_first_run_setup_rate_limits_invalid_tokens() -> None:
    test_settings = Settings(
        environment="production",
        setup_token="correct-token",
        auth_rate_limit_attempts=2,
        auth_rate_limit_window_seconds=60,
    )
    with authenticated_test_client() as (client, _sessions):
        app.dependency_overrides[get_settings] = lambda: test_settings
        payload = {
            "setup_token": "wrong-token",
            "username": "Admin",
            "password": "correct horse battery staple",
        }

        assert client.post("/api/setup", json=payload).status_code == 403
        assert client.post("/api/setup", json=payload).status_code == 403
        blocked = client.post("/api/setup", json=payload)

        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1


def test_catalogue_filter_preferences_are_saved_per_user() -> None:
    with authenticated_test_client() as (client, _sessions):
        add_user(
            _sessions,
            username="admin",
            password="correct horse battery staple",
            role="admin",
        )
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200

        assert client.get("/api/auth/catalogue-preferences").json() == {
            "filter_order": []
        }

        saved = client.put(
            "/api/auth/catalogue-preferences",
            json={"filter_order": ["creator", "model", "sort"]},
        )
        assert saved.status_code == 200
        assert saved.json() == {
            "filter_order": ["creator", "model", "sort"]
        }

        assert client.get("/api/auth/catalogue-preferences").json() == {
            "filter_order": ["creator", "model", "sort"]
        }

        duplicate = client.put(
            "/api/auth/catalogue-preferences",
            json={"filter_order": ["model", "model"]},
        )
        assert duplicate.status_code == 422
