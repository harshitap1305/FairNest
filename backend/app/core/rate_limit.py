"""In-memory token-bucket rate limiter."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.core.errors import RateLimitError


@dataclass
class _Bucket:
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class RateLimiter:
    """
    Token-bucket rate limiter.
    Thread-safe via a per-instance lock.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        """
        Raise RateLimitError if the key has exceeded limit requests in window_seconds.
        Uses a sliding token-bucket algorithm.
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = _Bucket(tokens=float(limit - 1), last_refill=now)
                return

            # Refill tokens based on elapsed time
            elapsed = now - bucket.last_refill
            refill_rate = limit / window_seconds  # tokens per second
            bucket.tokens = min(float(limit), bucket.tokens + elapsed * refill_rate)
            bucket.last_refill = now

            if bucket.tokens < 1.0:
                raise RateLimitError(
                    f"Rate limit exceeded: {limit} requests per {window_seconds}s"
                )

            bucket.tokens -= 1.0

    def reset(self, key: str) -> None:
        """Remove a key from the limiter (for testing or admin overrides)."""
        with self._lock:
            self._buckets.pop(key, None)


# Pre-built limiters for common use-cases
login_limiter = RateLimiter()          # 10 attempts per minute per IP
identifier_limiter = RateLimiter()    # 5 attempts per minute per identifier
sensitive_limiter = RateLimiter()     # 5 operations per minute per IP


def check_login(ip: str) -> None:
    login_limiter.check(f"login:{ip}", limit=10, window_seconds=60)


def check_identifier(identifier: str) -> None:
    identifier_limiter.check(f"id:{identifier}", limit=5, window_seconds=60)


def check_sensitive(ip: str) -> None:
    sensitive_limiter.check(f"sensitive:{ip}", limit=5, window_seconds=60)
