from pathlib import Path

from meshive.archives.sevenzip_cli import ListedArchiveEntry
from meshive.config import Settings
from meshive.models.catalog import Archive, ArchiveEntry, ModelImage
from meshive.services import scanner


def test_archive_image_policy_key_changes_with_selection_rules() -> None:
    base = Settings(
        archive_image_max_candidates=12,
        archive_image_max_entry_bytes=64 * 1024 * 1024,
        archive_image_max_compressed_bytes=64 * 1024 * 1024,
        archive_image_max_total_bytes=256 * 1024 * 1024,
        archive_image_max_pixels=80_000_000,
    )
    changed = Settings(
        archive_image_max_candidates=30,
        archive_image_max_entry_bytes=64 * 1024 * 1024,
        archive_image_max_compressed_bytes=64 * 1024 * 1024,
        archive_image_max_total_bytes=256 * 1024 * 1024,
        archive_image_max_pixels=80_000_000,
    )

    assert scanner._archive_image_selection_policy_key(base) != (
        scanner._archive_image_selection_policy_key(changed)
    )


def test_archive_image_cache_requires_matching_entry_fingerprint(tmp_path: Path) -> None:
    entry = ArchiveEntry(
        path="renders/cover.jpg",
        name="cover.jpg",
        is_directory=False,
        size_bytes=123,
        compressed_size_bytes=100,
        crc="ABC123",
        modified_at="2026-08-12 00:00:00",
    )
    archive = Archive(size_bytes=456, modified_ns=789)
    cache_key = "archive-images/cover.webp"
    thumbnail_key = "thumbnails/cover.webp"
    for key in (cache_key, thumbnail_key):
        target = tmp_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"cached")
    image = ModelImage(
        relative_path="archive/1/renders/cover.jpg",
        filename="cover.jpg",
        format="JPEG",
        size_bytes=123,
        modified_ns=789,
        storage_kind="archive",
        cache_key=cache_key,
        thumbnail_key=thumbnail_key,
        archive_entry_fingerprint=scanner._archive_entry_fingerprint(entry),
    )

    assert scanner._archive_image_cache_is_current(image, archive, entry, tmp_path)

    entry.crc = "CHANGED"
    assert not scanner._archive_image_cache_is_current(image, archive, entry, tmp_path)


def test_archive_entry_fingerprint_uses_listing_identity() -> None:
    first = ListedArchiveEntry(
        path="renders/cover.jpg",
        name="cover.jpg",
        is_directory=False,
        size_bytes=123,
        compressed_size_bytes=100,
        crc="ABC123",
        modified_at="2026-08-12 00:00:00",
    )
    second = ListedArchiveEntry(
        path="renders/cover.jpg",
        name="cover.jpg",
        is_directory=False,
        size_bytes=123,
        compressed_size_bytes=100,
        crc="CHANGED",
        modified_at="2026-08-12 00:00:00",
    )
    first_entry = ArchiveEntry(**first.__dict__)
    second_entry = ArchiveEntry(**second.__dict__)

    assert scanner._archive_entry_fingerprint(first_entry) != (
        scanner._archive_entry_fingerprint(second_entry)
    )