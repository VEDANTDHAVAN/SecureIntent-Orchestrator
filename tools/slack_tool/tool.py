"""
slack_tool/tool.py
-------------------
Minimal Slack integration for SecureIntent.

This module exposes a single public function:

    async def send_notification(...)

which posts a message to a Slack channel via an **Incoming Webhook URL**.

Configuration
-------------
- SLACK_WEBHOOK_URL (required unless passed explicitly):
    The Slack Incoming Webhook URL for your workspace/channel.
- SLACK_ENVIRONMENT_TAG (optional):
    If set (e.g. "dev", "staging", "prod"), it is prefixed in the message
    to make it easy to see which environment generated the notification.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Optional

import httpx
from loguru import logger


async def send_notification(
    *,
    text: str,
    blocks: Optional[Iterable[Dict[str, Any]]] = None,
    webhook_url: Optional[str] = None,
    username: str = "SecureIntent Bot",
    icon_emoji: str = ":shield:",
) -> dict:
    """
    Send a notification to Slack via Incoming Webhook.

    Args:
        text: Fallback text for the message (also used by clients that don't
              render blocks). REQUIRED by Slack.
        blocks: Optional iterable of Block Kit block dicts.
        webhook_url: Optional override for the webhook URL. If not provided,
                     SLACK_WEBHOOK_URL from environment is used.
        username: Display name for the bot/user in Slack.
        icon_emoji: Emoji icon for the bot (e.g. ':shield:').

    Returns:
        {
            "success": bool,
            "status_code": int,
            "error": str | None,
        }
    """
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        msg = "SLACK_WEBHOOK_URL not configured"
        logger.error("Slack notification failed: %s", msg)
        return {"success": False, "status_code": 0, "error": msg}

    env_tag = os.getenv("SLACK_ENVIRONMENT_TAG") or os.getenv("APP_ENV") or ""
    prefixed_text = text
    if env_tag:
        prefixed_text = f"[{env_tag}] {text}"

    payload: Dict[str, Any] = {
        "text": prefixed_text,
        "username": username,
        "icon_emoji": icon_emoji,
    }
    if blocks:
        payload["blocks"] = list(blocks)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        if 200 <= resp.status_code < 300:
            logger.info("Slack notification sent successfully (status=%s)", resp.status_code)
            return {"success": True, "status_code": resp.status_code, "error": None}

        body = resp.text
        logger.error(
            "Slack notification failed with status=%s body=%s",
            resp.status_code,
            body[:500],
        )
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": f"Slack API error: {body}",
        }
    except Exception as exc:  # pragma: no cover - network failure
        logger.error("Slack notification crashed: %s", exc)
        return {"success": False, "status_code": 0, "error": str(exc)}

