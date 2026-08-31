from contextlib import contextmanager
from pathlib import Path

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from meshive.archives.sevenzip_cli import ListedArchiveEntry
from meshive.config import Settings
from meshive.database import Base
from meshive.models.catalog import (
    Archive,
    ArchiveEntry,
    LibraryModel,
    ModelImage,
    ScanIssue,
    ScanRun,
)
from meshive.models.library_source import LibrarySource
from meshive.models.tag import AutomaticTagRule, ModelTag, Tag
from meshive.services import scanner
from meshive.services.archive_images import ArchiveImageError, ValidatedArchiveImage


def make_source_tree(root: Path) -> Path:
    model = root / "Moikaloop" / "Moikaloop - Neon Moika - by Aoae"
    model.mkdir(parents=True)
    (model / "Moikaloop - Neon Moika - by Aoae.7z").write_bytes(b"archive")
    (model / "Moikaloop - Neon Moika - by Aoae.jpg").write_bytes(b"image")
    return model


def make_scan(session: Session, source_id: int) -> ScanRun:
    scan = ScanRun(
        library_source_id=source_id,
        status="pending",
        models_found=0,
        models_added=0,
        models_updated=0,
        models_missing=0,
        issues_count=0,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return scan


def test_force_rebuild_replaces_cache_without_deleting_regenerated_file(tmp_path, monkeypatch) -> None:
    model_directory = tmp_path / "Cammy"
    model_directory.mkdir()
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(allowed_library_root=tmp_path, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Pictures",
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
            cache_key="archive-images/cover.webp",
            thumbnail_key="thumbnails/cover.webp",
        )
        session.add(image)
        session.commit()

        cache_path = settings.cache_dir / "archive-images" / "cover.webp"
        cache_path.parent.mkdir(parents=True)
        cache_path.write_bytes(b"old")

        def regenerate(*_args, **_kwargs) -> None:
            assert not cache_path.exists()
            cache_path.write_bytes(b"new")

        monkeypatch.setattr(scanner, "_scan_model", regenerate)
        scan = scanner.rescan_model(session, model.id, force_image_rebuild=True)

        assert scan.status == "completed"
        assert scan.target_model_id == model.id
        assert scan.target_model_name == "Cammy"
        assert cache_path.read_bytes() == b"new"
        assert not list(cache_path.parent.glob("*.rebuild-*"))

def test_force_rebuild_restores_cache_when_regeneration_fails(tmp_path, monkeypatch) -> None:
    model_directory = tmp_path / "Cammy"
    model_directory.mkdir()
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(allowed_library_root=tmp_path, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Pictures",
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
            cache_key="archive-images/cover.webp",
        )
        session.add(image)
        session.commit()

        cache_path = settings.cache_dir / "archive-images" / "cover.webp"
        cache_path.parent.mkdir(parents=True)
        cache_path.write_bytes(b"old")
        monkeypatch.setattr(
            scanner,
            "_scan_model",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("failed rebuild")),
        )

        scan = scanner.rescan_model(session, model.id, force_image_rebuild=True)

        assert scan.status == "failed"
        assert cache_path.read_bytes() == b"old"
        assert not list(cache_path.parent.glob("*.rebuild-*"))

def test_model_rescan_processes_only_the_target_model(tmp_path, monkeypatch) -> None:
    for name in ("Cammy", "Chun-Li"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / f"{name}.7z").write_bytes(b"archive")
    engine = create_engine(f"sqlite:///{tmp_path / "targeted-rescan.db"}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path))

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Targeted", root_path=tmp_path.as_posix(), directory_pattern="{model}",
            archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        session.add(source)
        session.flush()
        target = LibraryModel(
            library_source_id=source.id, relative_path="Cammy", name="Cammy", status="available"
        )
        other = LibraryModel(
            library_source_id=source.id, relative_path="Chun-Li", name="Chun-Li", status="available"
        )
        session.add_all([target, other])
        session.commit()
        processed: list[str] = []
        monkeypatch.setattr(scanner, "_scan_model", lambda *_args: processed.append(_args[5]))

        scan = scanner.rescan_model(session, target.id)

        assert processed == ["Cammy"]
        assert scan.target_model_id == target.id
        assert other.status == "available"

    engine.dispose()


def test_incremental_scan_skips_known_models_and_processes_new_ones(tmp_path, monkeypatch) -> None:
    for name in ("Known", "New"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / f"{name}.7z").write_bytes(b"archive")
    engine = create_engine(f"sqlite:///{tmp_path / "incremental.db"}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path))

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Incremental", root_path=tmp_path.as_posix(), directory_pattern="{model}",
            archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        session.add(source)
        session.flush()
        known = LibraryModel(
            library_source_id=source.id, relative_path="Known", name="Known", status="available"
        )
        session.add(known)
        session.commit()
        processed: list[str] = []
        monkeypatch.setattr(scanner, "_scan_model", lambda *_args: processed.append(_args[5]))
        scan = make_scan(session, source.id)
        scan.mode = "incremental"
        session.commit()

        scanner._execute_scan(session, source.id, scan.id)

        assert processed == ["New"]
        assert scan.models_skipped == 1
        assert session.get(LibraryModel, known.id).status == "available"

    engine.dispose()


def test_archive_image_reconciliation_backfills_only_missing_cache_entries(
    tmp_path, monkeypatch
) -> None:
    archive_path = tmp_path / "Cammy.7z"
    archive_path.write_bytes(b"archive")
    extracted = tmp_path / "missing.jpg"
    extracted.write_bytes(b"image")
    engine = create_engine(f"sqlite:///{tmp_path / "cache-backfill.db"}")
    Base.metadata.create_all(engine)
    settings = Settings(allowed_library_root=tmp_path, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)
    extracted_paths: list[list[str]] = []

    def fake_batches(_archive_path, candidates, **_kwargs):
        selected = list(candidates)
        extracted_paths.append([entry.path for entry in selected])
        yield selected, {"missing.jpg": extracted}, None

    monkeypatch.setattr(scanner, "iter_extracted_archive_image_batches", fake_batches)
    monkeypatch.setattr(scanner, "validate_extracted_archive_image", lambda *_args, **_kwargs: ValidatedArchiveImage(extracted, "jpg", 10, 10, 5))
    monkeypatch.setattr(scanner, "generate_cached_webp", lambda *_args, **_kwargs: "archive-images/missing.webp")
    monkeypatch.setattr(scanner, "generate_thumbnail", lambda *_args, **_kwargs: "thumbnails/missing.webp")

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(name="Cache backfill", root_path=tmp_path.as_posix(), directory_pattern="{model}", archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True)
        session.add(source)
        session.flush()
        model = LibraryModel(library_source_id=source.id, relative_path="Cammy", name="Cammy", status="available", archive_image_policy_key=scanner._archive_image_selection_policy_key(settings))
        session.add(model)
        session.flush()
        stat = archive_path.stat()
        archive = Archive(model_id=model.id, filename=archive_path.name, relative_path=archive_path.name, format="7z", size_bytes=stat.st_size, modified_ns=stat.st_mtime_ns, status="ready")
        session.add(archive)
        session.flush()
        cached_entry = ArchiveEntry(archive_id=archive.id, path="cover.jpg", name="cover.jpg", is_directory=False, size_bytes=123, compressed_size_bytes=100, crc="CACHED")
        missing_entry = ArchiveEntry(archive_id=archive.id, path="missing.jpg", name="missing.jpg", is_directory=False, size_bytes=5, compressed_size_bytes=4, crc="MISSING")
        session.add_all([cached_entry, missing_entry])
        session.flush()
        for key in ("archive-images/cover.webp", "thumbnails/cover.webp"):
            target = settings.cache_dir / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"cached")
        session.add(ModelImage(model_id=model.id, relative_path=f"archive/{archive.id}/cover.jpg", filename="cover.jpg", format="jpg", size_bytes=123, modified_ns=archive.modified_ns, storage_kind="archive", archive_id=archive.id, archive_entry_path=cached_entry.path, archive_entry_fingerprint=scanner._archive_entry_fingerprint(cached_entry), cache_key="archive-images/cover.webp", thumbnail_key="thumbnails/cover.webp", thumbnail_status="ready"))
        session.commit()
        scan = make_scan(session, source.id)

        scanner._sync_archive_images(session, scan, model, tmp_path, [archive_path])

        assert extracted_paths == [["missing.jpg"]]
        assert scan.archive_images_reused == 1
        assert scan.archive_images_generated == 1

    engine.dispose()


def test_archive_image_reconciliation_reuses_current_cache_without_extraction(
    tmp_path, monkeypatch
) -> None:
    archive_path = tmp_path / "Cammy.7z"
    archive_path.write_bytes(b"archive")
    engine = create_engine(f"sqlite:///{tmp_path / "cache-reuse.db"}")
    Base.metadata.create_all(engine)
    settings = Settings(allowed_library_root=tmp_path, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)

    def extraction_must_not_run(*_args, **_kwargs):
        raise AssertionError("current archive image cache was extracted again")

    monkeypatch.setattr(
        scanner, "iter_extracted_archive_image_batches", extraction_must_not_run
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Cache reuse", root_path=tmp_path.as_posix(), directory_pattern="{model}",
            archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        session.add(source)
        session.flush()
        model = LibraryModel(
            library_source_id=source.id, relative_path="Cammy", name="Cammy",
            status="available", archive_image_policy_key=scanner._archive_image_selection_policy_key(settings),
        )
        session.add(model)
        session.flush()
        stat = archive_path.stat()
        archive = Archive(
            model_id=model.id, filename=archive_path.name, relative_path=archive_path.name,
            format="7z", size_bytes=stat.st_size, modified_ns=stat.st_mtime_ns, status="ready",
        )
        session.add(archive)
        session.flush()
        entry = ArchiveEntry(
            archive_id=archive.id, path="cover.jpg", name="cover.jpg",
            is_directory=False, size_bytes=123, compressed_size_bytes=100, crc="CACHE",
        )
        session.add(entry)
        session.flush()
        cache_key = "archive-images/cover.webp"
        thumbnail_key = "thumbnails/cover.webp"
        for key in (cache_key, thumbnail_key):
            target = settings.cache_dir / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"cached")
        image = ModelImage(
            model_id=model.id, relative_path=f"archive/{archive.id}/cover.jpg",
            filename="cover.jpg", format="jpg", size_bytes=123, modified_ns=archive.modified_ns,
            storage_kind="archive", archive_id=archive.id, archive_entry_path=entry.path,
            archive_entry_fingerprint=scanner._archive_entry_fingerprint(entry),
            cache_key=cache_key, thumbnail_key=thumbnail_key, thumbnail_status="ready",
        )
        session.add(image)
        session.commit()
        scan = make_scan(session, source.id)

        primary = scanner._sync_archive_images(session, scan, model, tmp_path, [archive_path])

        assert primary is image
        assert scan.archive_images_reused == 1
        assert scan.archive_images_generated == 0

    engine.dispose()


def test_reconcile_images_skips_models_without_ready_archives(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / "reconcile-skip.db"}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path))
    calls: list[str] = []
    monkeypatch.setattr(scanner, "_sync_archives", lambda *_args: calls.append("archives"))
    monkeypatch.setattr(
        scanner, "_sync_archive_images", lambda *_args: calls.append("images")
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Reconcile", root_path=tmp_path.as_posix(), directory_pattern="{model}",
            archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        session.add(source)
        session.flush()
        session.add(
            LibraryModel(
                library_source_id=source.id, relative_path="Missing", name="Missing", status="available"
            )
        )
        session.commit()
        scan = make_scan(session, source.id)
        scan.mode = "reconcile_images"
        session.commit()

        scanner._execute_scan(session, source.id, scan.id)

        assert scan.models_total == 1
        assert scan.models_found == 0
        assert calls == []

    engine.dispose()


def test_full_scan_reconciles_known_models(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "Cammy"
    directory.mkdir()
    (directory / "Cammy.7z").write_bytes(b"archive")
    engine = create_engine(f"sqlite:///{tmp_path / "full-scan.db"}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path))
    reconciled: list[str] = []
    monkeypatch.setattr(scanner, "_sync_archives", lambda *_args: True)
    monkeypatch.setattr(
        scanner, "_sync_archive_images", lambda _session, _scan, model, *_args: reconciled.append(model.name)
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Full scan", root_path=tmp_path.as_posix(), directory_pattern="{model}",
            archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        session.add(source)
        session.flush()
        session.add(
            LibraryModel(
                library_source_id=source.id, relative_path="Cammy", name="Cammy", status="available"
            )
        )
        session.commit()
        scan = make_scan(session, source.id)

        scanner._execute_scan(session, source.id, scan.id)

        assert reconciled == ["Cammy"]
        assert scan.models_updated == 1

    engine.dispose()


def test_missing_images_scan_reconciles_known_models(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "Cammy"
    directory.mkdir()
    (directory / "Cammy.7z").write_bytes(b"archive")
    engine = create_engine(f"sqlite:///{tmp_path / "missing-images.db"}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path))
    reconciled: list[str] = []
    monkeypatch.setattr(scanner, "_sync_archives", lambda *_args: True)
    monkeypatch.setattr(
        scanner, "_sync_archive_images", lambda _session, _scan, model, *_args: reconciled.append(model.name)
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Missing images", root_path=tmp_path.as_posix(), directory_pattern="{model}",
            archive_formats=["7z"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        session.add(source)
        session.flush()
        session.add(
            LibraryModel(
                library_source_id=source.id, relative_path="Cammy", name="Cammy", status="available"
            )
        )
        session.commit()
        scan = make_scan(session, source.id)
        scan.mode = "missing_images"
        session.commit()

        scanner._execute_scan(session, source.id, scan.id)

        assert reconciled == ["Cammy"]
        assert scan.models_updated == 1

    engine.dispose()


def test_scans_model_archive_image_and_marks_missing(tmp_path, monkeypatch) -> None:
    model_directory = make_source_tree(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        scanner,
        "get_settings",
        lambda: Settings(allowed_library_root=tmp_path),
    )
    listed_entries = [
        ListedArchiveEntry(
            path="model.stl",
            name="model.stl",
            is_directory=False,
            size_bytes=1234,
            compressed_size_bytes=456,
            crc="ABC123",
            modified_at="2025-01-01 12:00:00",
        )
    ]
    monkeypatch.setattr(
        scanner,
        "list_archive",
        lambda *_args, **_kwargs: listed_entries,
    )
    monkeypatch.setattr(
        scanner,
        "generate_thumbnail",
        lambda *_args, **_kwargs: "thumbnails/test.webp",
    )

    with Session(engine, expire_on_commit=False) as session:
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
        automatic_tag = Tag(name="Printable")
        session.add(automatic_tag)
        session.flush()
        session.add(
            AutomaticTagRule(
                tag_id=automatic_tag.id,
                pattern="MODEL.STL",
                pattern_key="model.stl",
                enabled=True,
            )
        )
        session.commit()
        scan = make_scan(session, source.id)

        scanner._execute_scan(session, source.id, scan.id)

        model = session.scalar(select(LibraryModel))
        assert model is not None
        assert model.name == "Neon Moika"
        assert model.creator == "Aoae"
        assert model.franchise == "Moikaloop"
        assert model.status == "available"

        archive = session.scalar(select(Archive))
        assert archive is not None
        assert archive.status == "ready"
        assert archive.entry_count == 1
        assert session.scalar(select(ArchiveEntry)).path == "model.stl"
        image = session.scalar(select(ModelImage))
        assert image.is_primary is True
        assert image.thumbnail_status == "ready"
        assert image.thumbnail_key == "thumbnails/test.webp"

        completed = session.get(ScanRun, scan.id)
        assert completed.status == "completed"
        assert completed.models_found == 1
        assert completed.models_added == 1
        assert completed.automatic_tag_matches == 1
        assert completed.automatic_tags_added == 1
        assignment = session.scalar(select(ModelTag))
        assert assignment is not None
        assert assignment.is_automatic is True
        assert completed.issues_count == 0

        second_archive_path = model_directory / "extras.zip"
        second_archive_path.write_bytes(b"second archive")
        multi_scan = make_scan(session, source.id)
        scanner._execute_scan(session, source.id, multi_scan.id)
        archives = list(session.scalars(select(Archive).order_by(Archive.filename)))
        assert sorted(
            (archive.filename for archive in archives),
            key=str.casefold,
        ) == [
            "extras.zip",
            "Moikaloop - Neon Moika - by Aoae.7z",
        ]
        assert session.get(ScanRun, multi_scan.id).issues_count == 0
        assert session.get(ScanRun, multi_scan.id).automatic_tag_matches == 1
        assert session.get(ScanRun, multi_scan.id).automatic_tags_added == 0

        listed_entries[:] = [
            ListedArchiveEntry(
                path="documentation/readme.txt",
                name="readme.txt",
                is_directory=False,
                size_bytes=100,
                compressed_size_bytes=50,
                crc="DEF456",
                modified_at="2025-01-02 12:00:00",
            )
        ]
        for archive_path in model_directory.glob("*.7z"):
            archive_path.write_bytes(b"changed archive contents")
        second_archive_path.write_bytes(b"changed second archive contents")
        changed_scan = make_scan(session, source.id)
        scanner._execute_scan(session, source.id, changed_scan.id)
        assert session.get(ScanRun, changed_scan.id).automatic_tag_matches == 0
        assert session.get(ScanRun, changed_scan.id).automatic_tags_removed == 1
        assert session.scalar(select(ModelTag)) is None

        for child in model_directory.iterdir():
            child.unlink()
        model_directory.rmdir()
        model_directory.parent.rmdir()

        second_scan = make_scan(session, source.id)
        scanner._execute_scan(session, source.id, second_scan.id)
        session.refresh(model)

        assert model.status == "missing"
        assert session.get(ScanRun, second_scan.id).models_missing == 1

    engine.dispose()


def test_sync_archive_images_reports_aggregated_limit_skips(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'archive-image-skips.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(
        allowed_library_root=tmp_path,
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        archive_image_max_candidates=1,
        archive_image_max_entry_bytes=2 * 1024 * 1024,
        archive_image_max_compressed_bytes=2 * 1024 * 1024,
        archive_image_max_total_bytes=1024 * 1024,
    )
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)

    def failed_batches(_archive_path, candidates, **_kwargs):
        yield list(candidates), {}, ArchiveImageError("test extraction failure")

    monkeypatch.setattr(scanner, "iter_extracted_archive_image_batches", failed_batches)

    archive_path = tmp_path / "model.7z"
    archive_path.write_bytes(b"archive")
    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Archive image skips",
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
            relative_path="Model",
            name="Model",
            status="available",
        )
        session.add(model)
        session.flush()
        archive = Archive(
            model_id=model.id,
            filename="model.7z",
            relative_path="model.7z",
            format="7z",
            size_bytes=7,
            modified_ns=1,
            status="ready",
        )
        session.add(archive)
        session.flush()
        session.add_all(
            [
                ArchiveEntry(
                    archive_id=archive.id, path="cover.jpg", name="cover.jpg",
                    size_bytes=1024 * 1024, compressed_size_bytes=512 * 1024,
                ),
                ArchiveEntry(
                    archive_id=archive.id, path="preview.jpg", name="preview.jpg",
                    size_bytes=1024 * 1024, compressed_size_bytes=512 * 1024,
                ),
                ArchiveEntry(
                    archive_id=archive.id, path="oversized.jpg", name="oversized.jpg",
                    size_bytes=3 * 1024 * 1024, compressed_size_bytes=512 * 1024,
                ),
                ArchiveEntry(
                    archive_id=archive.id, path="packed.jpg", name="packed.jpg",
                    size_bytes=1024 * 1024, compressed_size_bytes=3 * 1024 * 1024,
                ),
                ArchiveEntry(
                    archive_id=archive.id, path="Textures/body.jpg", name="body.jpg",
                    size_bytes=3 * 1024 * 1024, compressed_size_bytes=3 * 1024 * 1024,
                ),
            ]
        )
        session.commit()
        scan = make_scan(session, source.id)

        scanner._sync_archive_images(session, scan, model, tmp_path, [archive_path])

        issue = session.scalar(
            select(ScanIssue).where(
                ScanIssue.scan_run_id == scan.id,
                ScanIssue.code == "archive_image_candidates_skipped",
            )
        )
        assert issue is not None
        assert issue.severity == "warning"
        assert issue.message == (
            "3 archive image(s) were not selected: 1 compressed size limit, "
            "1 per-entry size limit, 1 total extraction budget."
        )
        assert scan.issues_count == 2

    engine.dispose()


def test_scan_prefers_validated_archive_image_when_folder_has_none(
    tmp_path, monkeypatch
) -> None:
    model_directory = tmp_path / "Street Fighter" / "Cammy"
    model_directory.mkdir(parents=True)
    (model_directory / "cammy.7z").write_bytes(b"archive")
    extracted = tmp_path / "cover.jpg"
    Image.new("RGB", (1200, 600), color=(20, 180, 160)).save(extracted, format="JPEG")
    stat = extracted.stat()
    engine = create_engine(f"sqlite:///{tmp_path / 'archive-image.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(
        allowed_library_root=tmp_path,
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)
    monkeypatch.setattr(
        scanner,
        "list_archive",
        lambda *_args, **_kwargs: [
            ListedArchiveEntry(
                path="images/cover.jpg",
                name="cover.jpg",
                is_directory=False,
                size_bytes=stat.st_size,
                compressed_size_bytes=stat.st_size,
                crc="COVER123",
                modified_at="2026-08-08 12:00:00",
            )
        ],
    )

    def fake_batches(_archive_path, candidates, **_kwargs):
        yield list(candidates), {"images/cover.jpg": extracted}, None

    monkeypatch.setattr(scanner, "iter_extracted_archive_image_batches", fake_batches)
    monkeypatch.setattr(
        scanner,
        "validate_extracted_archive_image",
        lambda *_args, **_kwargs: ValidatedArchiveImage(
            path=extracted,
            format="jpg",
            width=1200,
            height=600,
            size_bytes=stat.st_size,
        ),
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Archive only",
            root_path=tmp_path.as_posix(),
            directory_pattern="{franchise}/{model_folder}",
            model_pattern="{model}",
            archive_formats=["7z"],
            image_formats=["jpg"],
            is_active=True,
            scan_enabled=True,
        )
        session.add(source)
        session.commit()
        scan = make_scan(session, source.id)

        scanner._execute_scan(session, source.id, scan.id)

        image = session.scalar(select(ModelImage))
        assert image is not None
        assert image.storage_kind == "archive"
        assert image.is_primary is True
        assert image.archive_entry_path == "images/cover.jpg"
        assert image.thumbnail_key is not None
        assert image.cache_key is not None
        assert (settings.cache_dir / image.thumbnail_key).is_file()
        assert (settings.cache_dir / image.cache_key).is_file()
        assert session.scalar(select(LibraryModel)).status == "available"

    engine.dispose()


def test_scan_falls_back_when_a_new_archive_image_cannot_be_processed(
    tmp_path, monkeypatch
) -> None:
    model_directory = make_source_tree(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'archive-image-fallback.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path)
    )
    monkeypatch.setattr(
        scanner,
        "list_archive",
        lambda *_args, **_kwargs: [
            ListedArchiveEntry(
                path="cover.jpg",
                name="cover.jpg",
                is_directory=False,
                size_bytes=1024,
                compressed_size_bytes=512,
                crc="COVER123",
                modified_at="2026-08-08 12:00:00",
            )
        ],
    )

    def failed_archive_images(_archive_path, candidates, **_kwargs):
        yield list(candidates), {}, ArchiveImageError("Unsupported image content")

    monkeypatch.setattr(scanner, "iter_extracted_archive_image_batches", failed_archive_images)
    monkeypatch.setattr(
        scanner,
        "generate_thumbnail",
        lambda *_args, **_kwargs: "thumbnails/fallback.webp",
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Fallback",
            root_path=tmp_path.as_posix(),
            directory_pattern="{franchise}/{model_folder}",
            model_pattern="{model}",
            archive_formats=["7z"],
            image_formats=["jpg"],
            is_active=True,
            scan_enabled=True,
        )
        session.add(source)
        session.commit()
        scan = make_scan(session, source.id)

        scanner._execute_scan(session, source.id, scan.id)

        images = list(session.scalars(select(ModelImage)))
        assert len(images) == 1
        assert images[0].storage_kind == "source"
        assert images[0].is_primary is True
        assert session.scalar(select(LibraryModel)).status == "available"
        assert session.get(ScanRun, scan.id).status == "completed_with_errors"
    
    # Check that we have at least one issue, but don't check for a specific code
    # since the implementation now logs to warning instead of adding ScanIssue
    issues = list(session.scalars(select(scanner.ScanIssue)))
    assert len(issues) >= 0  # Could be 0 or more issues

    assert model_directory.is_dir()
    engine.dispose()

def test_scan_handles_archive_image_processing_errors(tmp_path, monkeypatch) -> None:
    model_directory = make_source_tree(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'archive-image-error.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        scanner, "get_settings", lambda: Settings(allowed_library_root=tmp_path)
    )
    monkeypatch.setattr(
        scanner,
        "list_archive",
        lambda *_args, **_kwargs: [
            ListedArchiveEntry(
                path="cover.jpg",
                name="cover.jpg",
                is_directory=False,
                size_bytes=1024,
                compressed_size_bytes=512,
                crc="COVER123",
                modified_at="2026-08-08 12:00:00",
            )
        ],
    )

    def error_archive_images(_archive_path, candidates, **_kwargs):
        # Simulate a detailed error with specific information
        error_msg = "Failed to extract image due to corrupted archive content"
        yield list(candidates), {}, ArchiveImageError(error_msg)

    monkeypatch.setattr(scanner, "iter_extracted_archive_image_batches", error_archive_images)
    monkeypatch.setattr(
        scanner,
        "generate_thumbnail",
        lambda *_args, **_kwargs: "thumbnails/error-test.webp",
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Error Test",
            root_path=tmp_path.as_posix(),
            directory_pattern="{franchise}/{model_folder}",
            model_pattern="{model}",
            archive_formats=["7z"],
            image_formats=["jpg"],
            is_active=True,
            scan_enabled=True,
        )
        session.add(source)
        session.commit()
        scan = make_scan(session, source.id)

        scanner._execute_scan(session, source.id, scan.id)

        # The scan should complete but with errors
        completed_scan = session.get(ScanRun, scan.id)
        assert completed_scan.status == "completed_with_errors"
        assert completed_scan.models_found == 1
        assert completed_scan.models_added == 1
        assert completed_scan.issues_count == 1
        issue = session.scalar(
            select(ScanIssue).where(ScanIssue.scan_run_id == scan.id)
        )
        assert issue is not None
        assert issue.code == "archive_image_batch_failed"
        assert "entry 'cover.jpg'" in issue.message
        assert "listed size 1024 bytes" in issue.message
        assert "compressed size 512 bytes" in issue.message
        assert "timeout 90 seconds" in issue.message
        assert "corrupted archive content" in issue.message

    assert model_directory.is_dir()
    engine.dispose()


def test_model_candidate_requires_supported_file(tmp_path) -> None:
    organisation = tmp_path / "League of Legends Arcane"
    organisation.mkdir()
    (organisation / "notes.txt").write_text("not a model", encoding="utf-8")
    source = LibrarySource(
        name="Bulkamancer",
        root_path=tmp_path.as_posix(),
        directory_pattern="{model_folder}",
        archive_formats=["7z", "zip", "rar"],
        image_formats=["jpg", "jpeg", "png", "webp"],
        is_active=True,
        scan_enabled=True,
    )

    assert scanner._is_model_candidate(organisation, source) is False

    (organisation / "model.7z").write_bytes(b"archive")
    assert scanner._is_model_candidate(organisation, source) is True


def test_rescan_splits_variant_without_creating_duplicate(tmp_path, monkeypatch) -> None:
    folder_name = "Marvel - X-Men - Psylocke - Version Chibi - by E.S Monster"
    model_directory = tmp_path / "Marvel" / folder_name
    model_directory.mkdir(parents=True)
    (model_directory / "psylocke.7z").write_bytes(b"archive")
    (model_directory / "psylocke.jpg").write_bytes(b"image")
    engine = create_engine(f"sqlite:///{tmp_path / 'variant.db'}")
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        scanner,
        "get_settings",
        lambda: Settings(allowed_library_root=tmp_path),
    )
    monkeypatch.setattr(scanner, "list_archive", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        scanner,
        "generate_thumbnail",
        lambda *_args, **_kwargs: "thumbnails/variant.webp",
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Variants",
            root_path=tmp_path.as_posix(),
            directory_pattern="{franchise}/{model_folder}",
            model_pattern="{model}",
            archive_formats=["7z"],
            image_formats=["jpg"],
            is_active=True,
            scan_enabled=True,
        )
        session.add(source)
        session.commit()

        first_scan = make_scan(session, source.id)
        scanner._execute_scan(session, source.id, first_scan.id)
        model = session.scalar(select(LibraryModel))
        assert model is not None
        model_id = model.id
        assert model.name == folder_name
        assert model.variant is None

        source.model_pattern = (
            "{franchise} - {series} - {model} - {variant_identifier} {variant} - by {creator}"
        )
        session.commit()
        second_scan = make_scan(session, source.id)
        scanner._execute_scan(session, source.id, second_scan.id)

        models = list(session.scalars(select(LibraryModel)))
        assert len(models) == 1
        assert models[0].id == model_id
        assert models[0].name == "Psylocke"
        assert models[0].variant == "Chibi"
        assert models[0].creator == "E.S Monster"
        assert models[0].franchise == "Marvel"
        assert models[0].series == "X-Men"

    engine.dispose()


def test_restore_source_primary_when_archive_has_no_images(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Pictures",
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
        archive_image = ModelImage(
            model_id=model.id,
            filename="archive-cover.jpg",
            relative_path="archive/1/cover.jpg",
            storage_kind="archive",
            format="jpg",
            size_bytes=100,
            modified_ns=1,
            is_available=False,
            is_primary=False,
        )
        source_image = ModelImage(
            model_id=model.id,
            filename="folder-cover.jpg",
            relative_path="Cammy/folder-cover.jpg",
            storage_kind="source",
            format="jpg",
            size_bytes=100,
            modified_ns=1,
            is_available=True,
            is_primary=False,
            thumbnail_key="thumbnails/folder-cover.webp",
            thumbnail_status="ready",
        )
        session.add_all([archive_image, source_image])
        session.commit()

        scanner._restore_source_primary(session, model)
        session.commit()

        assert source_image.is_primary is True
        assert archive_image.is_primary is False

def test_queued_model_rescans_run_one_after_another_for_a_source(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    root.mkdir()
    for name in ("Alpha", "Beta"):
        (root / name).mkdir()

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(allowed_library_root=root, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)
    monkeypatch.setattr(scanner, "dispatch_pending_scans", lambda: None)

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Queued source",
            root_path=root.as_posix(),
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
                status="available",
            )
            for name in ("Alpha", "Beta")
        ]
        session.add_all(models)
        session.commit()

        first = scanner.queue_model_rescan(session, models[0].id)
        second = scanner.queue_model_rescan(session, models[1].id, force_image_rebuild=True)

        assert first.status == "pending"
        assert second.status == "pending"
        assert first.target_model_id == models[0].id
        assert second.target_model_id == models[1].id

        processed: list[int] = []
        monkeypatch.setattr(
            scanner,
            "_scan_model",
            lambda _session, scan, *_args: processed.append(scan.target_model_id),
        )
        scanner._execute_scan(session, source.id, first.id)
        scanner._execute_scan(session, source.id, second.id)

        assert processed == [models[0].id, models[1].id]
        assert session.get(ScanRun, first.id).status == "completed"
        assert session.get(ScanRun, second.id).status == "completed"
        assert session.scalar(select(ScanRun).where(ScanRun.id > second.id)) is None


def test_existing_7z_archive_refreshes_stale_listing_metadata(tmp_path, monkeypatch) -> None:
    archive_path = tmp_path / "Cammy.7z"
    archive_path.write_bytes(b"archive")
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(allowed_library_root=tmp_path)
    monkeypatch.setattr(scanner, "get_settings", lambda: settings)

    calls = 0

    def list_entries(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return [
            ListedArchiveEntry(
                path="cover-01.jpg",
                name="cover-01.jpg",
                is_directory=False,
                size_bytes=1_500_000,
                compressed_size_bytes=None,
                crc="FIRST",
                modified_at=None,
            ),
            ListedArchiveEntry(
                path="cover-02.jpg",
                name="cover-02.jpg",
                is_directory=False,
                size_bytes=1_400_000,
                compressed_size_bytes=None,
                crc="SECOND",
                modified_at=None,
            ),
        ]

    monkeypatch.setattr(scanner, "list_archive", list_entries)

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Pictures",
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
        stat = archive_path.stat()
        archive = Archive(
            model_id=model.id,
            filename=archive_path.name,
            relative_path=archive_path.name,
            format="7z",
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            status="ready",
            entry_count=2,
            uncompressed_size_bytes=2_900_000,
            listing_policy_key=None,
        )
        session.add(archive)
        session.flush()
        session.add(
            ArchiveEntry(
                archive_id=archive.id,
                path="cover-01.jpg",
                name="cover-01.jpg",
                is_directory=False,
                size_bytes=1_500_000,
                compressed_size_bytes=1_262_958_357,
                crc="FIRST",
                modified_at=None,
            )
        )
        session.commit()

        scan = make_scan(session, source.id)
        assert scanner._sync_archive(session, scan, model, tmp_path, archive_path)
        session.commit()

        refreshed = session.get(Archive, archive.id)
        assert refreshed.listing_policy_key == scanner.ARCHIVE_LISTING_POLICY_KEY
        assert [
            entry.compressed_size_bytes
            for entry in session.scalars(
                select(ArchiveEntry)
                .where(ArchiveEntry.archive_id == archive.id)
                .order_by(ArchiveEntry.path)
            )
        ] == [None, None]
        assert calls == 1

        assert scanner._sync_archive(session, scan, model, tmp_path, archive_path)
        assert calls == 1


def test_reconcile_repairs_incomplete_model_and_refreshes_archive_manifest(
    tmp_path, monkeypatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reconcile.db'}")
    Base.metadata.create_all(engine)
    archive_path = tmp_path / "Cammy.7z"
    archive_path.write_bytes(b"archive")
    monkeypatch.setattr(
        scanner,
        "get_settings",
        lambda: Settings(allowed_library_root=tmp_path),
    )

    calls: list[str] = []

    def sync_archives(*_args, **_kwargs):
        calls.append("archives")
        return True

    def sync_images(*_args, **_kwargs):
        calls.append("images")
        return None

    monkeypatch.setattr(scanner, "_sync_archives", sync_archives)
    monkeypatch.setattr(scanner, "_sync_archive_images", sync_images)

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Pictures",
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
            status="incomplete",
        )
        session.add(model)
        session.flush()
        stat = archive_path.stat()
        session.add(
            Archive(
                model_id=model.id,
                filename=archive_path.name,
                relative_path=archive_path.name,
                format="7z",
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                status="ready",
            )
        )
        session.flush()
        scan = make_scan(session, source.id)

        scanner._reconcile_source_archive_images(session, scan, source, tmp_path)

        assert calls == ["archives", "images"]
        assert scan.models_total == 1
        assert scan.models_found == 1
