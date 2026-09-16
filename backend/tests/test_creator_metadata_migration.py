from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_creator_metadata_migration_backfills_stable_profile_references(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'creator-metadata.sqlite3').as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260916_40")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (username, normalized_username, password_hash, role, is_active) "
                    "VALUES ('user', 'user', 'unused', 'user', 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO favorite_lists (user_id, name, normalized_name) VALUES (1, 'List', 'list')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO creator_profiles (display_name, normalized_name, is_active) "
                    "VALUES ('Aoae', 'aoae', 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO creator_metadata_links (creator_name, kind, label, url) "
                    "VALUES ('AOAE', 'website', 'Website', 'https://example.test')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO metadata_artwork "
                    "(entity_type, entity_value, entity_key, content, content_type, width, height, etag) "
                    "VALUES ('creator', 'Aoae', 'aoae', X'00', 'image/webp', 1, 1, 'etag')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO favorite_list_items (favorite_list_id, entity_type, entity_key, label) "
                    "VALUES (1, 'creator', 'aoae', 'Aoae')"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            profile_id = connection.scalar(text("SELECT id FROM creator_profiles WHERE normalized_name = 'aoae'"))
            assert connection.scalar(text("SELECT creator_profile_id FROM creator_metadata_links")) == profile_id
            assert connection.scalar(text("SELECT artwork_id FROM creator_profiles WHERE id = :id"), {"id": profile_id})
            assert connection.scalar(text("SELECT creator_profile_id FROM favorite_list_items")) == profile_id
            assert connection.scalar(text("SELECT entity_key FROM favorite_list_items")) == f"creator-profile:{profile_id}"
        engine.dispose()

        command.downgrade(config, "20260916_40")
    finally:
        get_settings.cache_clear()
