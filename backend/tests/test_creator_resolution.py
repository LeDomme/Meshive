from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from meshive.creators import (
    CreatorResolutionConflictError,
    resolve_creator_profile,
)
from meshive.database import Base
from meshive.models.creator import CreatorAlias, CreatorProfile


def test_resolve_creator_profile_creates_and_reuses_exact_normalized_identity() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        created = resolve_creator_profile(session, "  Cr\u00e9ator  ")
        assert created is not None
        assert created.display_name == "Cr\u00e9ator"
        assert created.normalized_name == "cr\u00e9ator"
        assert session.query(CreatorAlias).count() == 0

        reused = resolve_creator_profile(session, "Cr\u00e9ator")
        assert reused is not None
        assert reused.id == created.id
        assert resolve_creator_profile(session, "   ") is None
    engine.dispose()


def test_resolve_creator_profile_uses_alias_without_mutating_profile() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        profile = CreatorProfile(
            display_name="Canonical Creator",
            normalized_name="canonical creator",
            description="Keep this",
        )
        session.add(profile)
        session.flush()
        session.add(
            CreatorAlias(
                creator_profile_id=profile.id,
                alias="Creator Alias",
                normalized_alias="creator alias",
            )
        )
        session.flush()

        resolved = resolve_creator_profile(session, " creator alias ")

        assert resolved is not None
        assert resolved.id == profile.id
        assert profile.display_name == "Canonical Creator"
        assert profile.description == "Keep this"
    engine.dispose()


def test_resolve_creator_profile_rejects_cross_table_conflicts() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = CreatorProfile(display_name="First", normalized_name="same creator")
        second = CreatorProfile(display_name="Second", normalized_name="second creator")
        session.add_all([first, second])
        session.flush()
        session.add(
            CreatorAlias(
                creator_profile_id=second.id,
                alias="Same Creator",
                normalized_alias="same creator",
            )
        )
        session.flush()

        try:
            resolve_creator_profile(session, "Same Creator")
        except CreatorResolutionConflictError:
            pass
        else:
            raise AssertionError("Expected a Creator identity conflict")
    engine.dispose()
