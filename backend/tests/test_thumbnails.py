from PIL import Image

from meshive.services.thumbnails import (
    ThumbnailError,
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
    )

    output = safe_cache_path(cache, key)
    assert output.is_file()
    with Image.open(output) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert thumbnail.size == (480, 240)


def test_rejects_unsafe_cache_key(tmp_path) -> None:
    try:
        safe_cache_path(tmp_path, "../outside.webp")
    except ThumbnailError:
        pass
    else:
        raise AssertionError("Unsafe cache key was accepted")
