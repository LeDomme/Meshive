from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_existing_models_survive_variant_search_migration(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "model-variant-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260918_46")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO library_sources ("
                    "name, root_path, directory_pattern, model_pattern, "
                    "archive_formats, image_formats, is_active, scan_enabled) "
                    "VALUES ('Variants', '/models/variants', '{model}', NULL, "
                    "'[\"7z\"]', '[\"jpg\"]', 1, 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO library_models ("
                    "library_source_id, relative_path, name, creator, franchise, "
                    "series, collection, status) VALUES ("
                    "1, 'Marvel/Psylocke Chibi', 'Psylocke', 'E.S Monster', "
                    "'Marvel', 'X-Men', NULL, 'available')"
                )
            )
            connection.execute(
                text("UPDATE library_models SET variant = ' Halloween Town ' WHERE id = 1")
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            migrated = connection.execute(
                text(
                    "SELECT value, normalized_value, position FROM model_variants "
                    "WHERE model_id = 1"
                )
            ).one()
            search_columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(model_search)"))
            }
            connection.execute(
                text(
                "INSERT INTO model_variants (model_id, value, normalized_value, position) "
                "VALUES (1, 'Chibi version', 'chibi version', 0)"
                )
            )
            search_match = connection.execute(
                text(
                    "SELECT model_id FROM model_search "
                    "WHERE model_search MATCH 'Chibi'"
                )
            ).scalar_one()
        engine.dispose()

        assert migrated == (" Halloween Town ", "halloween town", 0)
        assert "variant" in search_columns
        assert search_match == 1
    finally:
        get_settings.cache_clear()
