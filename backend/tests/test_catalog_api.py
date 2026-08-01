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
from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel
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
            "model_id UNINDEXED, name, creator, franchise, series, collection, tags)"
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
                    "model_id, name, creator, franchise, series, collection, tags"
                    ") VALUES (:id, :name, :creator, :franchise, :series, '', '')"
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
