from collections.abc import Generator
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import AutomaticTagMatch, AutomaticTagRule, ModelTag, Tag
from meshive.services.tags import recompute_automatic_tags


def test_legacy_automatic_rule_mutations_are_explicitly_disabled() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role_id=None,
        role_definition=SimpleNamespace(is_superuser=True),
        all_sources=True,
    )
    app.dependency_overrides[require_admin] = lambda: None
    try:
        with sessions() as session:
            source = LibrarySource(
                name="Test",
                root_path="/models/test",
                directory_pattern="{model_folder}",
                archive_formats=["7z", "zip", "rar"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            session.commit()

        with TestClient(app) as client:
            tag = client.post(
                "/api/admin/tags",
                json={"name": "Bust", "color": "#00ffff"},
            ).json()
            created = client.post(
                "/api/admin/automatic-tag-rules",
                json={"tag_id": tag["id"], "pattern": "bust", "enabled": True},
            )
            assert created.status_code == 410
            assert "assignment rules" in created.json()["detail"]
            assert client.post("/api/admin/automatic-tag-rules/re-evaluate").status_code == 410

        with sessions() as session:
            assert session.scalar(select(AutomaticTagMatch)) is None
            assert session.scalar(select(ModelTag)) is None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_rule_re_evaluation_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            source = LibrarySource(
                name="Test",
                root_path="/models/test",
                directory_pattern="{model_folder}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Hero",
                name="Hero",
                status="available",
            )
            session.add(model)
            session.flush()
            archive = Archive(
                model_id=model.id,
                filename="hero.7z",
                relative_path="Hero/hero.7z",
                format="7z",
                size_bytes=100,
                modified_ns=1,
                status="ready",
            )
            session.add(archive)
            session.flush()
            session.add(
                ArchiveEntry(
                    archive_id=archive.id,
                    path="NSFW/hero.stl",
                    name="hero.stl",
                    is_directory=False,
                )
            )
            session.commit()

            tag = Tag(name="NSFW")
            session.add(tag)
            session.flush()
            session.add(
                AutomaticTagRule(
                    tag_id=tag.id,
                    pattern="nsfw",
                    pattern_key="nsfw",
                    enabled=True,
                )
            )
            session.flush()

            first = recompute_automatic_tags(session)
            second = recompute_automatic_tags(session)

            assert first.matches == 1
            assert first.assignments_added == 1
            assert second.matches == 1
            assert second.assignments_added == 0
            assert second.assignments_removed == 0
            assert len(list(session.scalars(select(AutomaticTagMatch)))) == 1
            assert len(list(session.scalars(select(ModelTag)))) == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
