"""Add optional model variants to catalogue metadata and search.

Revision ID: 20260802_17
Revises: 20260802_16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_17"
down_revision: str | Sequence[str] | None = "20260802_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEARCH_TRIGGERS = (
    "tags_au",
    "model_tags_ad",
    "model_tags_au",
    "model_tags_ai",
    "library_models_ad",
    "library_models_au",
    "library_models_ai",
)


def upgrade() -> None:
    with op.batch_alter_table("library_models") as batch:
        batch.add_column(sa.Column("variant", sa.String(length=255), nullable=True))

    _drop_search_index()
    _create_search_index(include_variant=True)


def downgrade() -> None:
    _drop_search_index()
    with op.batch_alter_table("library_models") as batch:
        batch.drop_column("variant")
    _create_search_index(include_variant=False)


def _drop_search_index() -> None:
    for trigger in _SEARCH_TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS model_search")


def _create_search_index(*, include_variant: bool) -> None:
    variant_definition = "variant, " if include_variant else ""
    variant_value = "COALESCE(m.variant, ''), " if include_variant else ""
    op.execute(
        f"""
        CREATE VIRTUAL TABLE model_search USING fts5(
            model_id UNINDEXED, name, {variant_definition}creator, franchise,
            series, collection, tags,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO model_search(
            model_id, name, {variant_definition}creator, franchise, series,
            collection, tags
        )
        SELECT m.id, m.name, {variant_value}COALESCE(m.creator, ''),
               COALESCE(m.franchise, ''), COALESCE(m.series, ''),
               COALESCE(m.collection, ''),
               COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt
                         JOIN tags t ON t.id = mt.tag_id
                         WHERE mt.model_id = m.id), '')
        FROM library_models m
        """
    )
    _create_refresh_trigger(
        "library_models_ai", "AFTER INSERT ON library_models", "NEW.id", include_variant
    )
    _create_refresh_trigger(
        "library_models_au", "AFTER UPDATE ON library_models", "NEW.id", include_variant
    )
    op.execute(
        """
        CREATE TRIGGER library_models_ad AFTER DELETE ON library_models BEGIN
          DELETE FROM model_search WHERE model_id = OLD.id;
        END
        """
    )
    _create_refresh_trigger(
        "model_tags_ai", "AFTER INSERT ON model_tags", "NEW.model_id", include_variant
    )
    _create_refresh_trigger(
        "model_tags_au", "AFTER UPDATE ON model_tags", "NEW.model_id", include_variant
    )
    _create_refresh_trigger(
        "model_tags_ad", "AFTER DELETE ON model_tags", "OLD.model_id", include_variant
    )
    _create_tag_update_trigger(include_variant=include_variant)


def _create_refresh_trigger(
    name: str, event: str, model_id: str, include_variant: bool
) -> None:
    variant_definition = "variant, " if include_variant else ""
    variant_value = "COALESCE(m.variant, ''), " if include_variant else ""
    op.execute(
        f"""
        CREATE TRIGGER {name} {event} BEGIN
          DELETE FROM model_search WHERE model_id = {model_id};
          INSERT INTO model_search(
              model_id, name, {variant_definition}creator, franchise, series,
              collection, tags
          )
          SELECT m.id, m.name, {variant_value}COALESCE(m.creator, ''),
                 COALESCE(m.franchise, ''), COALESCE(m.series, ''),
                 COALESCE(m.collection, ''),
                 COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt
                           JOIN tags t ON t.id = mt.tag_id
                           WHERE mt.model_id = m.id), '')
          FROM library_models m WHERE m.id = {model_id};
        END
        """
    )


def _create_tag_update_trigger(*, include_variant: bool) -> None:
    variant_definition = "variant, " if include_variant else ""
    variant_value = "COALESCE(m.variant, ''), " if include_variant else ""
    op.execute(
        f"""
        CREATE TRIGGER tags_au AFTER UPDATE OF name ON tags BEGIN
          DELETE FROM model_search
          WHERE model_id IN (SELECT model_id FROM model_tags WHERE tag_id = NEW.id);
          INSERT INTO model_search(
              model_id, name, {variant_definition}creator, franchise, series,
              collection, tags
          )
          SELECT m.id, m.name, {variant_value}COALESCE(m.creator, ''),
                 COALESCE(m.franchise, ''), COALESCE(m.series, ''),
                 COALESCE(m.collection, ''),
                 COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt
                           JOIN tags t ON t.id = mt.tag_id
                           WHERE mt.model_id = m.id), '')
          FROM library_models m
          WHERE m.id IN (SELECT model_id FROM model_tags WHERE tag_id = NEW.id);
        END
        """
    )
