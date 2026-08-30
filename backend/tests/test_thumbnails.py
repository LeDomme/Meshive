import random

from PIL import Image

from meshive.services.thumbnails import (
    ThumbnailError,
    generate_cached_webp,
    generate_thumbnail,
    safe_cache_path,
)


def test_generates_bounded_webp_thumbnail(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    cache = tmp_path / "cache"
    Image.new("RGB", (1200, 600), color=(20, 180, 160)).save(source, format="JPEG")
    stat = source.stat()

    key = generate_thumbnail(
        source,
        relative_source_path="1/Franchise/Model/source.jpg",
        source_size=stat.st_size,
        source_modified_ns=stat.st_mtime_ns,
        cache_root=cache,
        max_size=480,
        quality=82,
        max_output_bytes=100 * 1024,
    )

    output = safe_cache_path(cache, key)
    assert output.is_file()
    with Image.open(output) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert thumbnail.size == (480, 240)
    assert output.stat().st_size <= 100 * 1024


def test_reduces_quality_and_dimensions_to_hard_output_limit(tmp_path) -> None:
    source = tmp_path / "complex.png"
    cache = tmp_path / "cache"
    pixels = random.Random(42).randbytes(900 * 900 * 3)
    Image.frombytes("RGB", (900, 900), pixels).save(source, format="PNG")
    stat = source.stat()

    key = generate_thumbnail(
        source,
        relative_source_path="1/Franchise/Model/complex.png",
        source_size=stat.st_size,
        source_modified_ns=stat.st_mtime_ns,
        cache_root=cache,
        max_size=480,
        quality=95,
        max_output_bytes=20 * 1024,
    )

    output = safe_cache_path(cache, key)
    assert output.stat().st_size <= 20 * 1024
    with Image.open(output) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert max(thumbnail.size) <= 480


def test_output_limit_changes_thumbnail_cache_key(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    cache = tmp_path / "cache"
    Image.new("RGB", (200, 200), color=(20, 180, 160)).save(source, format="JPEG")
    stat = source.stat()

    common = {
        "relative_source_path": "1/Franchise/Model/source.jpg",
        "source_size": stat.st_size,
        "source_modified_ns": stat.st_mtime_ns,
        "cache_root": cache,
        "max_size": 480,
        "quality": 82,
    }
    larger_key = generate_thumbnail(source, **common, max_output_bytes=200 * 1024)
    bounded_key = generate_thumbnail(source, **common, max_output_bytes=100 * 1024)

    assert bounded_key != larger_key


def test_archive_derivative_uses_separate_cache_namespace(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    cache = tmp_path / "cache"
    Image.new("RGB", (1200, 600), color=(20, 180, 160)).save(source, format="JPEG")
    stat = source.stat()

    key = generate_cached_webp(
        source,
        relative_source_path="1/Franchise/Model/archive/cover.jpg",
        source_size=stat.st_size,
        source_modified_ns=stat.st_mtime_ns,
        cache_root=cache,
        cache_namespace="archive-images",
        max_size=1600,
        quality=82,
        max_output_bytes=768 * 1024,
    )

    output = safe_cache_path(cache, key)
    assert key.startswith("archive-images/")
    assert output.is_file()
    assert output.stat().st_size <= 768 * 1024


def test_rejects_unsafe_cache_key(tmp_path) -> None:
    try:
        safe_cache_path(tmp_path, "../outside.webp")
    except ThumbnailError:
        pass
    else:
        raise AssertionError("Unsafe cache key was accepted")



def test_uses_configured_pixel_limit_for_archive_derivatives(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.jpg"
    cache = tmp_path / "cache"
    Image.new("RGB", (100, 100), color=(20, 180, 160)).save(source, format="JPEG")
    stat = source.stat()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)

    key = generate_cached_webp(
        source,
        relative_source_path="1/Franchise/Model/archive/large.jpg",
        source_size=stat.st_size,
        source_modified_ns=stat.st_mtime_ns,
        cache_root=cache,
        cache_namespace="archive-images",
        max_size=1600,
        quality=82,
        max_output_bytes=768 * 1024,
        max_pixels=20_000,
    )

    assert safe_cache_path(cache, key).is_file()
