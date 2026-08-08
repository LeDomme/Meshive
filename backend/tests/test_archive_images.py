import pytest

from meshive.archives.sevenzip_cli import ListedArchiveEntry
from meshive.services.archive_images import select_archive_image_candidates


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


def test_rejects_non_positive_limits() -> None:
    with pytest.raises(
        ValueError, match="Archive image selection limits must be positive"
    ):
        _select([_entry("cover.jpg")], max_candidates=0)


def test_accepts_missing_compressed_size_when_uncompressed_size_is_bounded() -> None:
    selected = _select([_entry("cover.jpg", compressed_size_bytes=None)])

    assert [entry.path for entry in selected] == ["cover.jpg"]
