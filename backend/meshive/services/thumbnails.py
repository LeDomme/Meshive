import hashlib
import os
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps, UnidentifiedImageError


class ThumbnailError(RuntimeError):
    pass


def generate_thumbnail(
    source_path: Path,
    *,
    relative_source_path: str,
    source_size: int,
    source_modified_ns: int,
    cache_root: Path,
    max_size: int,
    quality: int,
) -> str:
    signature = (
        f"{relative_source_path}\0{source_size}\0{source_modified_ns}\0"
        f"{max_size}\0{quality}"
    )
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    key = PurePosixPath("thumbnails", digest[:2], f"{digest}.webp").as_posix()
    output_path = safe_cache_path(cache_root, key)
    if output_path.is_file():
        return key

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".tmp")
    try:
        with Image.open(source_path) as original:
            original.seek(0)
            image = ImageOps.exif_transpose(original)
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.save(
                temporary_path,
                format="WEBP",
                quality=quality,
                method=6,
            )
        os.replace(temporary_path, output_path)
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as error:
        temporary_path.unlink(missing_ok=True)
        raise ThumbnailError(str(error)) from error
    return key


def safe_cache_path(cache_root: Path, key: str) -> Path:
    root = cache_root.resolve()
    relative = PurePosixPath(key)
    if relative.is_absolute() or ".." in relative.parts:
        raise ThumbnailError("Unsafe thumbnail cache key")
    path = root.joinpath(*relative.parts).resolve()
    if path != root and root not in path.parents:
        raise ThumbnailError("Thumbnail resolves outside the cache")
    return path


def remove_cached_thumbnail(cache_root: Path, key: str | None) -> None:
    if not key:
        return
    try:
        safe_cache_path(cache_root, key).unlink(missing_ok=True)
    except OSError:
        # Stale cache files are harmless and can be cleaned by maintenance later.
        return
