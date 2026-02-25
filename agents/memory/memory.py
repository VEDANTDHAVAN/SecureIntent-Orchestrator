"""
memory.py
---------
In-memory short-term context store for the agent pipeline.

Stores recent intents per user with TTL so the intent extractor
can resolve references like "the email from Bob last week".

Interface is Redis-compatible for easy backend swap.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class MemoryEntry:
    key: str
    value: Any
    expires_at: float   # monotonic timestamp


class AgentMemory:
    """
    Sliding-window in-memory store.

    Entries expire after `ttl_seconds` (default 1 hour).
    Stale entries are evicted lazily on access.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._store: dict[str, list[MemoryEntry]] = {}  # { user_id: [entries] }
        self._default_ttl = default_ttl_seconds

    def store(self, user_id: str, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store a value under (user_id, key)."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.monotonic() + ttl
        entry = MemoryEntry(key=key, value=value, expires_at=expires_at)

        if user_id not in self._store:
            self._store[user_id] = []

        self._store[user_id].append(entry)
        self._evict(user_id)

    def get(self, user_id: str, key: str) -> Any | None:
        """Get the most recent value for (user_id, key)."""
        self._evict(user_id)
        entries = self._store.get(user_id, [])
        # Most recent first
        for entry in reversed(entries):
            if entry.key == key:
                return entry.value
        return None

    def get_recent_intents(self, user_id: str, n: int = 5) -> list[dict]:
        """Return the N most recent 'intent' entries for a user."""
        self._evict(user_id)
        entries = self._store.get(user_id, [])
        intent_entries = [e for e in entries if e.key == "intent"]
        return [e.value for e in intent_entries[-n:]]

    def clear(self, user_id: str) -> None:
        """Clear all entries for a user."""
        self._store.pop(user_id, None)

    def _evict(self, user_id: str) -> None:
        """Remove expired entries for a user."""
        now = time.monotonic()
        if user_id in self._store:
            before = len(self._store[user_id])
            self._store[user_id] = [
                e for e in self._store[user_id] if e.expires_at > now
            ]
            evicted = before - len(self._store[user_id])
            if evicted:
                logger.debug("Evicted %d stale memory entries for user=%s", evicted, user_id)


# Module-level singleton
agent_memory = AgentMemory()
