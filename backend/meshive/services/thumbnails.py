import hashlib
import os
from io import BytesIO
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
    max_output_bytes: int,
) -> str:
    return generate_cached_webp(
        source_path,
        relative_source_path=relative_source_path,
        source_size=source_size,
        source_modified_ns=source_modified_ns,
        cache_root=cache_root,
        cache_namespace="thumbnails",
        max_size=max_size,
        quality=quality,
        max_output_bytes=max_output_bytes,
    )


def generate_cached_webp(
    source_path: Path,
    *,
    relative_source_path: str,
    source_size: int,
    source_modified_ns: int,
    cache_root: Path,
    cache_namespace: str,
    max_size: int,
    quality: int,
    max_output_bytes: int,
) -> str:
    namespace = PurePosixPath(cache_namespace)
    if (
        not namespace.parts
        or namespace.is_absolute()
        or ".." in namespace.parts
        or len(namespace.parts) != 1
    ):
        raise ThumbnailError("Unsafe image cache namespace")
    signature = (
        f"{relative_source_path}\0{source_size}\0{source_modified_ns}\0"
        f"{namespace.as_posix()}\0{max_size}\0{quality}\0{max_output_bytes}"
    )
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    key = PurePosixPath(namespace, digest[:2], f"{digest}.webp").as_posix()
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
            _save_bounded_webp(
                image,
                temporary_path,
                quality=quality,
                max_output_bytes=max_output_bytes,
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


def _save_bounded_webp(
    image: Image.Image,
    output_path: Path,
    *,
    quality: int,
    max_output_bytes: int,
) -> None:
    if max_output_bytes <= 0:
        raise ThumbnailError("Thumbnail output limit must be positive")

    quality_steps = _quality_steps(quality)
    original = image.copy()
    working = original
    last_encoded = b""

    while True:
        for candidate_quality in quality_steps:
            last_encoded = _encode_webp(working, candidate_quality)
            if len(last_encoded) <= max_output_bytes:
                output_path.write_bytes(last_encoded)
                return

        longest_edge = max(working.size)
        if longest_edge <= 64:
            break
        size_ratio = (max_output_bytes / len(last_encoded)) ** 0.5
        scale = max(0.5, min(0.85, size_ratio * 0.95))
        next_edge = max(64, int(longest_edge * scale))
        if next_edge >= longest_edge:
            next_edge = longest_edge - 1
        working = original.copy()
        working.thumbnail((next_edge, next_edge), Image.Resampling.LANCZOS)

    raise ThumbnailError(
        f"Thumbnail could not be encoded below {max_output_bytes} bytes"
    )


def _quality_steps(initial_quality: int) -> tuple[int, ...]:
    steps = [initial_quality]
    candidate = initial_quality
    while candidate > 5:
        candidate = max(5, candidate - 10)
        if candidate not in steps:
            steps.append(candidate)
    return tuple(steps)


def _encode_webp(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    return output.getvalue()


def safe_cache_path(cache_root: Path, key: str) -> Path:
    root = cache_root.resolve()
    relative = PurePosixPath(key)
    if relative.is_absolute() or ".." in relative.parts:
        raise ThumbnailError("Unsafe thumbnail cache key")
    path = root.joinpath(*relative.parts).resolve()
    if path != root and root not in path.parents:
        raise ThumbnailError("Thumbnail resolves outside the cache")
    return path


def remove_cached_file(cache_root: Path, key: str | None) -> None:
    if not key:
        return
    try:
        safe_cache_path(cache_root, key).unlink(missing_ok=True)
    except OSError:
        # Stale cache files are harmless and can be cleaned by maintenance later.
        return


def remove_cached_thumbnail(cache_root: Path, key: str | None) -> None:
    remove_cached_file(cache_root, key)
