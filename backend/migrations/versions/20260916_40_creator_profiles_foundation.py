"""Add stable Creator Profile foundations and backfill legacy references.

Revision ID: 20260916_40
Revises: 20260911_39
"""

import unicodedata
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_40"
down_revision: str | Sequence[str] | None = "20260911_39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _preflight_legacy_creator_data()
    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("artwork_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["artwork_id"], ["metadata_artwork.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_creator_profiles_normalized_name", "creator_profiles", ["normalized_name"])
    op.create_table(
        "creator_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("creator_profile_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["creator_profile_id"], ["creator_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("normalized_alias"),
    )
    op.create_index("ix_creator_aliases_creator_profile_id", "creator_aliases", ["creator_profile_id"])
    op.create_index("ix_creator_aliases_normalized_alias", "creator_aliases", ["normalized_alias"])

    # SQLite can add a nullable REFERENCES column directly.  Avoid batch table
    # recreation here: library_models has FTS triggers which temporarily lose
    # their referenced table during a batch rename.
    op.execute(
        "ALTER TABLE library_models ADD COLUMN creator_profile_id "
        "INTEGER REFERENCES creator_profiles(id) ON DELETE SET NULL"
    )
    op.create_index("ix_library_models_creator_profile_id", "library_models", ["creator_profile_id"])
    op.execute(
        "ALTER TABLE creator_metadata_links ADD COLUMN creator_profile_id "
        "INTEGER REFERENCES creator_profiles(id) ON DELETE SET NULL"
    )
    op.create_index(
        "ix_creator_metadata_links_creator_profile_id",
        "creator_metadata_links",
        ["creator_profile_id"],
    )

    _backfill_creator_profiles()


def downgrade() -> None:
    op.drop_index("ix_creator_metadata_links_creator_profile_id", table_name="creator_metadata_links")
    op.drop_column("creator_metadata_links", "creator_profile_id")
    op.drop_index("ix_library_models_creator_profile_id", table_name="library_models")
    op.drop_column("library_models", "creator_profile_id")
    op.drop_index("ix_creator_aliases_normalized_alias", table_name="creator_aliases")
    op.drop_index("ix_creator_aliases_creator_profile_id", table_name="creator_aliases")
    op.drop_table("creator_aliases")
    op.drop_index("ix_creator_profiles_normalized_name", table_name="creator_profiles")
    op.drop_table("creator_profiles")


def _normalize_creator_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _preflight_legacy_creator_data() -> None:
    """Fail before SQLite DDL if legacy data cannot be assigned unambiguously."""
    connection = op.get_bind()
    for row in connection.execute(
        sa.text("SELECT id, creator_name FROM creator_metadata_links ORDER BY id")
    ).mappings():
        if not _normalize_creator_name(str(row["creator_name"])):
            raise RuntimeError(f"Creator Link {row['id']} has a blank creator name")

    artwork_names: set[str] = set()
    for row in connection.execute(
        sa.text(
            "SELECT id, entity_value, entity_key FROM metadata_artwork "
            "WHERE entity_type = 'creator' ORDER BY id"
        )
    ).mappings():
        normalized = _normalize_creator_name(str(row["entity_value"]))
        if not normalized or str(row["entity_key"]) != normalized:
            raise RuntimeError(
                f"Creator artwork {row['id']} has an unexpected normalized key; "
                "resolve the metadata row before upgrading"
            )
        if normalized in artwork_names:
            raise RuntimeError(
                f"Multiple creator artworks resolve to {normalized!r}; "
                "resolve the artwork conflict before upgrading"
            )
        artwork_names.add(normalized)


def _backfill_creator_profiles() -> None:
    """Backfill without changing legacy values or their existing semantics.

    The display spelling is the most frequently observed raw spelling over
    models, links, and creator artwork. Ties use the first stable database row
    encountered: models, then links, then artwork, each by ascending ID.
    """
    connection = op.get_bind()
    observations: dict[str, list[tuple[str, int]]] = defaultdict(list)
    model_updates: list[dict[str, object]] = []
    link_updates: list[dict[str, object]] = []
    artwork_by_normalized_name: dict[str, int] = {}

    for row in connection.execute(
        sa.text("SELECT id, creator FROM library_models WHERE creator IS NOT NULL ORDER BY id")
    ).mappings():
        raw = str(row["creator"])
        normalized = _normalize_creator_name(raw)
        if not normalized:
            continue
        observations[normalized].append((raw, int(row["id"])))
        model_updates.append({"id": int(row["id"]), "normalized_name": normalized})

    for row in connection.execute(
        sa.text("SELECT id, creator_name FROM creator_metadata_links ORDER BY id")
    ).mappings():
        raw = str(row["creator_name"])
        normalized = _normalize_creator_name(raw)
        if not normalized:
            raise RuntimeError(f"Creator Link {row['id']} has a blank creator name")
        observations[normalized].append((raw, 1_000_000_000 + int(row["id"])))
        link_updates.append({"id": int(row["id"]), "normalized_name": normalized})

    for row in connection.execute(
        sa.text(
            "SELECT id, entity_value, entity_key FROM metadata_artwork "
            "WHERE entity_type = 'creator' ORDER BY id"
        )
    ).mappings():
        raw = str(row["entity_value"])
        normalized = _normalize_creator_name(raw)
        if not normalized or str(row["entity_key"]) != normalized:
            raise RuntimeError(
                f"Creator artwork {row['id']} has an unexpected normalized key; "
                "resolve the metadata row before upgrading"
            )
        if normalized in artwork_by_normalized_name:
            raise RuntimeError(
                f"Multiple creator artworks resolve to {normalized!r}; "
                "resolve the artwork conflict before upgrading"
            )
        observations[normalized].append((raw, 2_000_000_000 + int(row["id"])))
        artwork_by_normalized_name[normalized] = int(row["id"])

    profile_ids: dict[str, int] = {}
    for normalized, names in observations.items():
        display_name = _select_display_name(names)
        connection.execute(
            sa.text(
                "INSERT INTO creator_profiles "
                "(display_name, normalized_name, artwork_id, is_active) "
                "VALUES (:display_name, :normalized_name, :artwork_id, 1)"
            ),
            {
                "display_name": display_name,
                "normalized_name": normalized,
                "artwork_id": artwork_by_normalized_name.get(normalized),
            },
        )
        profile_id = connection.scalar(
            sa.text("SELECT id FROM creator_profiles WHERE normalized_name = :normalized_name"),
            {"normalized_name": normalized},
        )
        if profile_id is None:
            raise RuntimeError(f"Could not create Creator Profile for {display_name!r}")
        profile_ids[normalized] = int(profile_id)
        # A unique normalized alias is the profile's canonical lookup key.
        # Case/NFKC variants remain losslessly stored in the legacy raw fields.
        connection.execute(
            sa.text(
                "INSERT INTO creator_aliases (creator_profile_id, alias, normalized_alias) "
                "VALUES (:creator_profile_id, :alias, :normalized_alias)"
            ),
            {
                "creator_profile_id": int(profile_id),
                "alias": display_name,
                "normalized_alias": normalized,
            },
        )

    _apply_profile_updates(connection, "library_models", model_updates, profile_ids)
    _apply_profile_updates(connection, "creator_metadata_links", link_updates, profile_ids)


def _select_display_name(names: list[tuple[str, int]]) -> str:
    counts: dict[str, int] = defaultdict(int)
    first_position: dict[str, int] = {}
    for raw, position in names:
        counts[raw] += 1
        first_position.setdefault(raw, position)
    return min(counts, key=lambda raw: (-counts[raw], first_position[raw], raw))


def _apply_profile_updates(
    connection: sa.Connection,
    table_name: str,
    updates: list[dict[str, object]],
    profile_ids: dict[str, int],
) -> None:
    statement = sa.text(
        f"UPDATE {table_name} SET creator_profile_id = :creator_profile_id WHERE id = :id"
    )
    for start in range(0, len(updates), 500):
        batch = [
            {"id": update["id"], "creator_profile_id": profile_ids[str(update["normalized_name"])]}
            for update in updates[start : start + 500]
        ]
        if batch:
            connection.execute(statement, batch)
