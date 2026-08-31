from contextlib import contextmanager
from io import BytesIO

import pytest
from PIL import Image

from meshive.archives.sevenzip_cli import ListedArchiveEntry
from meshive.services import archive_images
from meshive.services.archive_images import (
    ArchiveImageError,
    archive_image_limit_skip_counts,
    iter_extracted_archive_image_batches,
    open_extracted_archive_images,
    open_validated_archive_image,
    select_archive_image_candidates,
    validate_extracted_archive_image,
)


def _entry(
    path: str,
    *,
    size_bytes: int | None = 1024,
    compressed_size_bytes: int | None = 512,
    is_directory: bool = False,
) -> ListedArchiveEntry:
    return ListedArchiveEntry(
        path=path,
        name=path.rsplit("/", 1)[-1],
        is_directory=is_directory,
        size_bytes=size_bytes,
        compressed_size_bytes=compressed_size_bytes,
        crc=None,
        modified_at=None,
    )


def _select(
    entries: list[ListedArchiveEntry],
    *,
    max_candidates: int = 12,
    max_entry_bytes: int = 32 * 1024 * 1024,
    max_compressed_bytes: int = 32 * 1024 * 1024,
    max_total_bytes: int = 128 * 1024 * 1024,
) -> list[ListedArchiveEntry]:
    return select_archive_image_candidates(
        entries,
        max_candidates=max_candidates,
        max_entry_bytes=max_entry_bytes,
        max_compressed_bytes=max_compressed_bytes,
        max_total_bytes=max_total_bytes,
    )


def test_selects_supported_images_in_deterministic_priority_order() -> None:
    selected = _select(
        [
            _entry("Gallery/zeta.PNG"),
            _entry("deep/folder/model.webp"),
            _entry("Gallery/preview-02.jpg"),
            _entry("cover.JPEG"),
            _entry("mesh/model.stl"),
        ]
    )

    assert [entry.path for entry in selected] == [
        "cover.JPEG",
        "Gallery/preview-02.jpg",
        "Gallery/zeta.PNG",
        "deep/folder/model.webp",
    ]


def test_ignores_texture_system_unsafe_and_nested_archive_entries() -> None:
    selected = _select(
        [
            _entry("Textures/body.png"),
            _entry("__MACOSX/preview.jpg"),
            _entry(".hidden/cover.jpg"),
            _entry(".hidden.jpg"),
            _entry("../outside.jpg"),
            _entry("C:/outside.jpg"),
            _entry("@entries.jpg"),
            _entry("Gallery/image?.jpg"),
            _entry("Gallery/model-decal.jpg"),
            _entry("stickskaneda-decal/cover.jpg"),
            _entry("extras.zip"),
            _entry("Gallery", is_directory=True, size_bytes=0),
            _entry("Gallery/valid.jpg"),
        ]
    )

    assert [entry.path for entry in selected] == ["Gallery/valid.jpg"]


def test_enforces_entry_compressed_total_and_candidate_limits() -> None:
    selected = _select(
        [
            _entry("cover.jpg", size_bytes=8, compressed_size_bytes=4),
            _entry("preview.png", size_bytes=7, compressed_size_bytes=4),
            _entry("render.webp", size_bytes=6, compressed_size_bytes=6),
            _entry("unknown.jpg", size_bytes=None),
            _entry("oversized.jpg", size_bytes=11, compressed_size_bytes=4),
        ],
        max_candidates=2,
        max_entry_bytes=10,
        max_compressed_bytes=5,
        max_total_bytes=14,
    )

    assert [entry.path for entry in selected] == ["cover.jpg"]


def test_counts_only_gallery_candidates_skipped_by_selection_limits() -> None:
    skipped = archive_image_limit_skip_counts(
        [
            _entry("cover.jpg", size_bytes=8, compressed_size_bytes=4),
            _entry("preview.png", size_bytes=7, compressed_size_bytes=4),
            _entry("render.webp", size_bytes=6, compressed_size_bytes=6),
            _entry("oversized.jpg", size_bytes=11, compressed_size_bytes=4),
            _entry("Textures/body.png", size_bytes=100, compressed_size_bytes=100),
            _entry(".hidden/cover.jpg", size_bytes=100, compressed_size_bytes=100),
            _entry("unknown.jpg", size_bytes=None),
        ],
        max_candidates=1,
        max_entry_bytes=10,
        max_compressed_bytes=5,
        max_total_bytes=10,
    )

    assert skipped == {
        "candidate limit": 1,
        "compressed size limit": 1,
        "per-entry size limit": 1,
    }


def test_rejects_non_positive_limits() -> None:
    with pytest.raises(
        ValueError, match="Archive image selection limits must be positive"
    ):
        _select([_entry("cover.jpg")], max_candidates=0)


def test_accepts_missing_compressed_size_when_uncompressed_size_is_bounded() -> None:
    selected = _select([_entry("cover.jpg", compressed_size_bytes=None)])

    assert [entry.path for entry in selected] == ["cover.jpg"]


def _image_bytes(format_name: str, size: tuple[int, int] = (32, 24)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(20, 180, 160)).save(output, format=format_name)
    return output.getvalue()


def _install_fake_extractor(monkeypatch, content: bytes, *, reported_size: int | None = None):
    def fake_extract(
        _archive_path: str,
        _entry_path: str,
        destination_path,
        **_kwargs,
    ) -> int:
        destination_path.write_bytes(content)
        return len(content) if reported_size is None else reported_size

    monkeypatch.setattr(archive_images, "extract_archive_entry", fake_extract)


def test_extracts_validates_and_cleans_up_supported_image(tmp_path, monkeypatch) -> None:
    content = _image_bytes("PNG")
    _install_fake_extractor(monkeypatch, content)
    candidate = _entry("Gallery/cover.jpg", size_bytes=len(content))
    temporary_root = tmp_path / "data" / "tmp" / "archive-images"

    with open_validated_archive_image(
        tmp_path / "model.7z",
        candidate,
        command="7z",
        data_dir=tmp_path / "data",
        timeout_seconds=30,
        max_output_bytes=1024 * 1024,
        max_compressed_bytes=1024 * 1024,
        max_pixels=1_000_000,
    ) as image:
        assert image.path.is_file()
        assert temporary_root in image.path.parents
        assert image.format == "png"
        assert (image.width, image.height) == (32, 24)
        assert image.size_bytes == len(content)

    assert temporary_root.is_dir()
    assert list(temporary_root.iterdir()) == []


def test_rejects_invalid_image_content_and_cleans_up(tmp_path, monkeypatch) -> None:
    content = b"not an image"
    _install_fake_extractor(monkeypatch, content)
    candidate = _entry("cover.jpg", size_bytes=len(content))
    temporary_root = tmp_path / "data" / "tmp" / "archive-images"

    with (
        pytest.raises(ArchiveImageError, match="valid image"),
        open_validated_archive_image(
            tmp_path / "model.7z",
            candidate,
            command="7z",
            data_dir=tmp_path / "data",
            timeout_seconds=30,
            max_output_bytes=1024 * 1024,
            max_compressed_bytes=1024 * 1024,
            max_pixels=1_000_000,
        ),
    ):
        pass

    assert list(temporary_root.iterdir()) == []


def test_rejects_image_above_pixel_limit(tmp_path, monkeypatch) -> None:
    content = _image_bytes("WEBP", (100, 100))
    _install_fake_extractor(monkeypatch, content)
    candidate = _entry("cover.webp", size_bytes=len(content))

    with pytest.raises(ArchiveImageError) as error:
        with open_validated_archive_image(
            tmp_path / "model.7z",
            candidate,
            command="7z",
            data_dir=tmp_path / "data",
            timeout_seconds=30,
            max_output_bytes=1024 * 1024,
            max_compressed_bytes=1024 * 1024,
            max_pixels=9_999,
        ):
            pass

    message = str(error.value)
    assert "WEBP" in message
    assert "100x100" in message
    assert f"{len(content)} bytes" in message
    assert "pixel limit" in message


def test_rejects_extracted_size_mismatch(tmp_path, monkeypatch) -> None:
    content = _image_bytes("JPEG")
    _install_fake_extractor(monkeypatch, content, reported_size=len(content) - 1)
    candidate = _entry("cover.jpg", size_bytes=len(content))

    with (
        pytest.raises(ArchiveImageError, match="differs"),
        open_validated_archive_image(
            tmp_path / "model.7z",
            candidate,
            command="7z",
            data_dir=tmp_path / "data",
            timeout_seconds=30,
            max_output_bytes=1024 * 1024,
            max_compressed_bytes=1024 * 1024,
            max_pixels=1_000_000,
        ),
    ):
        pass


def test_batch_extracts_candidates_once_and_cleans_up(tmp_path, monkeypatch) -> None:
    content = _image_bytes("PNG")
    candidates = [
        _entry("Gallery/cover.png", size_bytes=len(content)),
        _entry("Gallery/render.png", size_bytes=len(content)),
    ]
    calls: list[list[str]] = []

    def fake_extract(_archive_path, entry_paths, destination, **_kwargs):
        calls.append(entry_paths)
        for entry_path in entry_paths:
            path = destination.joinpath(*entry_path.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    monkeypatch.setattr(archive_images, "extract_archive_entries", fake_extract)
    temporary_root = tmp_path / "data" / "tmp" / "archive-images"

    with open_extracted_archive_images(
        tmp_path / "model.7z",
        candidates,
        command="7z",
        data_dir=tmp_path / "data",
        timeout_seconds=90,
        max_entry_bytes=1024 * 1024,
        max_compressed_bytes=1024 * 1024,
        max_total_bytes=1024 * 1024,
    ) as extracted:
        assert sorted(extracted) == ["Gallery/cover.png", "Gallery/render.png"]
        assert all(path.is_file() for path in extracted.values())

    assert calls == [["Gallery/cover.png", "Gallery/render.png"]]
    assert temporary_root.is_dir()
    assert not list(temporary_root.iterdir())


def test_splits_timed_out_archive_image_batch(tmp_path, monkeypatch) -> None:
    candidates = [_entry("cover.jpg"), _entry("render.jpg")]
    attempts: list[list[str]] = []

    @contextmanager
    def fake_open(_archive_path, batch, **_kwargs):
        selected = list(batch)
        attempts.append([candidate.path for candidate in selected])
        if len(selected) > 1:
            raise ArchiveImageError("Archive command exceeded 90 second limit")
        yield {selected[0].path: tmp_path / selected[0].name}

    monkeypatch.setattr(archive_images, "open_extracted_archive_images", fake_open)

    batches = list(
        iter_extracted_archive_image_batches(
            tmp_path / "model.7z",
            candidates,
            command="7z",
            data_dir=tmp_path / "data",
            timeout_seconds=90,
            max_entry_bytes=1024 * 1024,
            max_compressed_bytes=1024 * 1024,
        )
    )

    assert attempts == [["cover.jpg", "render.jpg"], ["cover.jpg"], ["render.jpg"]]
    assert [batch[0][0].path for batch in batches] == ["cover.jpg", "render.jpg"]
    assert all(batch[2] is None for batch in batches)


def test_handles_error_detailed_logging(tmp_path, monkeypatch) -> None:
    candidates = [_entry("cover.jpg")]
    attempts: list[list[str]] = []

    @contextmanager
    def fake_open(_archive_path, batch, **_kwargs):
        selected = list(batch)
        attempts.append([candidate.path for candidate in selected])
        raise ArchiveImageError("Detailed error message for testing")

    monkeypatch.setattr(archive_images, "open_extracted_archive_images", fake_open)

    batches = list(
        iter_extracted_archive_image_batches(
            tmp_path / "model.7z",
            candidates,
            command="7z",
            data_dir=tmp_path / "data",
            timeout_seconds=90,
            max_entry_bytes=1024 * 1024,
            max_compressed_bytes=1024 * 1024,
        )
    )

    assert attempts == [["cover.jpg"]]
    assert len(batches) == 1
    assert batches[0][2] is not None
    assert "Detailed error message" in str(batches[0][2])


def test_accepts_mpo_images_as_jpeg(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "camera-photo.jpg"
    image_path.write_bytes(_image_bytes("JPEG"))
    original_open = Image.open

    def open_as_mpo(*args, **kwargs):
        image = original_open(*args, **kwargs)
        image.format = "MPO"
        return image

    monkeypatch.setattr(archive_images.Image, "open", open_as_mpo)

    validated = validate_extracted_archive_image(image_path, max_pixels=1_000_000)

    assert validated.format == "jpg"


def test_uses_configured_pixel_limit_instead_of_pillow_default(
    tmp_path, monkeypatch
) -> None:
    class FakeImage:
        format = "JPEG"
        size = (15_000, 10_000)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def verify(self) -> None:
            pass

        def load(self) -> None:
            pass

    seen_pixel_limits = []

    def fake_open(*_args, **_kwargs):
        seen_pixel_limits.append(Image.MAX_IMAGE_PIXELS)
        return FakeImage()

    previous_max_pixels = Image.MAX_IMAGE_PIXELS
    monkeypatch.setattr(archive_images.Image, "open", fake_open)
    image_path = tmp_path / "large.jpg"
    image_path.write_bytes(b"placeholder")

    validated = validate_extracted_archive_image(
        image_path, max_pixels=200_000_000
    )

    assert validated.width * validated.height == 150_000_000
    assert seen_pixel_limits == [None, None]
    assert Image.MAX_IMAGE_PIXELS == previous_max_pixels
