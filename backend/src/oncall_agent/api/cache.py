"""Small async TTL cache used by health, signals, and lineage endpoints."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(slots=True)
class _Entry[T]:
    value: T
    expires_at: float


class AsyncTTLCache[T]:
    """Coalesce concurrent cache misses and expire entries by monotonic time."""

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, _Entry[T]] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
        *,
        refresh: bool = False,
    ) -> T:
        """Return a fresh cached value, invoking ``loader`` once on a miss."""

        now = time.monotonic()
        entry = self._entries.get(key)
        if not refresh and entry is not None and entry.expires_at > now:
            return entry.value
        async with self._lock:
            now = time.monotonic()
            entry = self._entries.get(key)
            if not refresh and entry is not None and entry.expires_at > now:
                return entry.value
            value = await loader()
            self._entries[key] = _Entry(value=value, expires_at=now + self.ttl_seconds)
            return value

    def clear(self) -> None:
        """Drop all cached values."""

        self._entries.clear()
