"""
error_handler.py
----------------
Per-tool retry logic and graceful fallback for the tool orchestrator.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from loguru import logger


async def with_retry(
    fn: Callable[..., Coroutine[Any, Any, dict]],
    *args: Any,
    retries: int = 2,
    delay_seconds: float = 1.0,
    fallback: dict | None = None,
    label: str = "tool",
    **kwargs: Any,
) -> dict:
    """
    Execute a tool function with retries and optional fallback.

    Args:
        fn: Async tool function to call
        retries: Number of retry attempts after initial failure
        delay_seconds: Wait time between retries
        fallback: Dict to return if all retries fail (default: error dict)
        label: Human-readable label for logging

    Returns:
        Tool result dict { success, result, error }
    """
    last_error: str = ""

    for attempt in range(retries + 1):
        try:
            result = await fn(*args, **kwargs)
            if result.get("success"):
                return result
            last_error = result.get("error", "Unknown tool error")
            logger.warning(
                "Tool '%s' returned failure on attempt %d/%d: %s",
                label, attempt + 1, retries + 1, last_error,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.error(
                "Tool '%s' raised exception on attempt %d/%d: %s",
                label, attempt + 1, retries + 1, exc,
            )

        if attempt < retries:
            await asyncio.sleep(delay_seconds)

    # All retries exhausted
    logger.error("Tool '%s' failed after %d attempts. Last error: %s", label, retries + 1, last_error)

    return fallback or {
        "success": False,
        "result": None,
        "error": f"{label} failed after {retries + 1} attempts: {last_error}",
    }
