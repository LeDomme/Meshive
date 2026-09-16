"""Shared Creator Profile helpers.

The raw ``LibraryModel.creator`` value remains scan-owned.  This module only
defines the stable identity key used by Creator Profile records and aliases.
"""

import unicodedata

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.models.creator import CreatorAlias, CreatorProfile


def normalize_creator_name(value: str) -> str:
    """Return Meshive's Unicode-aware stable key for a Creator name."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


class CreatorResolutionConflictError(RuntimeError):
    """Raised when one normalized Creator key belongs to multiple profiles."""


def resolve_creator_profile(
    session: Session, raw_creator: str | None
) -> CreatorProfile | None:
    """Resolve a scanned Creator value to its stable profile.

    Raw catalogue data remains authoritative for display and compatibility.  This
    resolver only manages the stable foreign key and deliberately performs exact
    normalization matching; it never guesses aliases or changes existing profile
    metadata.
    """
    if raw_creator is None:
        return None
    if not isinstance(raw_creator, str):
        raise TypeError("Creator value must be text")

    display_name = raw_creator.strip()
    normalized_name = normalize_creator_name(raw_creator)
    if not display_name or not normalized_name:
        return None

    profile = _find_creator_profile(session, normalized_name)
    if profile is not None:
        return profile

    try:
        # A savepoint lets the surrounding scan transaction continue after a
        # concurrent SQLite writer wins the unique-key race.
        with session.begin_nested():
            profile = CreatorProfile(
                display_name=display_name,
                normalized_name=normalized_name,
            )
            session.add(profile)
            session.flush()
    except IntegrityError:
        profile = _find_creator_profile(session, normalized_name)
        if profile is not None:
            return profile
        raise
    return profile


def _find_creator_profile(session: Session, normalized_name: str) -> CreatorProfile | None:
    """Find one profile for a normalized key or reject cross-table conflicts."""
    profiles = list(
        session.scalars(
            select(CreatorProfile).where(CreatorProfile.normalized_name == normalized_name)
        )
    )
    alias_profile_ids = set(
        session.scalars(
            select(CreatorAlias.creator_profile_id).where(
                CreatorAlias.normalized_alias == normalized_name
            )
        )
    )
    profile_ids = {profile.id for profile in profiles} | alias_profile_ids
    if len(profile_ids) > 1:
        raise CreatorResolutionConflictError(
            f"Creator identity '{normalized_name}' maps to multiple Creator Profiles"
        )
    if not profile_ids:
        return None
    profile_id = profile_ids.pop()
    if profiles and profiles[0].id == profile_id:
        return profiles[0]
    return session.get(CreatorProfile, profile_id)
