from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from meshive.config import get_settings


def test_automatic_tag_migration_preserves_search_triggers(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "automatic-tag-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260802_19")
        command.upgrade(config, "head")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        model_tag_columns = {column["name"] for column in inspector.get_columns("model_tags")}
        scan_columns = {column["name"] for column in inspector.get_columns("scan_runs")}
        with engine.connect() as connection:
            triggers = set(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'trigger' AND name LIKE 'model_tags_%'"
                    )
                ).scalars()
            )
        table_names = set(inspector.get_table_names())
        engine.dispose()

        assert "is_automatic" in model_tag_columns
        assert {
            "automatic_tag_matches",
            "automatic_tags_added",
            "automatic_tags_removed",
        } <= scan_columns
        assert {"automatic_tag_rules", "automatic_tag_matches"} <= table_names
        assert {"model_tags_ai", "model_tags_au", "model_tags_ad"} <= triggers
    finally:
        get_settings.cache_clear()
