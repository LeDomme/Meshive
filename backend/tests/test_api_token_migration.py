from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_api_token_migration_preserves_auth_data_and_grants_administrator(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "api-token-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    command.upgrade(config, "20261015_48")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        administrator_id = connection.execute(
            text("SELECT id FROM roles WHERE normalized_name = 'administrator'")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO users ("
                "username, normalized_username, password_hash, role, role_id, "
                "all_sources, is_active, must_change_password"
                ") VALUES ("
                "'Existing', 'existing', 'hash', 'admin', :role_id, 1, 1, 0"
                ")"
            ),
            {"role_id": administrator_id},
        )
        user_id = connection.execute(
            text("SELECT id FROM users WHERE normalized_username = 'existing'")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO user_sessions ("
                "token_hash, user_id, expires_at, last_used_at"
                ") VALUES ("
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                ":user_id, '2099-01-01 00:00:00', '2026-10-16 00:00:00'"
                ")"
            ),
            {"user_id": user_id},
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars()
        )
        assert "api_tokens" in tables
        assert "catalogue_share_links" in tables
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM user_sessions")).scalar_one() == 1
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM role_permissions rp "
                    "JOIN roles r ON r.id = rp.role_id "
                    "WHERE r.normalized_name = 'administrator' "
                    "AND rp.permission_key = 'api_tokens.manage_own'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM role_permissions rp "
                    "JOIN roles r ON r.id = rp.role_id "
                    "WHERE r.normalized_name = 'administrator' "
                    "AND rp.permission_key = 'catalogue_share_links.manage_own'"
                )
            ).scalar_one()
            == 1
        )

    engine.dispose()
    get_settings.cache_clear()
