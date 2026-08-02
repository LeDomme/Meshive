from collections.abc import Generator

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


def test_automatic_rules_match_paths_and_preserve_manual_tags() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: object()
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
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Hero",
                name="Hero",
                status="available",
            )
            session.add(model)
            session.flush()
            first_archive = Archive(
                model_id=model.id,
                filename="hero.7z",
                relative_path="Hero/hero.7z",
                format="7z",
                size_bytes=100,
                modified_ns=1,
                status="ready",
            )
            second_archive = Archive(
                model_id=model.id,
                filename="extras.zip",
                relative_path="Hero/extras.zip",
                format="zip",
                size_bytes=50,
                modified_ns=1,
                status="ready",
            )
            session.add_all([first_archive, second_archive])
            session.flush()
            session.add_all(
                [
                    ArchiveEntry(
                        archive_id=first_archive.id,
                        path="Supported/BUST/hero.stl",
                        name="hero.stl",
                        is_directory=False,
                    ),
                    ArchiveEntry(
                        archive_id=second_archive.id,
                        path="Documentation/readme.txt",
                        name="readme.txt",
                        is_directory=False,
                    ),
                ]
            )
            session.commit()
            model_id = model.id

        with TestClient(app) as client:
            tag = client.post(
                "/api/admin/tags",
                json={"name": "Bust", "color": "#00ffff"},
            ).json()
            created = client.post(
                "/api/admin/automatic-tag-rules",
                json={"tag_id": tag["id"], "pattern": "bust", "enabled": True},
            )
            assert created.status_code == 201
            assert created.json()["match_count"] == 1
            duplicate = client.post(
                "/api/admin/automatic-tag-rules",
                json={"tag_id": tag["id"], "pattern": "BUST", "enabled": True},
            )
            assert duplicate.status_code == 409

            detail = client.get(f"/api/models/{model_id}").json()
            assert [item["name"] for item in detail["tags"]] == ["Bust"]

            listed = client.get("/api/admin/automatic-tag-rules").json()
            assert listed[0]["pattern"] == "bust"
            assert listed[0]["match_count"] == 1
            reevaluated = client.post("/api/admin/automatic-tag-rules/re-evaluate").json()
            assert reevaluated == {
                "models_evaluated": 1,
                "matches": 1,
                "assignments_added": 0,
                "assignments_removed": 0,
            }

            assert client.put(f"/api/admin/models/{model_id}/tags/{tag['id']}").status_code == 204
            disabled = client.put(
                f"/api/admin/automatic-tag-rules/{created.json()['id']}",
                json={"tag_id": tag["id"], "pattern": "bust", "enabled": False},
            )
            assert disabled.status_code == 200
            assert disabled.json()["match_count"] == 0

            detail = client.get(f"/api/models/{model_id}").json()
            assert [item["name"] for item in detail["tags"]] == ["Bust"]

            assert (
                client.delete(f"/api/admin/models/{model_id}/tags/{tag['id']}").status_code == 204
            )
            detail = client.get(f"/api/models/{model_id}").json()
            assert detail["tags"] == []

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
