"""
executor.py
-----------
Tool orchestrator executor — routes approved plan steps to registered tools.

Called from GoalExecutionEngine ONLY after:
  1. Trust/risk score is below CRITICAL
  2. Policy engine has returned ALLOW (or REQUIRE_APPROVAL + human approved)
  3. Sandbox validator has passed

Never called directly from the LLM or intent agent.
"""

from __future__ import annotations

from loguru import logger

from sandbox.runner import run_isolated
from tools.orchestrator.registry import get_tool


async def execute_step(
    *,
    goal_type: str,
    action: str,
    entities: dict,
    user_id: str,
    refresh_token: str,
    step_index: int = 0,
) -> dict:
    """
    Execute a single plan step via the tool registry.

    Args:
        goal_type: GoalType value (e.g. "SEND_EMAIL_REPLY")
        action: Specific action within that goal type
        entities: Extracted entities from intent (to, subject, body, etc.)
        user_id: Supabase user ID (for audit logging)
        refresh_token: User's Google OAuth refresh token
        step_index: Position in the plan (for logging)

    Returns:
        {
            "success": bool,
            "result": Any,
            "error": str | None,
            "step_index": int,
            "goal_type": str,
        }
    """
    tool_fn = get_tool(goal_type)

    if tool_fn is None:
        logger.error("No tool registered for goal_type='%s'", goal_type)
        return {
            "success": False,
            "result": None,
            "error": f"No tool registered for '{goal_type}'",
            "step_index": step_index,
            "goal_type": goal_type,
        }

    label = f"step[{step_index}]:{goal_type}:{action}"
    logger.info("Executing %s for user=%s", label, user_id)

    # Build tool kwargs — tools receive entities + auth
    tool_kwargs = {
        **entities,
        "refresh_token": refresh_token,
        "user_id": user_id,
    }

    result = await run_isolated(tool_fn, timeout_seconds=30.0, step_label=label, **tool_kwargs)

    return {
        **result,
        "step_index": step_index,
        "goal_type": goal_type,
    }
