"""
rate_limiter.py
---------------
In-memory per-user rate limiter for plan executions.

Prevents abuse / runaway automation:
  - Max executions per user per hour (default: 10)
  - Configurable via environment variables

Interface is Redis-compatible so it can be swapped for a Redis backend
without changing callers.
"""

import os
import time
from collections import defaultdict
from dataclasses import dataclass

from loguru import logger


@dataclass
class RateLimitResult:
    allowed: bool
    action: str
    user_id: str
    remaining: int
    reset_in_seconds: float


class RateLimiter:
    """
    Sliding-window in-memory rate limiter.

    Stores a list of timestamps per (user_id, action) key.
    On each check, evicts timestamps outside the window.
    """

    def __init__(self):
        # { (user_id, action): [timestamp, ...] }
        self._log: dict[tuple[str, str], list[float]] = defaultdict(list)

        # Limits loaded from env (or defaults)
        self._limits: dict[str, tuple[int, int]] = {
            # action_name: (max_count, window_seconds)
            "execute": (
                int(os.getenv("RATE_LIMIT_EXECUTIONS_PER_HOUR", "10")),
                3600,
            ),
            "extract_intent": (
                int(os.getenv("RATE_LIMIT_EXTRACTIONS_PER_HOUR", "30")),
                3600,
            ),
            "default": (20, 3600),
        }

    def check(self, user_id: str, action: str = "execute") -> RateLimitResult:
        """
        Check if user is within rate limit for the given action.

        Does NOT record the attempt — call `record()` after a successful check.
        """
        max_count, window = self._limits.get(action, self._limits["default"])
        key = (user_id, action)
        now = time.monotonic()
        cutoff = now - window

        # Evict old entries
        self._log[key] = [t for t in self._log[key] if t > cutoff]

        current_count = len(self._log[key])
        allowed = current_count < max_count
        remaining = max(0, max_count - current_count)

        reset_in = 0.0
        if self._log[key]:
            oldest = self._log[key][0]
            reset_in = max(0.0, window - (now - oldest))

        if not allowed:
            logger.warning(
                "Rate limit hit: user=%s action=%s count=%d/%d",
                user_id, action, current_count, max_count,
            )

        return RateLimitResult(
            allowed=allowed,
            action=action,
            user_id=user_id,
            remaining=remaining,
            reset_in_seconds=round(reset_in, 1),
        )

    def record(self, user_id: str, action: str = "execute") -> None:
        """Record an attempt for the given user/action."""
        self._log[(user_id, action)].append(time.monotonic())

    def reset(self, user_id: str, action: str | None = None) -> None:
        """Clear rate limit state for a user (admin/testing use)."""
        if action:
            self._log.pop((user_id, action), None)
        else:
            keys = [k for k in self._log if k[0] == user_id]
            for k in keys:
                del self._log[k]


# Module-level singleton
rate_limiter = RateLimiter()
