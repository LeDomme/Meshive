"""Add the FTS5 model search index.

Revision ID: 20260730_10
Revises: 20260730_09
"""
from collections.abc import Sequence
from alembic import op

revision: str = "20260730_10"
down_revision: str | Sequence[str] | None = "20260730_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE model_search USING fts5(
            model_id UNINDEXED, name, creator, franchise, series, collection, tags,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        INSERT INTO model_search(model_id, name, creator, franchise, series, collection, tags)
        SELECT m.id, m.name, COALESCE(m.creator, ''), COALESCE(m.franchise, ''),
               COALESCE(m.series, ''), COALESCE(m.collection, ''),
               COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt
                         JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
        FROM library_models m
        """
    )
    _create_refresh_trigger("library_models_ai", "AFTER INSERT ON library_models", "NEW.id")
    _create_refresh_trigger("library_models_au", "AFTER UPDATE ON library_models", "NEW.id")
    op.execute(
        """
        CREATE TRIGGER library_models_ad AFTER DELETE ON library_models BEGIN
          DELETE FROM model_search WHERE model_id = OLD.id;
        END
        """
    )
    _create_refresh_trigger("model_tags_ai", "AFTER INSERT ON model_tags", "NEW.model_id")
    _create_refresh_trigger("model_tags_au", "AFTER UPDATE ON model_tags", "NEW.model_id")
    _create_refresh_trigger("model_tags_ad", "AFTER DELETE ON model_tags", "OLD.model_id")
    op.execute(
        """
        CREATE TRIGGER tags_au AFTER UPDATE OF name ON tags BEGIN
          DELETE FROM model_search
          WHERE model_id IN (SELECT model_id FROM model_tags WHERE tag_id = NEW.id);
          INSERT INTO model_search(model_id, name, creator, franchise, series, collection, tags)
          SELECT m.id, m.name, COALESCE(m.creator, ''), COALESCE(m.franchise, ''),
                 COALESCE(m.series, ''), COALESCE(m.collection, ''),
                 COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt
                           JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
          FROM library_models m
          WHERE m.id IN (SELECT model_id FROM model_tags WHERE tag_id = NEW.id);
        END
        """
    )


def _create_refresh_trigger(name: str, event: str, model_id: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER {name} {event} BEGIN
          DELETE FROM model_search WHERE model_id = {model_id};
          INSERT INTO model_search(model_id, name, creator, franchise, series, collection, tags)
          SELECT m.id, m.name, COALESCE(m.creator, ''), COALESCE(m.franchise, ''),
                 COALESCE(m.series, ''), COALESCE(m.collection, ''),
                 COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt
                           JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
          FROM library_models m WHERE m.id = {model_id};
        END
        """
    )


def downgrade() -> None:
    for trigger in (
        "tags_au", "model_tags_ad", "model_tags_au", "model_tags_ai",
        "library_models_ad", "library_models_au", "library_models_ai",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS model_search")
