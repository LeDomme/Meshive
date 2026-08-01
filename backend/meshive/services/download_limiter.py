import threading

from meshive.config import get_settings

_slots = threading.BoundedSemaphore(get_settings().max_concurrent_downloads)


def claim_download() -> bool:
    return _slots.acquire(blocking=False)


def release_download() -> None:
    _slots.release()
