from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_existing_users_survive_password_recovery_migration(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "password-recovery-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260802_15")
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
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT username, email, normalized_email, email_verified_at "
                    "FROM users"
                )
            ).one()
            token_table = connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'user_action_tokens'"
                )
            ).scalar_one()
        engine.dispose()

        assert migrated == ("Viewer", None, None, None)
        assert token_table == "user_action_tokens"
    finally:
        get_settings.cache_clear()
