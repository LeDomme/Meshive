from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.config import get_settings


def test_creator_profile_migration_backfills_legacy_creator_data(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "creator-profiles.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260911_39")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO library_sources "
                    "(name, root_path, directory_pattern, archive_formats, image_formats, "
                    "is_active, scan_enabled) VALUES "
                    "('Source', '/models/source', '{model}', '[\"7z\"]', '[\"jpg\"]', 1, 1)"
                )
            )
            source_id = connection.scalar(text("SELECT id FROM library_sources"))
            connection.execute(
                text(
                    "INSERT INTO library_models "
                    "(library_source_id, relative_path, name, creator, status) VALUES "
                    "(:source_id, 'one', 'One', 'Aoae', 'available'), "
                    "(:source_id, 'two', 'Two', 'aoae', 'available'), "
                    "(:source_id, 'three', 'Three', 'Ａｏａｅ', 'available'), "
                    "(:source_id, 'four', 'Four', 'Some Creator', 'available'), "
                    "(:source_id, 'five', 'Five', '', 'available')"
                ),
                {"source_id": source_id},
            )
            connection.execute(
                text(
                    "INSERT INTO creator_metadata_links (creator_name, kind, label, url) VALUES "
                    "('Aoae', 'website', 'Website', 'https://example.com/aoae'), "
                    "('Link Only', 'website', 'Website', 'https://example.com/link-only')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO metadata_artwork "
                    "(entity_type, entity_value, entity_key, content, content_type, width, height, etag) "
                    "VALUES ('creator', 'Artwork Only', 'artwork only', X'00', 'image/webp', 1, 1, 'artwork')"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            profiles = connection.execute(
                text(
                    "SELECT display_name, normalized_name, artwork_id FROM creator_profiles "
                    "ORDER BY normalized_name"
                )
            ).all()
            aliases = connection.execute(
                text(
                    "SELECT creator_profiles.display_name, creator_aliases.alias "
                    "FROM creator_aliases JOIN creator_profiles "
                    "ON creator_profiles.id = creator_aliases.creator_profile_id "
                    "ORDER BY creator_profiles.normalized_name"
                )
            ).all()
            models = connection.execute(
                text(
                    "SELECT creator, creator_profile_id FROM library_models ORDER BY id"
                )
            ).all()
            links = connection.execute(
                text(
                    "SELECT creator_name, creator_profile_id, url FROM creator_metadata_links ORDER BY id"
                )
            ).all()
            artwork = connection.execute(
                text(
                    "SELECT entity_value, content FROM metadata_artwork WHERE entity_type = 'creator'"
                )
            ).one()
            foreign_keys = connection.execute(text("PRAGMA foreign_key_list(library_models)")).all()
        engine.dispose()

        assert [(name, normalized) for name, normalized, _ in profiles] == [
            ("Aoae", "aoae"),
            ("Artwork Only", "artwork only"),
            ("Link Only", "link only"),
            ("Some Creator", "some creator"),
        ]
        assert aliases == [
            ("Aoae", "Aoae"),
            ("Artwork Only", "Artwork Only"),
            ("Link Only", "Link Only"),
            ("Some Creator", "Some Creator"),
        ]
        assert models[0][1] == models[1][1] == models[2][1]
        assert models[3][1] is not None
        assert models[4] == ("", None)
        assert all(profile_id is not None for _, profile_id, _ in links)
        assert links[0][2] == "https://example.com/aoae"
        assert artwork == ("Artwork Only", b"\x00")
        assert next(artwork_id for _, normalized, artwork_id in profiles if normalized == "artwork only")
        assert any(
            foreign_key[2] == "creator_profiles" and foreign_key[6].upper() == "SET NULL"
            for foreign_key in foreign_keys
        )

        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(
                text("DELETE FROM metadata_artwork WHERE entity_type = 'creator'")
            )
            profile_after_artwork_delete = connection.execute(
                text(
                    "SELECT artwork_id FROM creator_profiles "
                    "WHERE normalized_name = 'artwork only'"
                )
            ).scalar_one()
        engine.dispose()
        assert profile_after_artwork_delete is None
    finally:
        get_settings.cache_clear()


def test_creator_profile_migration_rejects_unexpected_creator_artwork_key(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "creator-profiles-conflict.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260911_39")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO metadata_artwork "
                    "(entity_type, entity_value, entity_key, content, content_type, width, height, etag) "
                    "VALUES ('creator', 'Artist', 'not-the-normalized-key', X'00', 'image/webp', 1, 1, 'bad')"
                )
            )
        engine.dispose()

        try:
            command.upgrade(config, "head")
        except RuntimeError as error:
            assert "unexpected normalized key" in str(error)
        else:
            raise AssertionError("The migration must reject unexpected creator artwork keys")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'creator_profiles'"
                )
            ) == 0
        engine.dispose()
    finally:
        get_settings.cache_clear()
