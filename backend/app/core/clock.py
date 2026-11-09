"""Controllable clock for testability."""

from __future__ import annotations

from datetime import datetime, timezone

_override: datetime | None = None


def now() -> datetime:
    """Return the current UTC datetime (or the test-injected override)."""
    return _override if _override is not None else datetime.now(timezone.utc)


def set_now(dt: datetime | None) -> None:
    """Override the clock for tests. Pass None to restore real time."""
    global _override
    _override = dt
