from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_existing_folder_images_survive_archive_image_cache_migration(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "archive-image-cache-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260802_20")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO library_sources ("
                    "name, root_path, directory_pattern, model_pattern, "
                    "archive_formats, image_formats, is_active, scan_enabled) "
                    "VALUES ('Archive images', '/models/archive-images', '{model}', NULL, "
                    "'[\"7z\"]', '[\"jpg\"]', 1, 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO library_models ("
                    "library_source_id, relative_path, name, status) VALUES ("
                    "1, 'Cammy', 'Cammy', 'available')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO model_images ("
                    "model_id, filename, relative_path, format, size_bytes, modified_ns, "
                    "is_primary, is_available, thumbnail_status) VALUES ("
                    "1, 'cover.jpg', 'Cammy/cover.jpg', 'jpg', 123, 456, 1, 1, 'ready')"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT filename, storage_kind, archive_id, archive_entry_path, cache_key "
                    "FROM model_images WHERE id = 1"
                )
            ).one()
        engine.dispose()

        assert migrated == ("cover.jpg", "source", None, None, None)
    finally:
        get_settings.cache_clear()
