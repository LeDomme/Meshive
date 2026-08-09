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
    assert "archive_image_batch_failed" in {
            issue.code for issue in session.scalars(select(scanner.ScanIssue))
        }

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
