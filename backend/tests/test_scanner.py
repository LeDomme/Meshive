from pathlib import Path

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
from meshive.services import scanner


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
    monkeypatch.setattr(
        scanner,
        "list_archive",
        lambda *_args, **_kwargs: [
            ListedArchiveEntry(
                path="model.stl",
                name="model.stl",
                is_directory=False,
                size_bytes=1234,
                compressed_size_bytes=456,
                crc="ABC123",
                modified_at="2025-01-01 12:00:00",
            )
        ],
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
        assert completed.issues_count == 0

        second_archive_path = model_directory / "extras.zip"
        second_archive_path.write_bytes(b"second archive")
        multi_scan = make_scan(session, source.id)
        scanner._execute_scan(session, source.id, multi_scan.id)
        archives = list(
            session.scalars(
                select(Archive).order_by(Archive.filename)
            )
        )
        assert sorted(
            (archive.filename for archive in archives),
            key=str.casefold,
        ) == [
            "extras.zip",
            "Moikaloop - Neon Moika - by Aoae.7z",
        ]
        assert session.get(ScanRun, multi_scan.id).issues_count == 0

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
