import tarfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import (
    CATALOGUE_VIEW,
    CATALOGUE_VIEW_MAINTENANCE,
    MODELS_DELETE_MISSING,
    MODELS_PRIMARY_IMAGE,
    MODELS_REBUILD_IMAGES,
    MODELS_RESCAN,
    MODELS_RESET_IMAGES,
)
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.catalog import (
    Archive,
    ArchiveEntry,
    LibraryModel,
    ModelImage,
    ScanIssue,
    ScanRun,
)
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.repositories.roles import get_system_role_for_legacy_role


@contextmanager
def catalog_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE model_search USING fts5("
            "model_id UNINDEXED, name, variant, creator, franchise, series, "
            "collection, tags)"
        )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        role_id=None,
        role_definition=SimpleNamespace(is_superuser=True),
        all_sources=True,
    )
    try:
        with TestClient(app) as client:
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_lists_searches_filters_and_downloads_models(tmp_path) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Aoae",
                root_path=tmp_path.as_posix(),
                directory_pattern="{franchise}/{model_folder}",
                model_pattern="{franchise} - {model} - by {creator}",
                archive_formats=["7z", "zip", "rar"],
                image_formats=["jpg", "jpeg", "png", "webp"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Moikaloop/Moikaloop - Neon Moika - by Aoae",
                name="Neon Moika",
                creator="Aoae",
                franchise="Moikaloop",
                series="Moikaloop",
                status="available",
            )
            session.add(model)
            session.flush()
            archive = Archive(
                model_id=model.id,
                filename="model.7z",
                relative_path=f"{model.relative_path}/model.7z",
                format="7z",
                size_bytes=1024,
                modified_ns=1,
                status="ready",
                entry_count=1,
                uncompressed_size_bytes=2048,
            )
            session.add(archive)
            session.flush()
            session.add(
                ArchiveEntry(
                    archive_id=archive.id,
                    path="STL/model.stl",
                    name="model.stl",
                    is_directory=False,
                    size_bytes=2048,
                    compressed_size_bytes=1024,
                )
            )
            session.add(
                Archive(
                    model_id=model.id,
                    filename="extras.zip",
                    relative_path=f"{model.relative_path}/extras.zip",
                    format="zip",
                    size_bytes=512,
                    modified_ns=1,
                    status="ready",
                    entry_count=0,
                    uncompressed_size_bytes=0,
                )
            )
            session.commit()
            session.execute(
                text(
                    "INSERT INTO model_search("
                    "model_id, name, variant, creator, franchise, series, "
                    "collection, tags) VALUES ("
                    ":id, :name, '', :creator, :franchise, :series, '', '')"
                ),
                {
                    "id": model.id,
                    "name": model.name,
                    "creator": model.creator,
                    "franchise": model.franchise,
                    "series": model.series,
                },
            )
            session.commit()

        archive_path = tmp_path / model.relative_path / "model.7z"
        archive_path.parent.mkdir(parents=True)
        archive_path.write_bytes(b"0123456789")
        extras_path = tmp_path / model.relative_path / "extras.zip"
        extras_path.write_bytes(b"extra")

        response = client.get("/api/models", params={"search": "neon"})
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["creator"] == "Aoae"
        assert response.json()["items"][0]["series"] == "Moikaloop"
        assert response.json()["items"][0]["archive_count"] == 2
        assert response.json()["items"][0]["archive_size_bytes"] == 1536

        detail = client.get(f"/api/models/{model.id}")
        assert detail.status_code == 200
        assert detail.json()["relative_path"] == model.relative_path
        assert len(detail.json()["archives"]) == 2
        assert detail.json()["archive_bundle_download_url"] == (
            f"/api/models/{model.id}/archives/download-all"
        )
        assert detail.json()["archives"][1]["entries"][0]["path"] == "STL/model.stl"
        download_url = detail.json()["archives"][1]["download_url"]
        partial_download = client.get(
            download_url, headers={"Range": "bytes=2-5"}
        )
        assert partial_download.status_code == 206
        assert partial_download.content == b"2345"
        assert partial_download.headers["content-range"] == "bytes 2-5/10"
        assert "attachment" in partial_download.headers["content-disposition"]

        bundle_download = client.get(detail.json()["archive_bundle_download_url"])
        assert bundle_download.status_code == 200
        assert bundle_download.headers["content-type"].startswith("application/x-tar")
        assert "attachment" in bundle_download.headers["content-disposition"]
        with tarfile.open(fileobj=BytesIO(bundle_download.content), mode="r:") as bundle:
            assert bundle.getnames() == ["extras.zip", "model.7z"]
            assert bundle.extractfile("extras.zip").read() == b"extra"
            assert bundle.extractfile("model.7z").read() == b"0123456789"

        filtered_out = client.get(
            "/api/models", params={"franchise": "Different franchise"}
        )
        assert filtered_out.status_code == 200
        assert filtered_out.json()["total"] == 0

        exact_model = client.get("/api/models", params={"model": model.name})
        assert exact_model.status_code == 200
        assert exact_model.json()["total"] == 1
        assert exact_model.json()["items"][0]["name"] == model.name

        partial_model = client.get("/api/models", params={"model": "Neon"})
        assert partial_model.status_code == 200
        assert partial_model.json()["total"] == 0

        filters = client.get("/api/models/filters")
        assert filters.status_code == 200
        assert filters.json()["models"] == [{"value": model.name, "count": 1}]
        assert filters.json()["creators"] == [{"value": "Aoae", "count": 1}]
        assert filters.json()["series"] == [{"value": "Moikaloop", "count": 1}]


def test_catalogue_source_scope_prevents_cross_source_data_leaks() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source_a = LibrarySource(
                name="Source A",
                root_path="/models/a",
                directory_pattern="{creator}/{model}",
            )
            source_b = LibrarySource(
                name="Source B",
                root_path="/models/b",
                directory_pattern="{creator}/{model}",
            )
            session.add_all([source_a, source_b])
            session.flush()
            models = [
                LibraryModel(
                    library_source_id=source_a.id,
                    relative_path="A/Amber",
                    name="Amber Model",
                    creator="Creator A",
                    franchise="Franchise A",
                    status="available",
                ),
                LibraryModel(
                    library_source_id=source_b.id,
                    relative_path="B/Blue",
                    name="Blue Model",
                    creator="Creator B",
                    franchise="Franchise B",
                    status="available",
                ),
                LibraryModel(
                    library_source_id=source_b.id,
                    relative_path="B/Bronze",
                    name="Bronze Model",
                    creator="Creator B",
                    franchise="Franchise B",
                    status="available",
                ),
            ]
            session.add_all(models)
            session.flush()
            for model in models:
                session.execute(
                    text(
                        "INSERT INTO model_search(model_id, name, variant, creator, "
                        "franchise, series, collection, tags) VALUES "
                        "(:id, :name, '', :creator, :franchise, '', '', '')"
                    ),
                    {
                        "id": model.id,
                        "name": model.name,
                        "creator": model.creator,
                        "franchise": model.franchise,
                    },
                )
            administrator = User(
                username="Administrator",
                normalized_username="administrator",
                password_hash="unused",
                role="admin",
                role_definition=get_system_role_for_legacy_role(session, "admin"),
                all_sources=False,
                is_active=True,
            )
            all_sources_user = User(
                username="All sources",
                normalized_username="all sources",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=True,
                is_active=True,
            )
            a_only_user = User(
                username="A only",
                normalized_username="a only",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=False,
                is_active=True,
            )
            no_sources_user = User(
                username="No sources",
                normalized_username="no sources",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=False,
                is_active=True,
            )
            session.add_all(
                [
                    administrator,
                    all_sources_user,
                    a_only_user,
                    no_sources_user,
                ]
            )
            session.flush()
            session.add(
                UserLibrarySource(user_id=a_only_user.id, library_source_id=source_a.id)
            )
            session.commit()

        def use_user(user: User) -> None:
            app.dependency_overrides[get_current_user] = lambda: user

        for user in (administrator, all_sources_user):
            use_user(user)
            response = client.get("/api/models", params={"sort": "name_asc"})
            assert response.status_code == 200
            assert response.json()["total"] == 3
            assert {item["source_id"] for item in response.json()["items"]} == {
                source_a.id,
                source_b.id,
            }

        use_user(a_only_user)
        response = client.get("/api/models", params={"sort": "name_asc", "page_size": 1})
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert [item["name"] for item in response.json()["items"]] == ["Amber Model"]
        assert client.get("/api/models", params={"search": "blue"}).json()["total"] == 0
        assert client.get("/api/models", params={"page": 2, "page_size": 1}).json()["items"] == []

        facets = client.get("/api/models/filters").json()
        assert facets["models"] == [{"value": "Amber Model", "count": 1}]
        assert facets["creators"] == [{"value": "Creator A", "count": 1}]
        assert facets["franchises"] == [{"value": "Franchise A", "count": 1}]
        assert facets["sources"] == [{"id": source_a.id, "name": "Source A", "count": 1}]
        assert client.get(f"/api/models/{models[1].id}").status_code == 404
        assert client.get(f"/api/models/{models[1].id}/navigation").status_code == 404
        navigation = client.get(f"/api/models/{models[0].id}/navigation").json()
        assert navigation == {"previous": None, "next": None}

        use_user(no_sources_user)
        response = client.get("/api/models", params={"search": "model"})
        assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 48}
        facets = client.get("/api/models/filters").json()
        assert all(not facets[key] for key in ("models", "creators", "franchises", "sources"))
        assert client.get(f"/api/models/{models[0].id}").status_code == 404
        assert client.get(f"/api/models/{models[0].id}/navigation").status_code == 404


def test_media_and_download_routes_are_source_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("meshive.api.catalog.get_settings", lambda: SimpleNamespace(cache_dir=tmp_path))
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source_a = LibrarySource(name="A", root_path=str(tmp_path / "a"), directory_pattern="{model}")
            source_b = LibrarySource(name="B", root_path=str(tmp_path / "b"), directory_pattern="{model}")
            session.add_all([source_a, source_b])
            session.flush()
            model_a = LibraryModel(library_source_id=source_a.id, relative_path="A", name="A", status="available")
            model_b = LibraryModel(library_source_id=source_b.id, relative_path="B", name="B", status="available")
            session.add_all([model_a, model_b])
            session.flush()
            archive_a = Archive(model_id=model_a.id, filename="a.zip", relative_path="A/a.zip", format="zip", size_bytes=6, modified_ns=1, status="ready")
            archive_b = Archive(model_id=model_b.id, filename="b.zip", relative_path="B/b.zip", format="zip", size_bytes=6, modified_ns=1, status="ready")
            archive_b_extra = Archive(model_id=model_b.id, filename="b-extra.zip", relative_path="B/b-extra.zip", format="zip", size_bytes=6, modified_ns=1, status="ready")
            session.add_all([archive_a, archive_b, archive_b_extra])
            session.flush()
            session.add(
                ArchiveEntry(
                    archive_id=archive_a.id,
                    path="files/a.stl",
                    name="a.stl",
                    is_directory=False,
                )
            )
            image_a = ModelImage(model_id=model_a.id, filename="a.jpg", relative_path="A/a.jpg", storage_kind="source", format="jpg", size_bytes=1, modified_ns=1, is_available=True)
            image_b = ModelImage(model_id=model_b.id, filename="b.jpg", relative_path="B/b.jpg", storage_kind="source", format="jpg", size_bytes=1, modified_ns=1, is_available=True)
            session.add_all([image_a, image_b])
            member = User(username="Member", normalized_username="member", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=True, is_active=True)
            viewer_role = Role(name="Viewer test", normalized_name="viewer test")
            viewer = User(username="Viewer", normalized_username="viewer", password_hash="unused", role="user", role_definition=viewer_role, all_sources=True, is_active=True)
            no_catalogue_role = Role(name="No catalogue", normalized_name="no catalogue")
            no_catalogue = User(username="No catalogue", normalized_username="no catalogue", password_hash="unused", role="user", role_definition=no_catalogue_role, all_sources=False, is_active=True)
            a_only = User(username="A only media", normalized_username="a only media", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=False, is_active=True)
            no_grant = User(username="No grant media", normalized_username="no grant media", password_hash="unused", role="user", role_definition=get_system_role_for_legacy_role(session, "user"), all_sources=False, is_active=True)
            session.add_all([member, viewer, a_only, no_grant, no_catalogue])
            session.flush()
            session.add_all([
                RolePermission(role_id=viewer_role.id, permission_key=CATALOGUE_VIEW),
                UserLibrarySource(user_id=a_only.id, library_source_id=source_a.id),
                UserLibrarySource(user_id=no_catalogue.id, library_source_id=source_a.id),
            ])
            session.commit()
        (tmp_path / "a" / "A").mkdir(parents=True)
        (tmp_path / "b" / "B").mkdir(parents=True)
        (tmp_path / "a" / "A" / "a.zip").write_bytes(b"abcdef")
        (tmp_path / "a" / "A" / "a.jpg").write_bytes(b"x")
        (tmp_path / "b" / "B" / "b.zip").write_bytes(b"abcdef")
        (tmp_path / "b" / "B" / "b-extra.zip").write_bytes(b"abcdef")
        (tmp_path / "b" / "B" / "b.jpg").write_bytes(b"x")
        app.dependency_overrides[get_current_user] = lambda: member
        assert client.get(f"/api/models/{model_a.id}/archives/{archive_a.id}/download", headers={"Range": "bytes=1-3"}).status_code == 206
        assert client.get(f"/api/models/{model_b.id}/archives/download-all").status_code == 200
        assert client.get(f"/api/models/{model_a.id}/images/{image_a.id}").status_code == 200
        assert client.get(f"/api/models/{model_a.id}/images/{image_b.id}").status_code == 404
        assert client.get(f"/api/models/{model_a.id}").json()["archives"][0]["entries"]
        app.dependency_overrides[get_current_user] = lambda: viewer
        assert client.get(f"/api/models/{model_a.id}/archives/{archive_a.id}/download").status_code == 403
        assert client.get(f"/api/models/{model_a.id}").json()["archives"][0]["entries"] == []
        app.dependency_overrides[get_current_user] = lambda: a_only
        assert client.get(f"/api/models/{model_b.id}/images/{image_b.id}").status_code == 404
        assert client.get(f"/api/models/{model_b.id}/thumbnail").status_code == 404
        assert client.get(f"/api/models/{model_b.id}/archives/{archive_b.id}/download", headers={"Range": "bytes=0-1"}).status_code == 404
        assert client.get(f"/api/models/{model_b.id}/archives/download-all").status_code == 404
        assert client.get(f"/api/models/{model_a.id}/archives/{archive_b.id}/download").status_code == 404
        app.dependency_overrides[get_current_user] = lambda: no_grant
        assert client.get(f"/api/models/{model_b.id}/archives/download-all").status_code == 404
        app.dependency_overrides[get_current_user] = lambda: no_catalogue
        assert client.get("/api/models").status_code == 403
        assert client.get("/api/models/filters").status_code == 403
        assert client.get(f"/api/models/{model_a.id}").status_code == 403
        assert client.get(f"/api/models/{model_a.id}/navigation").status_code == 403
        assert client.get(f"/api/models/{model_a.id}/images/{image_a.id}").status_code == 403
        assert client.get(f"/api/models/{model_a.id}/thumbnail").status_code == 403
        assert client.get(f"/api/models/{model_b.id}").status_code == 404
        assert client.get(f"/api/models/{model_b.id}/navigation").status_code == 404
        assert client.get(f"/api/models/{model_b.id}/images/{image_b.id}").status_code == 404


def test_canonical_model_filter_groups_variants_and_searches_variant() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Variants",
                root_path="/models/variants",
                directory_pattern="{franchise}/{model_folder}",
                model_pattern=(
                    "{franchise} - {series} - {model} - "
                    "{variant_identifier} {variant} - by {creator}"
                ),
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            models = [
                LibraryModel(
                    library_source_id=source.id,
                    relative_path=f"Marvel/Psylocke {variant}",
                    name="Psylocke",
                    variant=variant,
                    creator="E.S Monster",
                    franchise="Marvel",
                    series="X-Men",
                    status="available",
                )
                for variant in ("06", "Chibi version")
            ]
            session.add_all(models)
            session.flush()
            for model in models:
                session.execute(
                    text(
                        "INSERT INTO model_search("
                        "model_id, name, variant, creator, franchise, series, "
                        "collection, tags) VALUES ("
                        ":id, :name, :variant, :creator, :franchise, :series, '', '')"
                    ),
                    {
                        "id": model.id,
                        "name": model.name,
                        "variant": model.variant,
                        "creator": model.creator,
                        "franchise": model.franchise,
                        "series": model.series,
                    },
                )
            session.commit()
            chibi_id = models[1].id

        filters = client.get("/api/models/filters")
        assert filters.status_code == 200
        assert filters.json()["models"] == [{"value": "Psylocke", "count": 2}]

        filtered = client.get("/api/models", params={"model": "Psylocke"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 2
        assert [item["variant"] for item in filtered.json()["items"]] == [
            "06",
            "Chibi version",
        ]

        searched = client.get("/api/models", params={"search": "chibi"})
        assert searched.status_code == 200
        assert searched.json()["total"] == 1
        assert searched.json()["items"][0]["name"] == "Psylocke"
        assert searched.json()["items"][0]["variant"] == "Chibi version"

        detail = client.get(f"/api/models/{chibi_id}")
        assert detail.status_code == 200
        assert detail.json()["variant"] == "Chibi version"


def test_admin_can_only_delete_missing_models() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Test",
                root_path="/models/test",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            missing = LibraryModel(
                library_source_id=source.id,
                relative_path="Old name",
                name="Old name",
                status="missing",
            )
            available = LibraryModel(
                library_source_id=source.id,
                relative_path="Current name",
                name="Current name",
                status="available",
            )
            session.add_all([missing, available])
            session.commit()
            missing_id = missing.id
            available_id = available.id

        rejected = client.delete(f"/api/admin/models/{available_id}")
        assert rejected.status_code == 409

        deleted = client.delete(f"/api/admin/models/{missing_id}")
        assert deleted.status_code == 204
        with sessions() as session:
            assert session.get(LibraryModel, missing_id) is None
            session.add_all(
                [
                    LibraryModel(
                        library_source_id=source.id,
                        relative_path=f"Missing {index}",
                        name=f"Missing {index}",
                        status="missing",
                    )
                    for index in range(2)
                ]
            )
            session.commit()

        bulk_deleted = client.delete("/api/admin/models/missing")
        assert bulk_deleted.status_code == 200
        assert bulk_deleted.json() == {"deleted": 2}
        with sessions() as session:
            remaining = list(session.scalars(select(LibraryModel)))
            assert [model.id for model in remaining] == [available_id]


def test_admin_can_choose_primary_picture_and_reset_picture_records() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Pictures",
                root_path="/models/pictures",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Cammy",
                name="Cammy",
                status="available",
            )
            session.add(model)
            session.flush()
            session.add_all(
                [
                    ModelImage(
                        model_id=model.id,
                        filename="first.jpg",
                        relative_path="Cammy/first.jpg",
                        format="jpg",
                        size_bytes=100,
                        modified_ns=1,
                        is_primary=True,
                    ),
                    ModelImage(
                        model_id=model.id,
                        filename="second.jpg",
                        relative_path="Cammy/second.jpg",
                        format="jpg",
                        size_bytes=200,
                        modified_ns=2,
                    ),
                ]
            )
            session.commit()
            model_id = model.id
            second_id = session.scalar(
                select(ModelImage.id).where(ModelImage.filename == "second.jpg")
            )

        selected = client.put(f"/api/admin/models/{model_id}/images/{second_id}/primary")
        assert selected.status_code == 200
        assert selected.json() == {"image_id": second_id}
        with sessions() as session:
            images = list(
                session.scalars(
                    select(ModelImage)
                    .where(ModelImage.model_id == model_id)
                    .order_by(ModelImage.id)
                )
            )
            assert [image.is_primary for image in images] == [False, True]
            assert [image.is_primary_override for image in images] == [False, True]

        reset = client.delete(f"/api/admin/models/{model_id}/images")
        assert reset.status_code == 200
        assert reset.json() == {"deleted": 2}
        with sessions() as session:
            assert list(session.scalars(select(ModelImage))) == []


def test_missing_archive_cache_image_returns_not_found(tmp_path, monkeypatch) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Cached images",
                root_path=tmp_path.as_posix(),
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Cammy",
                name="Cammy",
                status="available",
            )
            session.add(model)
            session.flush()
            image = ModelImage(
                model_id=model.id,
                filename="cover.webp",
                relative_path="archive/1/cover.jpg",
                storage_kind="archive",
                format="webp",
                size_bytes=100,
                modified_ns=1,
                cache_key="archive-images/missing.webp",
            )
            session.add(image)
            session.commit()
            model_id = model.id
            image_id = image.id

        from meshive.api import catalog

        monkeypatch.setattr(
            catalog,
            "get_settings",
            lambda: SimpleNamespace(cache_dir=tmp_path),
        )
        response = client.get(f"/api/models/{model_id}/images/{image_id}")
        assert response.status_code == 404

def test_catalogue_pagination_boundaries() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Pagination",
                root_path="/models/pagination",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            session.add_all(
                [
                    LibraryModel(
                        library_source_id=source.id,
                        relative_path=f"Model {index}",
                        name=f"Model {index}",
                        status="available",
                    )
                    for index in range(1, 6)
                ]
            )
            session.commit()

        first_page = client.get("/api/models", params={"page": 1, "page_size": 2})
        middle_page = client.get("/api/models", params={"page": 2, "page_size": 2})
        last_page = client.get("/api/models", params={"page": 3, "page_size": 2})
        page_after_last = client.get(
            "/api/models", params={"page": 4, "page_size": 2}
        )

        assert all(
            response.status_code == 200
            for response in (first_page, middle_page, last_page, page_after_last)
        )
        first_payload = first_page.json()
        assert first_payload["total"] == 5
        assert first_payload["page"] == 1
        assert first_payload["page_size"] == 2
        assert [item["name"] for item in first_payload["items"]] == [
            "Model 1",
            "Model 2",
        ]
        assert [item["name"] for item in middle_page.json()["items"]] == [
            "Model 3",
            "Model 4",
        ]
        assert [item["name"] for item in last_page.json()["items"]] == ["Model 5"]
        assert page_after_last.json()["items"] == []
        assert client.get("/api/models", params={"page": 0}).status_code == 422


def test_catalogue_sorting_applies_before_pagination() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Sorting",
                root_path="/models/sorting",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            models = [
                LibraryModel(
                    library_source_id=source.id,
                    relative_path="Zeta",
                    name="Zeta",
                    creator="Alpha Creator",
                    status="available",
                    first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                LibraryModel(
                    library_source_id=source.id,
                    relative_path="Alpha",
                    name="Alpha",
                    creator="Zeta Creator",
                    status="available",
                    first_seen_at=datetime(2026, 2, 1, tzinfo=UTC),
                ),
                LibraryModel(
                    library_source_id=source.id,
                    relative_path="No creator",
                    name="No creator",
                    creator=None,
                    status="available",
                    first_seen_at=datetime(2026, 3, 1, tzinfo=UTC),
                ),
            ]
            session.add_all(models)
            session.flush()
            for model, modified_ns in zip(models, (100, 300, 200), strict=True):
                session.add(
                    Archive(
                        model_id=model.id,
                        filename=f"{model.name}.7z",
                        relative_path=f"{model.relative_path}/{model.name}.7z",
                        format="7z",
                        size_bytes=1,
                        modified_ns=modified_ns,
                        status="ready",
                        entry_count=0,
                        uncompressed_size_bytes=0,
                    )
                )
            session.commit()

        newest = client.get(
            "/api/models", params={"sort": "meshive_newest", "page_size": 2}
        )
        assert [item["name"] for item in newest.json()["items"]] == [
            "No creator",
            "Alpha",
        ]

        by_name = client.get("/api/models", params={"sort": "name_desc"})
        assert [item["name"] for item in by_name.json()["items"]] == [
            "Zeta",
            "No creator",
            "Alpha",
        ]

        by_creator = client.get("/api/models", params={"sort": "creator_asc"})
        assert [item["creator"] for item in by_creator.json()["items"]] == [
            "Alpha Creator",
            "Zeta Creator",
            None,
        ]

        by_files = client.get("/api/models", params={"sort": "files_newest"})
        assert [item["name"] for item in by_files.json()["items"]] == [
            "Alpha",
            "No creator",
            "Zeta",
        ]


def test_model_navigation_follows_catalogue_filters_and_sorting() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Navigation",
                root_path="/models/navigation",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            models = [
                LibraryModel(
                    library_source_id=source.id,
                    relative_path=name,
                    name=name,
                    franchise="Marvel" if name != "Unrelated" else "DC",
                    status="available",
                )
                for name in ["Alpha", "Beta", "Gamma", "Unrelated"]
            ]
            session.add_all(models)
            session.commit()

            response = client.get(
                f"/api/models/{models[1].id}/navigation",
                params={"franchise": "Marvel", "sort": "name_desc"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "previous": {"id": models[2].id, "name": "Gamma", "variant": None},
            "next": {"id": models[0].id, "name": "Alpha", "variant": None},
        }

        boundary = client.get(
            f"/api/models/{models[2].id}/navigation",
            params={"franchise": "Marvel", "sort": "name_desc"},
        )
        assert boundary.status_code == 200
        assert boundary.json()["previous"] is None
        assert boundary.json()["next"]["id"] == models[1].id


def test_filter_options_follow_other_selected_facets() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Facets",
                root_path="/models/facets",
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            session.add_all(
                [
                    LibraryModel(
                        library_source_id=source.id,
                        relative_path="Abe Model",
                        name="Abe Model",
                        creator="Abe3D",
                        franchise="Marvel",
                        series="X-Men",
                        status="available",
                    ),
                    LibraryModel(
                        library_source_id=source.id,
                        relative_path="Ado Model",
                        name="Ado Model",
                        creator="Other Creator",
                        franchise="Ado",
                        series="Music",
                        status="available",
                    ),
                ]
            )
            session.commit()

        for_creator = client.get("/api/models/filters", params={"creator": "Abe3D"})
        assert [item["value"] for item in for_creator.json()["franchises"]] == [
            "Marvel"
        ]
        assert [item["value"] for item in for_creator.json()["series"]] == [
            "X-Men"
        ]
        assert [item["value"] for item in for_creator.json()["models"]] == [
            "Abe Model"
        ]

        for_franchise = client.get("/api/models/filters", params={"franchise": "Ado"})
        assert [item["value"] for item in for_franchise.json()["creators"]] == [
            "Other Creator"
        ]

        for_model = client.get("/api/models/filters", params={"model": "Ado Model"})
        assert [item["value"] for item in for_model.json()["creators"]] == [
            "Other Creator"
        ]
        assert [item["value"] for item in for_model.json()["franchises"]] == [
            "Ado"
        ]
        assert [item["value"] for item in for_model.json()["models"]] == [
            "Abe Model",
            "Ado Model",
        ]


def test_source_scan_defaults_to_smart_and_preserves_requested_modes(tmp_path, monkeypatch) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Mode source", root_path=tmp_path.as_posix(), directory_pattern="{model}",
                archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
            )
            session.add(source)
            session.commit()
            source_id = source.id
        monkeypatch.setattr("meshive.api.scans.dispatch_pending_scans", lambda: None)

        default_response = client.post(f"/api/admin/library-sources/{source_id}/scan")

        assert default_response.status_code == 202
        assert default_response.json()["mode"] == "smart"

        with sessions() as session:
            session.execute(delete(ScanRun))
            session.commit()

        response = client.post(
            f"/api/admin/library-sources/{source_id}/scan",
            json={"mode": "incremental"},
        )

        assert response.status_code == 202
        assert response.json()["mode"] == "incremental"
        scans = client.get(f"/api/admin/library-sources/{source_id}/scans")
        assert scans.status_code == 200
        assert [scan["mode"] for scan in scans.json()] == ["incremental"]

        invalid_response = client.post(
            f"/api/admin/library-sources/{source_id}/scan",
            json={"mode": "unknown"},
        )

        assert invalid_response.status_code == 422


def test_model_rescan_queues_a_targeted_scan(tmp_path, monkeypatch) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Exclusive source",
                root_path=tmp_path.as_posix(),
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Example",
                name="Example",
                status="available",
            )
            session.add(model)
            session.commit()
            model_id = model.id

        monkeypatch.setattr("meshive.services.scanner.dispatch_pending_scans", lambda: None)
        response = client.post(f"/api/admin/models/{model_id}/rescan")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["target_model_id"] == model_id
    assert response.json()["trigger"] == "model_rescan"
    assert response.json()["mode"] == "full"


def test_model_image_rebuild_queues_a_targeted_rebuild(tmp_path, monkeypatch) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Exclusive source",
                root_path=tmp_path.as_posix(),
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Example",
                name="Example",
                status="available",
            )
            session.add(model)
            session.commit()
            model_id = model.id
        monkeypatch.setattr("meshive.services.scanner.dispatch_pending_scans", lambda: None)

        response = client.post(f"/api/admin/models/{model_id}/rebuild-images")

        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        assert response.json()["target_model_id"] == model_id
        assert response.json()["trigger"] == "model_image_rebuild"
        assert response.json()["mode"] == "full"


def test_model_detail_includes_admin_archive_statistics(tmp_path) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Test",
                root_path=tmp_path.as_posix(),
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Cammy",
                name="Cammy",
                status="available",
            )
            session.add(model)
            session.flush()
            archive = Archive(
                model_id=model.id,
                filename="Cammy.7z",
                relative_path="Cammy/Cammy.7z",
                format="7z",
                size_bytes=1024,
                modified_ns=1,
                status="ready",
                entry_count=9,
                uncompressed_size_bytes=2048,
            )
            session.add(archive)
            session.flush()
            session.add_all(
                [
                    ArchiveEntry(archive_id=archive.id, path="preview.jpg", name="preview.jpg", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="preview.webp", name="preview.webp", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="preview.png", name="preview.png", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="decals/preview.jpg", name="preview.jpg", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="model-decal.jpg", name="model-decal.jpg", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="Textures/body.jpg", name="body.jpg", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="parts/body.stl", name="body.stl", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="slicer/Cammy.ctb", name="Cammy.ctb", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="slicer/Cammy.chitubox", name="Cammy.chitubox", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="slicer/Cammy.lys", name="Cammy.lys", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="slicer/Cammy.lychee", name="Cammy.lychee", is_directory=False),
                    ArchiveEntry(archive_id=archive.id, path="parts", name="parts", is_directory=True),
                ]
            )
            session.add_all(
                [
                    ModelImage(
                        model_id=model.id,
                        filename="preview.jpg",
                        relative_path="archive/preview.jpg",
                        storage_kind="archive",
                        format="jpg",
                        size_bytes=100,
                        modified_ns=1,
                        archive_id=archive.id,
                        cache_key="archive-images/preview.jpg.webp",
                    ),
                    ModelImage(
                        model_id=model.id,
                        filename="preview.webp",
                        relative_path="archive/preview.webp",
                        storage_kind="archive",
                        format="webp",
                        size_bytes=100,
                        modified_ns=1,
                        archive_id=archive.id,
                        cache_key="archive-images/preview.webp.webp",
                    ),
                    ModelImage(
                        model_id=model.id,
                        filename="source.jpg",
                        relative_path="Cammy/source.jpg",
                        storage_kind="source",
                        format="jpg",
                        size_bytes=100,
                        modified_ns=1,
                    ),
                ]
            )
            metadata_only_model = LibraryModel(
                library_source_id=source.id,
                relative_path="Metadata only",
                name="Metadata only",
                status="available",
            )
            session.add(metadata_only_model)
            session.flush()
            metadata_archive = Archive(
                model_id=metadata_only_model.id,
                filename="Metadata only.7z",
                relative_path="Metadata only/Metadata only.7z",
                format="7z",
                size_bytes=1024,
                modified_ns=1,
                status="ready",
                entry_count=1,
                uncompressed_size_bytes=4096,
            )
            session.add(metadata_archive)
            session.flush()
            session.add(
                ArchiveEntry(
                    archive_id=metadata_archive.id,
                    path="Akuma_STL/._preview.jpg",
                    name="._preview.jpg",
                    is_directory=False,
                    size_bytes=4096,
                    compressed_size_bytes=256,
                )
            )
            standard_user = User(
                username="Standard user",
                normalized_username="standard user",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=True,
                is_active=True,
            )
            session.add(standard_user)
            session.commit()
            model_id = model.id

        response = client.get(f"/api/models/{model_id}")

        assert response.status_code == 200
        assert response.json()["archive_statistics"] == {
            "image_files": 3,
            "stl_files": 1,
            "chitubox_files": 2,
            "lychee_files": 2,
            "exported_images": 2,
        }
        assert response.json()["images"][0]["url"].endswith(
            "?v=archive-images%2Fpreview.jpg.webp"
        )

        mismatch_filter = client.get("/api/models/filters")
        assert mismatch_filter.status_code == 200
        assert {
            "value": "archive_images_mismatch",
            "count": 1,
        } in mismatch_filter.json()["statuses"]

        mismatch_models = client.get(
            "/api/models", params={"status": "archive_images_mismatch"}
        )
        assert mismatch_models.status_code == 200
        assert mismatch_models.json()["total"] == 1
        assert mismatch_models.json()["items"][0]["id"] == model_id

        app.dependency_overrides[get_current_user] = lambda: standard_user
        standard_user_response = client.get(f"/api/models/{model_id}")

        assert standard_user_response.status_code == 200
        assert standard_user_response.json()["archive_statistics"] is None
        assert client.get(
            "/api/models", params={"status": "archive_images_mismatch"}
        ).status_code == 403


def test_model_detail_includes_recent_scan_issues(tmp_path) -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source = LibrarySource(
                name="Test",
                root_path=tmp_path.as_posix(),
                directory_pattern="{model}",
                archive_formats=["7z"],
                image_formats=["jpg"],
            )
            session.add(source)
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Cammy",
                name="Cammy",
                status="available",
            )
            session.add(model)
            session.flush()
            scan = ScanRun(library_source_id=source.id, status="completed", mode="full")
            session.add(scan)
            session.flush()
            session.add_all(
                [
                    ScanIssue(
                        scan_run_id=scan.id,
                        model_id=model.id,
                        relative_path=model.relative_path,
                        severity="warning",
                        code="archive_image_batch_failed",
                        message="Image extraction exceeded the configured limit",
                    ),
                    ScanIssue(
                        scan_run_id=scan.id,
                        model_id=model.id,
                        relative_path=model.relative_path,
                        severity="warning",
                        code="archive_image_failed",
                        message="Image data is not valid",
                    ),
                ]
            )
            standard_user = User(
                username="Standard user",
                normalized_username="standard user",
                password_hash="unused",
                role="user",
                role_definition=get_system_role_for_legacy_role(session, "user"),
                all_sources=True,
                is_active=True,
            )
            session.add(standard_user)
            session.commit()
            model_id = model.id

        response = client.get(f"/api/models/{model_id}")

        assert response.status_code == 200
        issues = response.json()["recent_scan_issues"]
        assert [issue["code"] for issue in issues] == [
            "archive_image_failed",
            "archive_image_batch_failed",
        ]
        assert [issue["message"] for issue in issues] == [
            "Image data is not valid",
            "Image extraction exceeded the configured limit",
        ]
        assert all(issue["created_at"] for issue in issues)

        app.dependency_overrides[get_current_user] = lambda: standard_user
        standard_user_response = client.get(f"/api/models/{model_id}")

        assert standard_user_response.status_code == 200
        assert standard_user_response.json()["recent_scan_issues"] == []

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1,
            role="admin",
            role_id=None,
            role_definition=SimpleNamespace(is_superuser=True),
            all_sources=True,
        )
        cleared = client.delete(f"/api/admin/models/{model_id}/scan-issues")

        assert cleared.status_code == 200
        assert cleared.json() == {"deleted": 2}
        assert client.get(f"/api/models/{model_id}").json()["recent_scan_issues"] == []


def test_admin_model_actions_are_scoped_by_source_and_permission(monkeypatch) -> None:
    monkeypatch.setattr("meshive.services.scanner.dispatch_pending_scans", lambda: None)
    with catalog_client() as (client, sessions):
        with sessions() as session:
            permissions = {
                CATALOGUE_VIEW,
                CATALOGUE_VIEW_MAINTENANCE,
                MODELS_DELETE_MISSING,
                MODELS_PRIMARY_IMAGE,
                MODELS_REBUILD_IMAGES,
                MODELS_RESCAN,
                MODELS_RESET_IMAGES,
            }
            operator = Role(name="Model operator", normalized_name="model operator")
            session.add(operator)
            session.flush()
            session.add_all(
                [RolePermission(role_id=operator.id, permission_key=permission) for permission in permissions]
            )
            source_a = LibrarySource(name="Source A", root_path="/a", directory_pattern="{model}")
            source_b = LibrarySource(name="Source B", root_path="/b", directory_pattern="{model}")
            a_only = User(
                username="A only", normalized_username="a only", password_hash="unused",
                role="user", role_definition=operator, all_sources=False,
            )
            all_sources = User(
                username="All sources", normalized_username="all sources", password_hash="unused",
                role="user", role_definition=operator, all_sources=True,
            )
            viewer = User(
                username="Viewer", normalized_username="viewer", password_hash="unused",
                role="user", role_definition=Role(name="Viewer", normalized_name="viewer"),
                all_sources=False,
            )
            no_grant = User(
                username="No grant", normalized_username="no grant", password_hash="unused",
                role="user", role_definition=operator, all_sources=False,
            )
            session.add_all([source_a, source_b, a_only, all_sources, viewer, no_grant])
            session.flush()
            models_a = {
                name: LibraryModel(
                    library_source_id=source_a.id,
                    relative_path=name,
                    name=name,
                    status="missing" if name == "missing-a" else "available",
                )
                for name in ("primary-a", "rescan-a", "rebuild-a", "reset-a", "issues-a", "missing-a")
            }
            model_b = LibraryModel(
                library_source_id=source_b.id,
                relative_path="hidden-b",
                name="hidden-b",
                status="missing",
            )
            session.add_all([*models_a.values(), model_b])
            session.flush()
            primary_a = ModelImage(
                model_id=models_a["primary-a"].id, filename="primary-a.jpg",
                relative_path="primary-a.jpg", format="jpg", size_bytes=1, modified_ns=1,
            )
            reset_a = ModelImage(
                model_id=models_a["reset-a"].id, filename="reset-a.jpg",
                relative_path="reset-a.jpg", format="jpg", size_bytes=1, modified_ns=1,
            )
            primary_b = ModelImage(
                model_id=model_b.id, filename="hidden-b.jpg", relative_path="hidden-b.jpg",
                format="jpg", size_bytes=1, modified_ns=1,
            )
            scan = ScanRun(library_source_id=source_a.id, status="completed", mode="full")
            session.add_all([primary_a, reset_a, primary_b, scan])
            session.flush()
            session.add(ScanIssue(
                scan_run_id=scan.id, model_id=models_a["issues-a"].id,
                relative_path="issues-a", severity="warning", code="test", message="test issue",
            ))
            session.add(UserLibrarySource(user_id=a_only.id, library_source_id=source_a.id))
            session.add(UserLibrarySource(user_id=viewer.id, library_source_id=source_a.id))
            session.commit()
            model_ids = {name: model.id for name, model in models_a.items()}
            model_b_id, primary_a_id, primary_b_id = model_b.id, primary_a.id, primary_b.id

        app.dependency_overrides[get_current_user] = lambda: a_only
        maintenance = client.get("/api/models", params={"status": "missing"})
        assert maintenance.status_code == 200
        assert maintenance.json()["total"] == 1
        assert [item["id"] for item in maintenance.json()["items"]] == [model_ids["missing-a"]]
        filters = client.get("/api/models/filters", params={"status": "missing"})
        assert {source["id"] for source in filters.json()["sources"]} == {source_a.id}
        assert client.put(f"/api/admin/models/{model_ids['primary-a']}/images/{primary_a_id}/primary").status_code == 200
        assert client.post(f"/api/admin/models/{model_ids['rescan-a']}/rescan").status_code == 202
        assert client.post(f"/api/admin/models/{model_ids['rebuild-a']}/rebuild-images").status_code == 202
        assert client.delete(f"/api/admin/models/{model_ids['issues-a']}/scan-issues").json() == {"deleted": 1}
        assert client.delete(f"/api/admin/models/{model_ids['reset-a']}/images").json() == {"deleted": 1}
        assert client.put(f"/api/admin/models/{model_b_id}/images/{primary_b_id}/primary").status_code == 404
        assert client.post(f"/api/admin/models/{model_b_id}/rescan").status_code == 404
        assert client.post(f"/api/admin/models/{model_b_id}/rebuild-images").status_code == 404
        assert client.delete(f"/api/admin/models/{model_b_id}/scan-issues").status_code == 404
        assert client.delete(f"/api/admin/models/{model_b_id}/images").status_code == 404
        assert client.delete(f"/api/admin/models/{model_b_id}").status_code == 404

        app.dependency_overrides[get_current_user] = lambda: viewer
        assert client.get("/api/models", params={"status": "missing"}).status_code == 403
        assert client.put(f"/api/admin/models/{model_ids['primary-a']}/images/{primary_a_id}/primary").status_code == 403
        assert client.post(f"/api/admin/models/{model_ids['rescan-a']}/rescan").status_code == 403
        assert client.post(f"/api/admin/models/{model_ids['rebuild-a']}/rebuild-images").status_code == 403
        assert client.delete(f"/api/admin/models/{model_ids['issues-a']}/scan-issues").status_code == 403
        assert client.delete(f"/api/admin/models/{model_ids['reset-a']}/images").status_code == 403
        assert client.delete(f"/api/admin/models/{model_ids['missing-a']}").status_code == 403
        assert client.put(f"/api/admin/models/{model_b_id}/images/{primary_b_id}/primary").status_code == 404

        app.dependency_overrides[get_current_user] = lambda: no_grant
        assert client.post(f"/api/admin/models/{model_ids['rescan-a']}/rescan").status_code == 404
        assert client.delete("/api/admin/models/missing").json() == {"deleted": 0}

        app.dependency_overrides[get_current_user] = lambda: a_only
        assert client.delete("/api/admin/models/missing").json() == {"deleted": 1}

        with sessions() as session:
            hidden_image = session.get(ModelImage, primary_b_id)
            assert hidden_image is not None
            assert hidden_image.is_primary is False
            assert session.get(LibraryModel, model_b_id) is not None
            assert session.scalar(
                select(ScanRun.id).where(ScanRun.library_source_id == source_b.id)
            ) is None

        app.dependency_overrides[get_current_user] = lambda: all_sources
        assert client.put(f"/api/admin/models/{model_b_id}/images/{primary_b_id}/primary").status_code == 200

        with sessions() as session:
            assert session.get(LibraryModel, model_b_id) is not None
            assert session.get(LibraryModel, model_ids["missing-a"]) is None
            assert session.get(ModelImage, primary_b_id) is not None
