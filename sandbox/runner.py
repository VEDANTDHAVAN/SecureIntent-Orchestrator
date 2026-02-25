"""
runner.py
---------
Controlled async execution wrapper with timeout and error isolation.

Ensures no single step can hang indefinitely or crash the whole pipeline.
"""

import asyncio
from typing import Any, Callable, Coroutine

from loguru import logger


async def run_with_timeout(
    coro: Coroutine[Any, Any, Any],
    timeout_seconds: float = 30.0,
    label: str = "task",
) -> Any:
    """
    Run a coroutine with a hard timeout.

    Args:
        coro: The coroutine to run
        timeout_seconds: Max seconds before TimeoutError is raised
        label: Human-readable label for logging

    Raises:
        asyncio.TimeoutError if the coroutine doesn't complete in time
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error("Timeout after %.1fs executing '%s'", timeout_seconds, label)
        raise


async def run_isolated(
    step_fn: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    timeout_seconds: float = 30.0,
    step_label: str = "step",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Run a single step function in isolation.

    Catches all exceptions and returns a structured result dict
    so a single step failure doesn't crash the whole pipeline.

    Returns:
        {
            "success": bool,
            "result": Any | None,
            "error": str | None,
        }
    """
    try:
        result = await run_with_timeout(
            step_fn(*args, **kwargs),
            timeout_seconds=timeout_seconds,
            label=step_label,
        )
        return {"success": True, "result": result, "error": None}

    except asyncio.TimeoutError:
        return {
            "success": False,
            "result": None,
            "error": f"Step '{step_label}' timed out after {timeout_seconds}s",
        }
    except Exception as exc:
        logger.error("Step '%s' failed: %s", step_label, exc)
        return {
            "success": False,
            "result": None,
            "error": str(exc),
        }
