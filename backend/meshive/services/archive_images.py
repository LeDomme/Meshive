import tempfile
import warnings
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

from meshive.archives.sevenzip_cli import (
    ArchiveReadError,
    ListedArchiveEntry,
    extract_archive_entry,
)

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

_DETECTED_IMAGE_FORMATS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}


class ArchiveImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedArchiveImage:
    path: Path
    format: str
    width: int
    height: int
    size_bytes: int


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


@contextmanager
def open_validated_archive_image(
    archive_path: Path,
    candidate: ListedArchiveEntry,
    *,
    command: str,
    data_dir: Path,
    timeout_seconds: int,
    max_output_bytes: int,
    max_compressed_bytes: int,
    max_pixels: int,
    threads: int = 1,
) -> Iterator[ValidatedArchiveImage]:
    if not _is_eligible_image(
        candidate,
        max_entry_bytes=max_output_bytes,
        max_compressed_bytes=max_compressed_bytes,
    ):
        raise ArchiveImageError("Archive entry is not an eligible image candidate")
    assert candidate.size_bytes is not None

    temporary_root = data_dir / "tmp" / "archive-images"
    try:
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="archive-image-", dir=temporary_root
        ) as work:
            extracted_path = Path(work) / "candidate.bin"
            try:
                extracted_size = extract_archive_entry(
                    str(archive_path),
                    candidate.path,
                    extracted_path,
                    command=command,
                    timeout_seconds=timeout_seconds,
                    max_output_bytes=max_output_bytes,
                    threads=threads,
                )
            except ArchiveReadError as error:
                raise ArchiveImageError(str(error)) from error
            if (
                extracted_size != candidate.size_bytes
                or extracted_path.stat().st_size != candidate.size_bytes
            ):
                raise ArchiveImageError(
                    "Extracted archive image size differs from its archive listing"
                )
            yield _validate_extracted_image(extracted_path, max_pixels=max_pixels)
    except OSError as error:
        raise ArchiveImageError(str(error)) from error


def _validate_extracted_image(
    path: Path,
    *,
    max_pixels: int,
) -> ValidatedArchiveImage:
    if max_pixels <= 0:
        raise ArchiveImageError("Archive image pixel limit must be positive")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                detected_format = _DETECTED_IMAGE_FORMATS.get(image.format or "")
                if detected_format is None:
                    raise ArchiveImageError("Archive entry is not a supported image")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ArchiveImageError(
                        f"Archive image exceeds the {max_pixels} pixel limit"
                    )
                image.verify()
            with Image.open(path) as image:
                image.load()
    except ArchiveImageError:
        raise
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ArchiveImageError("Archive entry does not contain a valid image") from error

    return ValidatedArchiveImage(
        path=path,
        format=detected_format,
        width=width,
        height=height,
        size_bytes=path.stat().st_size,
    )


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
        or entry.path.startswith("@")
        or any(character in entry.path for character in ("\x00", "\r", "\n", "*", "?"))
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
