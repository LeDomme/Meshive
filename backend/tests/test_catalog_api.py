import tarfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.auth.dependencies import get_current_user
from meshive.database import Base, get_session
from meshive.main import app
from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel, ModelImage, ScanIssue, ScanRun
from meshive.models.library_source import LibrarySource


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
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
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

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        standard_user_response = client.get(f"/api/models/{model_id}")

        assert standard_user_response.status_code == 200
        assert standard_user_response.json()["recent_scan_issues"] == []

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
        cleared = client.delete(f"/api/admin/models/{model_id}/scan-issues")

        assert cleared.status_code == 200
        assert cleared.json() == {"deleted": 2}
        assert client.get(f"/api/models/{model_id}").json()["recent_scan_issues"] == []
