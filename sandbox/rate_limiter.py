"""
Rate Limiter — Sliding window rate limiting.
Per-tool and per-user request throttling.
"""

from __future__ import annotations

import time
from collections import defaultdict
from shared.logger import get_logger
from shared.constants import (
    DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    DEFAULT_RATE_LIMIT_PER_TOOL_MAX,
)
from .schemas import RateLimitStatus

logger = get_logger("sandbox.rate_limiter")


class RateLimiter:
    """
    Sliding window rate limiter.
    
    Tracks requests per (tool_name, user_id) pair using an in-memory
    store. In production, replace with Redis for distributed rate limiting.
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_RATE_LIMIT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        per_tool_max: int = DEFAULT_RATE_LIMIT_PER_TOOL_MAX,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.per_tool_max = per_tool_max
        # Stores timestamps of requests: {key: [timestamp1, timestamp2, ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, tool_name: str, user_id: str = "") -> RateLimitStatus:
        """
        Check if a request is allowed under rate limits.

        Args:
            tool_name: Name of the tool being invoked.
            user_id: Optional user identifier.

        Returns:
            RateLimitStatus indicating whether the request is allowed.
        """
        now = time.time()
        key = self._make_key(tool_name, user_id)

        # Clean expired entries
        self._cleanup(key, now)

        current_count = len(self._requests[key])
        limit = self.per_tool_max
        is_allowed = current_count < limit

        retry_after = 0.0
        if not is_allowed and self._requests[key]:
            oldest = self._requests[key][0]
            retry_after = max(0.0, self.window_seconds - (now - oldest))

        return RateLimitStatus(
            tool_name=tool_name,
            user_id=user_id,
            is_allowed=is_allowed,
            current_count=current_count,
            max_allowed=limit,
            window_seconds=self.window_seconds,
            retry_after_seconds=round(retry_after, 2),
        )

    def record(self, tool_name: str, user_id: str = ""):
        """
        Record a request (call this after allowing the request).
        """
        now = time.time()
        key = self._make_key(tool_name, user_id)
        self._cleanup(key, now)
        self._requests[key].append(now)

    def check_and_record(
        self, tool_name: str, user_id: str = ""
    ) -> RateLimitStatus:
        """
        Check rate limit and record in one call.
        Only records if the request is allowed.
        """
        status = self.check(tool_name, user_id)
        if status.is_allowed:
            self.record(tool_name, user_id)
            status.current_count += 1
        return status

    def reset(self, tool_name: str = "", user_id: str = ""):
        """Reset rate limit counters."""
        if tool_name or user_id:
            key = self._make_key(tool_name, user_id)
            self._requests.pop(key, None)
        else:
            self._requests.clear()

    def _cleanup(self, key: str, now: float):
        """Remove expired timestamps outside the sliding window."""
        cutoff = now - self.window_seconds
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > cutoff
        ]

    @staticmethod
    def _make_key(tool_name: str, user_id: str) -> str:
        """Create a composite key for the rate limit store."""
        return f"{tool_name}:{user_id}" if user_id else tool_name
