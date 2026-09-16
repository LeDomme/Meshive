"""Bind Creator metadata and favorites to stable profiles.

Revision ID: 20260916_41
Revises: 20260916_40
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_41"
down_revision: str | Sequence[str] | None = "20260916_40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    op.execute(
        "ALTER TABLE favorite_list_items ADD COLUMN creator_profile_id "
        "INTEGER REFERENCES creator_profiles(id) ON DELETE SET NULL"
    )
    op.create_index(
        "ix_favorite_list_items_creator_profile_id",
        "favorite_list_items",
        ["creator_profile_id"],
    )
    _backfill_creator_links(connection)
    _backfill_creator_artwork(connection)
    _backfill_creator_favorites(connection)


def downgrade() -> None:
    op.drop_index("ix_favorite_list_items_creator_profile_id", "favorite_list_items")
    op.drop_column("favorite_list_items", "creator_profile_id")


def _profile_id(connection, normalized_name: str) -> int | None:
    rows = connection.execute(
        sa.text(
            "SELECT id FROM creator_profiles WHERE normalized_name = :name "
            "UNION SELECT creator_profile_id FROM creator_aliases "
            "WHERE normalized_alias = :name"
        ),
        {"name": normalized_name},
    ).scalars().all()
    profile_ids = set(rows)
    if len(profile_ids) > 1:
        raise RuntimeError(
            f"Creator identity {normalized_name!r} maps to multiple Creator Profiles"
        )
    return next(iter(profile_ids), None)


def _backfill_creator_links(connection) -> None:
    for row in connection.execute(
        sa.text(
            "SELECT id, creator_name FROM creator_metadata_links "
            "WHERE creator_profile_id IS NULL ORDER BY id"
        )
    ).mappings():
        profile_id = _profile_id(connection, _normalize(str(row["creator_name"])))
        if profile_id is not None:
            connection.execute(
                sa.text("UPDATE creator_metadata_links SET creator_profile_id = :profile_id WHERE id = :id"),
                {"id": row["id"], "profile_id": profile_id},
            )


def _backfill_creator_artwork(connection) -> None:
    assignments: dict[int, int] = {}
    for row in connection.execute(
        sa.text("SELECT id, entity_key FROM metadata_artwork WHERE entity_type = 'creator'")
    ).mappings():
        profile_id = _profile_id(connection, str(row["entity_key"]))
        if profile_id is not None:
            if profile_id in assignments:
                raise RuntimeError(
                    f"Multiple creator artworks map to Creator Profile {profile_id}"
                )
            assignments[profile_id] = int(row["id"])
            connection.execute(
                sa.text("UPDATE creator_profiles SET artwork_id = :artwork_id WHERE id = :id"),
                {"id": profile_id, "artwork_id": row["id"]},
            )


def _backfill_creator_favorites(connection) -> None:
    assignments: set[tuple[int, int]] = set()
    for row in connection.execute(
        sa.text(
            "SELECT id, favorite_list_id, entity_key FROM favorite_list_items "
            "WHERE entity_type = 'creator' ORDER BY id"
        )
    ).mappings():
        profile_id = _profile_id(connection, str(row["entity_key"]))
        if profile_id is not None:
            key = (int(row["favorite_list_id"]), profile_id)
            if key in assignments:
                raise RuntimeError(
                    "Multiple creator favorites in one list map to the same Creator Profile"
                )
            assignments.add(key)
            connection.execute(
                sa.text(
                    "UPDATE favorite_list_items SET creator_profile_id = :profile_id, "
                    "entity_key = :entity_key WHERE id = :id"
                ),
                {"id": row["id"], "profile_id": profile_id, "entity_key": f"creator-profile:{profile_id}"},
            )


def _normalize(value: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKC", value).strip().casefold()
