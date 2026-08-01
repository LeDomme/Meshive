from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_existing_creator_url_is_migrated_to_website_metadata(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "creator-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260801_13")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO creator_links (creator_name, url) "
                    "VALUES ('Aoae', 'https://example.com/aoae')"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT creator_name, kind, label, url "
                    "FROM creator_metadata_links"
                )
            ).one()
        engine.dispose()

        assert migrated == (
            "Aoae",
            "website",
            "Website",
            "https://example.com/aoae",
        )
    finally:
        get_settings.cache_clear()
