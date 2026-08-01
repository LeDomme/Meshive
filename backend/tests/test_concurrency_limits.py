import threading

from meshive.config import Settings
from meshive.services import download_limiter, scanner


def test_scan_limit_and_duplicate_source_claims(monkeypatch) -> None:
    monkeypatch.setattr(
        scanner,
        "get_settings",
        lambda: Settings(max_concurrent_scans=1),
    )
    scanner._active_sources.clear()
    try:
        assert scanner.claim_source(1) is True
        assert scanner.claim_source(1) is False
        assert scanner.claim_source(2) is False
        scanner.release_source(1)
        assert scanner.claim_source(2) is True
    finally:
        scanner._active_sources.clear()


def test_download_limit_releases_capacity(monkeypatch) -> None:
    monkeypatch.setattr(
        download_limiter,
        "_slots",
        threading.BoundedSemaphore(1),
    )

    assert download_limiter.claim_download() is True
    assert download_limiter.claim_download() is False
    download_limiter.release_download()
    assert download_limiter.claim_download() is True
    download_limiter.release_download()
