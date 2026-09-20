"""Store model variants as ordered multi-value metadata.

Revision ID: 20260920_47
Revises: 20260918_46
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_47"
down_revision: str | Sequence[str] | None = "20260918_46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "model_id",
            sa.Integer(),
            sa.ForeignKey("library_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("model_id", "normalized_value"),
    )
    op.create_index("ix_model_variants_model_id", "model_variants", ["model_id"])
    op.execute(
        """
        INSERT INTO model_variants (model_id, value, normalized_value, position)
        SELECT id, variant, lower(trim(variant)), 0
        FROM library_models
        WHERE variant IS NOT NULL AND trim(variant) != ''
        """
    )
    _drop_search_index()
    op.drop_column("library_models", "variant")
    _create_search_index()


def downgrade() -> None:
    _drop_search_index()
    op.add_column("library_models", sa.Column("variant", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE library_models
        SET variant = (
            SELECT value FROM model_variants
            WHERE model_variants.model_id = library_models.id
            ORDER BY position, id
            LIMIT 1
        )
        """
    )
    op.drop_index("ix_model_variants_model_id", table_name="model_variants")
    op.drop_table("model_variants")
    _create_legacy_search_index()


def _create_legacy_search_index() -> None:
    """Restore the pre-1.9 FTS projection after the relation has been removed."""
    op.execute(
        """
        CREATE VIRTUAL TABLE model_search USING fts5(
            model_id UNINDEXED, name, variant, creator, franchise, series, collection, tags,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        INSERT INTO model_search (model_id, name, variant, creator, franchise, series, collection, tags)
        SELECT m.id, m.name, COALESCE(m.variant, ''), COALESCE(m.creator, ''),
               COALESCE(m.franchise, ''), COALESCE(m.series, ''), COALESCE(m.collection, ''),
               COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
        FROM library_models m
        """
    )


def _drop_search_index() -> None:
    for trigger in (
        "tags_au",
        "model_tags_ad",
        "model_tags_au",
        "model_tags_ai",
        "library_models_ad",
        "library_models_au",
        "library_models_ai",
        "model_variants_ad",
        "model_variants_au",
        "model_variants_ai",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS model_search")


def _create_search_index() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE model_search USING fts5(
            model_id UNINDEXED, name, variant, creator, franchise, series, collection, tags,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    _refresh_all()
    for name, event, model_id in (
        ("library_models_ai", "INSERT", "NEW.id"),
        ("library_models_au", "UPDATE", "NEW.id"),
        ("library_models_ad", "DELETE", "OLD.id"),
        ("model_variants_ai", "INSERT", "NEW.model_id"),
        ("model_variants_au", "UPDATE", "NEW.model_id"),
        ("model_variants_ad", "DELETE", "OLD.model_id"),
        ("model_tags_ai", "INSERT", "NEW.model_id"),
        ("model_tags_au", "UPDATE", "NEW.model_id"),
        ("model_tags_ad", "DELETE", "OLD.model_id"),
    ):
        _create_refresh_trigger(name, event, model_id)
    _create_tag_update_trigger()


def _refresh_all() -> None:
    op.execute(
        """
        INSERT INTO model_search (model_id, name, variant, creator, franchise, series, collection, tags)
        SELECT m.id, m.name,
               COALESCE((SELECT group_concat(mv.value, ' ') FROM model_variants mv WHERE mv.model_id = m.id), ''),
               COALESCE(m.creator, ''), COALESCE(m.franchise, ''), COALESCE(m.series, ''),
               COALESCE(m.collection, ''),
               COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
        FROM library_models m
        """
    )


def _create_refresh_trigger(name: str, event: str, model_id: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER {name} AFTER {event} ON {name.rsplit('_', 1)[0]}
        BEGIN
            DELETE FROM model_search WHERE model_id = {model_id};
            INSERT INTO model_search (model_id, name, variant, creator, franchise, series, collection, tags)
            SELECT m.id, m.name,
                   COALESCE((SELECT group_concat(mv.value, ' ') FROM model_variants mv WHERE mv.model_id = m.id), ''),
                   COALESCE(m.creator, ''), COALESCE(m.franchise, ''), COALESCE(m.series, ''),
                   COALESCE(m.collection, ''),
                   COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
            FROM library_models m WHERE m.id = {model_id};
        END
        """
    )


def _create_tag_update_trigger() -> None:
    op.execute(
        """
        CREATE TRIGGER tags_au AFTER UPDATE ON tags
        BEGIN
            DELETE FROM model_search WHERE model_id IN (SELECT model_id FROM model_tags WHERE tag_id = NEW.id);
            INSERT INTO model_search (model_id, name, variant, creator, franchise, series, collection, tags)
            SELECT m.id, m.name,
                   COALESCE((SELECT group_concat(mv.value, ' ') FROM model_variants mv WHERE mv.model_id = m.id), ''),
                   COALESCE(m.creator, ''), COALESCE(m.franchise, ''), COALESCE(m.series, ''), COALESCE(m.collection, ''),
                   COALESCE((SELECT group_concat(t.name, ' ') FROM model_tags mt JOIN tags t ON t.id = mt.tag_id WHERE mt.model_id = m.id), '')
            FROM library_models m WHERE m.id IN (SELECT model_id FROM model_tags WHERE tag_id = NEW.id);
        END
        """
    )
