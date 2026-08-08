from collections.abc import Iterable
from pathlib import PurePosixPath

from meshive.archives.sevenzip_cli import ListedArchiveEntry

SUPPORTED_ARCHIVE_IMAGE_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png", ".webp"})

_IGNORED_PATH_PARTS = frozenset(
    {
        "__macosx",
        "material",
        "materials",
        "map",
        "maps",
        "texture",
        "textures",
    }
)

_PREFERRED_NAME_MARKERS = (
    "cover",
    "preview",
    "render",
    "promo",
    "beauty",
    "thumbnail",
)


def select_archive_image_candidates(
    entries: Iterable[ListedArchiveEntry],
    *,
    max_candidates: int,
    max_entry_bytes: int,
    max_compressed_bytes: int,
    max_total_bytes: int,
) -> list[ListedArchiveEntry]:
    """Return deterministic, bounded image candidates from an archive listing.

    This function only examines metadata that was already produced by the bounded
    archive listing command. It does not extract data or recurse into archives.
    Entries without a declared uncompressed size are skipped so the later
    extraction stage always starts with a known resource budget.
    """

    if min(
        max_candidates,
        max_entry_bytes,
        max_compressed_bytes,
        max_total_bytes,
    ) <= 0:
        raise ValueError("Archive image selection limits must be positive")

    candidates = [
        entry
        for entry in entries
        if _is_eligible_image(
            entry,
            max_entry_bytes=max_entry_bytes,
            max_compressed_bytes=max_compressed_bytes,
        )
    ]
    candidates.sort(key=_candidate_sort_key)

    selected: list[ListedArchiveEntry] = []
    selected_bytes = 0
    for entry in candidates:
        assert entry.size_bytes is not None
        if selected_bytes + entry.size_bytes > max_total_bytes:
            continue
        selected.append(entry)
        selected_bytes += entry.size_bytes
        if len(selected) == max_candidates:
            break
    return selected


def _is_eligible_image(
    entry: ListedArchiveEntry,
    *,
    max_entry_bytes: int,
    max_compressed_bytes: int,
) -> bool:
    if entry.is_directory or entry.size_bytes is None or entry.size_bytes <= 0:
        return False
    if entry.size_bytes > max_entry_bytes:
        return False
    if (
        entry.compressed_size_bytes is not None
        and entry.compressed_size_bytes > max_compressed_bytes
    ):
        return False

    path = PurePosixPath(entry.path.replace("\\", "/"))
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or ":" in path.parts[0]
        or "\x00" in entry.path
        or path.name.startswith(".")
    ):
        return False
    if path.suffix.casefold() not in SUPPORTED_ARCHIVE_IMAGE_EXTENSIONS:
        return False

    directory_parts = path.parts[:-1]
    return not any(
        part.startswith(".") or part.casefold() in _IGNORED_PATH_PARTS
        for part in directory_parts
    )


def _candidate_sort_key(entry: ListedArchiveEntry) -> tuple[int, int, str]:
    path = PurePosixPath(entry.path.replace("\\", "/"))
    stem = path.stem.casefold()
    name_priority = len(_PREFERRED_NAME_MARKERS)
    for index, marker in enumerate(_PREFERRED_NAME_MARKERS):
        if marker in stem:
            name_priority = index
            break
    return name_priority, len(path.parts), path.as_posix().casefold()
