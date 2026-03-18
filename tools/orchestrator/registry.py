"""
registry.py
-----------
Tool registry — maps GoalType values to their handler callables.

When the orchestrator executes a plan step, it looks up the tool here.
Adding new tools only requires registering them in TOOL_REGISTRY.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from loguru import logger

# Type alias
ToolFn = Callable[..., Coroutine[Any, Any, dict]]

# ── Registry ──────────────────────────────────────────────────────────────────
# Populated at import time; tools that fail to import are skipped with a warning.

TOOL_REGISTRY: dict[str, ToolFn] = {}


def _register_tools() -> None:
    try:
        from tools.gmail_tool.gmail_tool import send_reply, create_draft, forward_email
        TOOL_REGISTRY["SEND_EMAIL_REPLY"] = send_reply
        TOOL_REGISTRY["CREATE_EMAIL_DRAFT"] = create_draft
        TOOL_REGISTRY["FORWARD_EMAIL"] = forward_email
        logger.info("Registered Gmail tool actions: SEND_EMAIL_REPLY, CREATE_EMAIL_DRAFT, FORWARD_EMAIL")
    except ImportError as exc:
        logger.warning("Gmail tool not available: %s", exc)

    # Slack notifications (optional)
    try:
        from tools.slack_tool.tool import send_notification as send_slack_notification
        TOOL_REGISTRY["SEND_SLACK_NOTIFICATION"] = send_slack_notification
        logger.info("Registered Slack tool action: SEND_SLACK_NOTIFICATION")
    except ImportError as exc:
        logger.warning("Slack tool not available: %s", exc)

    # Stubs for future tools (safe no-ops until implemented)
    TOOL_REGISTRY.setdefault("NO_ACTION", _noop)
    TOOL_REGISTRY.setdefault("SCHEDULE_CALENDAR_EVENT", _stub("calendar"))
    TOOL_REGISTRY.setdefault("INITIATE_PAYMENT", _stub("payment"))
    TOOL_REGISTRY.setdefault("SEND_SLACK_NOTIFICATION", _stub("slack"))


async def _noop(**kwargs) -> dict:
    return {"success": True, "result": "no_action", "error": None}


def _stub(tool_name: str) -> ToolFn:
    async def _fn(**kwargs) -> dict:
        logger.warning("Tool '%s' is not yet implemented — skipping step", tool_name)
        return {"success": False, "result": None, "error": f"{tool_name} tool not implemented"}
    return _fn


def get_tool(goal_type: str) -> ToolFn | None:
    """Look up a tool handler by GoalType string. Returns None if not registered."""
    return TOOL_REGISTRY.get(goal_type.upper())


# Register all tools on import
_register_tools()
