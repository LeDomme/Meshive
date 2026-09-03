from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from meshive.archives.sevenzip_cli import ListedArchiveEntry
from meshive.config import Settings
from meshive.database import Base
from meshive.models.catalog import Archive, LibraryModel, ModelImage, ScanIssue, ScanRun
from meshive.models.library_source import LibrarySource
from meshive.services import scanner


def add_model(
    root: Path,
    franchise: str,
    folder: str,
    archives: tuple[str, ...],
    images: tuple[str, ...] = ("cover.jpg",),
) -> None:
    model = root / franchise / folder
    model.mkdir(parents=True)
    for archive in archives:
        (model / archive).write_bytes(b"representative archive")
    for image in images:
        (model / image).write_bytes(b"representative image")


def test_scans_representative_mixed_library(tmp_path, monkeypatch) -> None:
    add_model(
        tmp_path,
        "Marvel",
        "Marvel Rivals - Magik - by 3D.moonn",
        ("Magik.7z", "Magik extras.zip"),
        ("render.png", "cover.jpg"),
    )
    add_model(
        tmp_path,
        "Disney",
        "Aladdin - Jasmin - by CA3D",
        ("Jasmin.rar",),
    )
    add_model(
        tmp_path,
        "Nintendo",
        "Animal Crossing - Doom Crossing Meme Chibi Isabelle - by NomNom",
        ("Isabelle.zip",),
    )
    add_model(
        tmp_path,
        "Pragmata",
        "Pragmata - Diorama Upgrade - by Bulkamancer",
        ("Diorama.7z",),
        (),
    )
    organisation = tmp_path / "League of Legends" / "League of Legends Arcane"
    organisation.mkdir(parents=True)
    (organisation / "notes.txt").write_text("not a model", encoding="utf-8")

    engine = create_engine(f"sqlite:///{tmp_path / 'representative.db'}")
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
                path="meshes/model.stl",
                name="model.stl",
                is_directory=False,
                size_bytes=123,
                compressed_size_bytes=45,
                crc="A1B2C3D4",
                modified_at="2026-01-01 12:00:00",
            )
        ],
    )
    monkeypatch.setattr(
        scanner,
        "generate_thumbnail",
        lambda *_args, **_kwargs: "thumbnails/representative.webp",
    )

    with Session(engine, expire_on_commit=False) as session:
        source = LibrarySource(
            name="Representative library",
            root_path=tmp_path.as_posix(),
            directory_pattern="{franchise}/{model_folder}",
            model_pattern="\n".join(
                (
                    "{franchise} {series} - {model} - by {creator}",
                    "{series} - {model} - by {creator}",
                    "{franchise} - {model} - by {creator}",
                    "{model} - by {creator}",
                )
            ),
            archive_formats=["7z", "zip", "rar"],
            image_formats=["jpg", "jpeg", "png", "webp"],
            is_active=True,
            scan_enabled=True,
        )
        session.add(source)
        session.commit()
        scan = scanner.create_scan_run(session, source.id, mode="smart")

        scanner._execute_scan(session, source.id, scan.id)

        models = {
            model.name: model
            for model in session.scalars(select(LibraryModel).order_by(LibraryModel.id))
        }
        assert set(models) == {
            "Magik",
            "Jasmin",
            "Doom Crossing Meme Chibi Isabelle",
            "Diorama Upgrade",
        }
        assert models["Magik"].franchise == "Marvel"
        assert models["Magik"].series == "Rivals"
        assert models["Magik"].creator == "3D.moonn"
        assert models["Jasmin"].franchise == "Disney"
        assert models["Jasmin"].series == "Aladdin"
        assert models["Doom Crossing Meme Chibi Isabelle"].series == "Animal Crossing"
        assert models["Diorama Upgrade"].status == "incomplete"

        formats = set(session.scalars(select(Archive.format)))
        assert formats == {"7z", "zip", "rar"}
        assert len(list(session.scalars(select(Archive)))) == 5
        magik_images = list(
            session.scalars(
                select(ModelImage).where(ModelImage.model_id == models["Magik"].id)
            )
        )
        assert next(image.filename for image in magik_images if image.is_primary) == (
            "cover.jpg"
        )
        issues = list(session.scalars(select(ScanIssue)))
        assert [(issue.code, issue.relative_path) for issue in issues] == [
            (
                "image_missing",
                "Pragmata/Pragmata - Diorama Upgrade - by Bulkamancer",
            )
        ]
        completed = session.get(ScanRun, scan.id)
        assert completed.status == "completed_with_errors"
        assert completed.models_found == 4
        assert completed.issues_count == 1

    engine.dispose()
