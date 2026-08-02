from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from meshive.config import get_settings


def test_existing_users_survive_favorite_list_migration(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "favorite-list-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260802_17")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users ("
                    "username, normalized_username, password_hash, role, "
                    "is_active, must_change_password) VALUES ("
                    "'Viewer', 'viewer', 'unused', 'user', 1, 0)"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        inspector = inspect(engine)
        with engine.connect() as connection:
            username = connection.execute(
                text("SELECT username FROM users WHERE normalized_username = 'viewer'")
            ).scalar_one()
        table_names = inspector.get_table_names()
        engine.dispose()

        assert username == "Viewer"
        assert "favorite_lists" in table_names
        assert "favorite_list_items" in table_names
        assert "metadata_artwork" in table_names
    finally:
        get_settings.cache_clear()
