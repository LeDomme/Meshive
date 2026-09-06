import tracemalloc

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from meshive.archives.sevenzip_cli import ListedArchiveEntry
from meshive.config import Settings, get_settings
from meshive.database import Base
from meshive.models.catalog import (
    Archive,
    ArchiveBrowseNode,
    ArchiveEntry,
    LibraryModel,
    ScanRun,
)
from meshive.models.library_source import LibrarySource
from meshive.services import scanner
from meshive.services.archive_browse import rebuild_archive_browse_nodes


def _archive(session: Session) -> Archive:
    source = LibrarySource(name="Source", root_path="/models", directory_pattern="{model}")
    session.add(source)
    session.flush()
    model = LibraryModel(
        library_source_id=source.id,
        relative_path="Model",
        name="Model",
        status="available",
    )
    session.add(model)
    session.flush()
    archive = Archive(
        model_id=model.id,
        filename="model.zip",
        relative_path="Model/model.zip",
        format="zip",
        size_bytes=1,
        modified_ns=1,
        status="ready",
        entry_count=0,
        uncompressed_size_bytes=0,
    )
    session.add(archive)
    session.flush()
    return archive


def test_browse_nodes_add_synthetic_folders_and_preserve_physical_entries(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'nodes.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        archive = _archive(session)
        session.add_all(
            [
                ArchiveEntry(
                    archive_id=archive.id,
                    path="deep/inner/file.stl",
                    name="file.stl",
                    is_directory=False,
                ),
                ArchiveEntry(
                    archive_id=archive.id,
                    path="explicit",
                    name="explicit",
                    is_directory=True,
                ),
                ArchiveEntry(
                    archive_id=archive.id,
                    path="unicode\\Ärger\\same.stl",
                    name="same.stl",
                    is_directory=False,
                ),
                ArchiveEntry(
                    archive_id=archive.id,
                    path="other/same.stl",
                    name="same.stl",
                    is_directory=False,
                ),
            ]
        )
        session.flush()
        rebuild_archive_browse_nodes(session, archive.id)
        nodes = {
            node.path: node
            for node in session.scalars(
                select(ArchiveBrowseNode).where(ArchiveBrowseNode.archive_id == archive.id)
            )
        }

        assert set(nodes) == {
            "deep",
            "deep/inner",
            "deep/inner/file.stl",
            "explicit",
            "unicode",
            "unicode/Ärger",
            "unicode/Ärger/same.stl",
            "other",
            "other/same.stl",
        }
        assert nodes["deep"].archive_entry_id is None
        assert nodes["deep"].parent_path == ""
        assert nodes["deep/inner"].depth == 2
        assert nodes["explicit"].archive_entry_id is not None
        assert nodes["unicode/Ärger"].name_sort_key == "ärger"
        assert nodes["unicode/Ärger/same.stl"].parent_path == "unicode/Ärger"


def test_browse_node_rebuild_is_idempotent_and_bounded(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'large.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        archive = _archive(session)
        session.add_all(
            [
                ArchiveEntry(
                    archive_id=archive.id,
                    path=f"folder-{index // 100}/file-{index:05}.stl",
                    name=f"file-{index:05}.stl",
                    is_directory=False,
                )
                for index in range(10_000)
            ]
        )
        session.flush()
        tracemalloc.start()
        rebuild_archive_browse_nodes(session, archive.id, batch_size=100)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        first_count = session.scalar(
            select(text("count(*)")).select_from(ArchiveBrowseNode)
        )
        rebuild_archive_browse_nodes(session, archive.id, batch_size=100)
        second_count = session.scalar(
            select(text("count(*)")).select_from(ArchiveBrowseNode)
        )

        assert first_count == 10_100
        assert second_count == first_count
        assert peak < 32 * 1024 * 1024


def test_archive_browse_node_migration_upgrade_downgrade_upgrade(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "browse-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260910_38")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO library_sources (name, root_path, directory_pattern, "
                    "archive_formats, image_formats, is_active, scan_enabled) "
                    "VALUES ('Source', '/models', '{model}', '[\"zip\"]', '[\"jpg\"]', 1, 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO library_models (library_source_id, relative_path, name, status) "
                    "VALUES (1, 'Model', 'Model', 'available')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO archives (model_id, filename, relative_path, format, size_bytes, "
                    "modified_ns, status, entry_count, uncompressed_size_bytes) "
                    "VALUES (1, 'model.zip', 'Model/model.zip', 'zip', 1, 1, 'ready', 1, 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO archive_entries (archive_id, path, name, is_directory) "
                    "VALUES (1, 'nested/file.stl', 'file.stl', 0)"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM archive_browse_nodes")).scalar() == 2
        engine.dispose()

        command.downgrade(config, "20260910_38")
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM archive_browse_nodes")).scalar() == 2
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_rescan_replaces_stale_browse_nodes(tmp_path, monkeypatch) -> None:
    archive_path = tmp_path / "model.zip"
    archive_path.write_bytes(b"first")
    engine = create_engine(f"sqlite:///{tmp_path / 'rescan.sqlite3'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path))
    listings = iter(
        [
            [
                ListedArchiveEntry(
                    path="old/file.stl",
                    name="file.stl",
                    is_directory=False,
                    size_bytes=1,
                    compressed_size_bytes=1,
                    crc=None,
                    modified_at=None,
                )
            ],
            [
                ListedArchiveEntry(
                    path="new/file.stl",
                    name="file.stl",
                    is_directory=False,
                    size_bytes=2,
                    compressed_size_bytes=2,
                    crc=None,
                    modified_at=None,
                )
            ],
        ]
    )
    monkeypatch.setattr(scanner, "list_archive", lambda *_args, **_kwargs: next(listings))
    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Source",
            root_path=tmp_path.as_posix(),
            directory_pattern="{model}",
            archive_formats=["zip"],
            image_formats=["jpg"],
            is_active=True,
            scan_enabled=True,
        )
        session.add(source)
        session.flush()
        model = LibraryModel(
            library_source_id=source.id,
            relative_path="Model",
            name="Model",
            status="available",
        )
        scan = ScanRun(library_source_id=source.id, status="running", mode="full")
        session.add_all([model, scan])
        session.flush()
        assert scanner._sync_archive(session, scan, model, tmp_path, archive_path)
        session.commit()
        archive_path.write_bytes(b"second listing")
        assert scanner._sync_archive(session, scan, model, tmp_path, archive_path)
        session.commit()

        assert [node.path for node in session.scalars(select(ArchiveBrowseNode))] == [
            "new",
            "new/file.stl",
        ]
        assert scanner._sync_archives(session, scan, model, tmp_path, [])
        assert list(session.scalars(select(ArchiveBrowseNode))) == []
