from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_existing_sessions_survive_client_metadata_migration(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "session-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260801_14")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(username, normalized_username, password_hash, role, "
                    "is_active, must_change_password) "
                    "VALUES ('Viewer', 'viewer', 'unused', 'user', 1, 0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO user_sessions "
                    "(token_hash, user_id, expires_at) "
                    "VALUES ('existing-token-hash', 1, "
                    "datetime('now', '+1 day'))"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT token_hash, browser, operating_system, device_type "
                    "FROM user_sessions"
                )
            ).one()
        engine.dispose()

        assert migrated == ("existing-token-hash", None, None, None)
    finally:
        get_settings.cache_clear()
