"""
tool_dispatcher.py
------------------
Maps StepAction enum values to real tool function calls.

Called by the /plans/{id}/execute endpoint after human approval.
Looks up the user's refresh token from Supabase and dispatches each
step to the correct tool (Gmail / Calendar).

Dry-run mode: set dry_run=True to simulate without making API calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from agents.planner.schemas import StepAction


# ── Step result structure ─────────────────────────────────────────────────────

def _ok(action: str, **extra) -> dict:
    return {"action": action, "success": True, "error": None, **extra}

def _err(action: str, msg: str) -> dict:
    return {"action": action, "success": False, "error": msg}


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def dispatch_step(
    step: dict,                 # ExecutionStep serialized as dict
    refresh_token: str,
    email_context: dict,        # {subject, sender, body, thread_id, message_id}
    dry_run: bool = False,
) -> dict:
    """
    Execute a single plan step by dispatching to the correct tool.

    Returns a result dict: { action, success, error, ...extra }
    """
    action_str = (step.get("action") or "log_only").lower()
    params     = step.get("params") or {}
    description = step.get("description", "")

    logger.info("Dispatching step: action=%s dry_run=%s", action_str, dry_run)

    if dry_run:
        return _ok(action_str, simulated=True, description=description)

    try:
        action = StepAction(action_str)
    except ValueError:
        logger.warning("Unknown action '%s' → treating as log_only", action_str)
        action = StepAction.LOG_ONLY

    # ── Gmail actions ────────────────────────────────────────────────────────
    if action == StepAction.GMAIL_SEND_REPLY:
        from tools.gmail_tool.gmail_tool import send_reply
        result = await send_reply(
            to=params.get("to", [email_context.get("sender", "")]),
            subject="Re: " + email_context.get("subject", ""),
            body=params.get("body", description),
            thread_id=email_context.get("thread_id", ""),
            reply_to_message_id=email_context.get("message_id"),
            refresh_token=refresh_token,
        )
        return {**result, "action": action_str}

    if action == StepAction.GMAIL_SEND_EMAIL:
        from tools.gmail_tool.gmail_tool import send_reply
        result = await send_reply(
            to=params.get("to", []),
            subject=params.get("subject", email_context.get("subject", "")),
            body=params.get("body", description),
            thread_id="",
            refresh_token=refresh_token,
        )
        return {**result, "action": action_str}

    if action == StepAction.GMAIL_FORWARD:
        from tools.gmail_tool.gmail_tool import forward_email
        result = await forward_email(
            message_id=email_context.get("message_id", ""),
            to=params.get("to", []),
            note=params.get("note", description),
            refresh_token=refresh_token,
        )
        return {**result, "action": action_str}

    if action == StepAction.GMAIL_CREATE_DRAFT:
        from tools.gmail_tool.gmail_tool import create_draft
        result = await create_draft(
            to=params.get("to", [email_context.get("sender", "")]),
            subject="Re: " + email_context.get("subject", ""),
            body=params.get("body", description),
            thread_id=email_context.get("thread_id"),
            refresh_token=refresh_token,
        )
        return {**result, "action": action_str}

    # ── Calendar actions ─────────────────────────────────────────────────────
    if action == StepAction.CALENDAR_CHECK_AVAIL:
        from tools.calendar_tool.tool import check_availability
        result = await check_availability(
            refresh_token=refresh_token,
            start_iso=params.get("start_iso", datetime.now(timezone.utc).isoformat()),
            end_iso=params.get("end_iso", ""),
        )
        return {**result, "action": action_str}

    if action == StepAction.CALENDAR_CREATE_EVENT:
        from tools.calendar_tool.tool import create_event
        # Parse suggested slots or use params directly
        result = await create_event(
            refresh_token=refresh_token,
            title=params.get("title", email_context.get("subject", "Meeting")),
            start_iso=params.get("start_iso", ""),
            end_iso=params.get("end_iso", ""),
            attendees=params.get("attendees", [email_context.get("sender", "")]),
            description=params.get("description", description),
            location=params.get("location", ""),
            send_invites=True,
        )
        return {**result, "action": action_str}

    if action == StepAction.CALENDAR_UPDATE_EVENT:
        # For MVP: re-create with new time (update API is complex)
        from tools.calendar_tool.tool import create_event
        result = await create_event(
            refresh_token=refresh_token,
            title=params.get("title", "Rescheduled: " + email_context.get("subject", "Meeting")),
            start_iso=params.get("start_iso", ""),
            end_iso=params.get("end_iso", ""),
            attendees=params.get("attendees", [email_context.get("sender", "")]),
            description=params.get("description", description),
            send_invites=True,
        )
        return {**result, "action": action_str}

    if action == StepAction.CALENDAR_CANCEL_EVENT:
        from tools.calendar_tool.tool import cancel_event
        result = await cancel_event(
            refresh_token=refresh_token,
            event_id=params.get("event_id", ""),
        )
        return {**result, "action": action_str}

    # ── Notification / escalation (email) ───────────────────────────────────
    if action in (StepAction.NOTIFY_STAKEHOLDER, StepAction.ESCALATE_MANAGER):
        from tools.gmail_tool.gmail_tool import send_reply
        result = await send_reply(
            to=params.get("to", [email_context.get("sender", "")]),
            subject="Update: " + email_context.get("subject", ""),
            body=params.get("body", description),
            thread_id=email_context.get("thread_id", ""),
            refresh_token=refresh_token,
        )
        return {**result, "action": action_str}

    # ── Telegram actions ────────────────────────────────────────────────────
    if action == StepAction.TELEGRAM_SEND_MESSAGE:
        from tools.telegram_tool.tool import send_message
        result = await send_message(
            chat_id=params.get("chat_id", ""),
            text=params.get("text", description),
        )
        return {**result, "action": action_str}

    # ── Payment steps (simulation only for MVP) ──────────────────────────────
    if action in (StepAction.PAYMENT_VERIFY, StepAction.PAYMENT_INITIATE, StepAction.INVOICE_REQUEST):
        logger.info("Payment step simulated (no real integration yet): %s", action_str)
        return _ok(action_str, simulated=True, note="Payment integration not live in MVP")

    # ── Task management (simulation) ─────────────────────────────────────────
    if action in (StepAction.TASK_CREATE, StepAction.TASK_ASSIGN, StepAction.TASK_UPDATE, StepAction.TASK_ESCALATE):
        logger.info("Task step simulated: %s", action_str)
        return _ok(action_str, simulated=True, note="Task management integration coming soon")

    # ── Document steps (simulation) ──────────────────────────────────────────
    if action in (StepAction.DOC_REQUEST, StepAction.DOC_SHARE, StepAction.DOC_SUMMARIZE):
        logger.info("Document step simulated: %s", action_str)
        return _ok(action_str, simulated=True, note="Document integration coming soon")

    # ── Approval routing (email notification) ────────────────────────────────
    if action in (StepAction.APPROVAL_REQUEST, StepAction.APPROVAL_SEND):
        from tools.gmail_tool.gmail_tool import send_reply
        result = await send_reply(
            to=params.get("to", [email_context.get("sender", "")]),
            subject=("Approval Required: " if action == StepAction.APPROVAL_REQUEST else "Approved: ")
                    + email_context.get("subject", ""),
            body=params.get("body", description),
            thread_id=email_context.get("thread_id", ""),
            refresh_token=refresh_token,
        )
        return {**result, "action": action_str}

    # ── Human review / log only ──────────────────────────────────────────────
    logger.info("Log-only step: %s — %s", action_str, description)
    return _ok(action_str, note=f"Logged: {description}")


async def dispatch_plan(
    plan_steps: list[dict],
    refresh_token: str,
    email_context: dict,
    dry_run: bool = False,
) -> list[dict]:
    """
    Execute all non-approval steps in a plan sequentially.
    Human-approval steps are skipped (already approved by the time we get here).

    Returns a list of step results in order.
    """
    results = []
    for step in plan_steps:
        if step.get("requires_human_approval") and not dry_run:
            # The approval was given at the plan level — still execute the step
            pass
        try:
            result = await dispatch_step(step, refresh_token, email_context, dry_run=dry_run)
        except Exception as exc:
            logger.error("Step dispatch crashed for %s: %s", step.get("action"), exc)
            result = _err(step.get("action", "unknown"), str(exc))
        results.append(result)
    return results
