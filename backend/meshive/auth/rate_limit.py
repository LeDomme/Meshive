from collections import deque
from threading import Lock
from time import monotonic


class AttemptRateLimiter:
    """Small in-process sliding-window limiter for authentication failures."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def retry_after(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        now = monotonic()
        with self._lock:
            attempts = self._attempts.get(key)
            if attempts is None:
                return None
            self._discard_expired(attempts, now, window_seconds)
            if not attempts:
                self._attempts.pop(key, None)
                return None
            if len(attempts) < limit:
                return None
            return max(1, int(window_seconds - (now - attempts[0])) + 1)

    def record_failure(self, key: str, *, window_seconds: int) -> None:
        now = monotonic()
        with self._lock:
            if key not in self._attempts and len(self._attempts) >= 10_000:
                self._remove_expired_keys(now, window_seconds)
                if len(self._attempts) >= 10_000:
                    self._attempts.pop(next(iter(self._attempts)))
            attempts = self._attempts.setdefault(key, deque())
            self._discard_expired(attempts, now, window_seconds)
            attempts.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    @staticmethod
    def _discard_expired(
        attempts: deque[float], now: float, window_seconds: int
    ) -> None:
        cutoff = now - window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    def _remove_expired_keys(self, now: float, window_seconds: int) -> None:
        for key, attempts in list(self._attempts.items()):
            self._discard_expired(attempts, now, window_seconds)
            if not attempts:
                self._attempts.pop(key, None)


login_limiter = AttemptRateLimiter()
setup_limiter = AttemptRateLimiter()
recovery_limiter = AttemptRateLimiter()
