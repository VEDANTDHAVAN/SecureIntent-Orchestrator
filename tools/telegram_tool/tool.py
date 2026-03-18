"""
telegram_tool/tool.py
-------------------
Telegram bot integration for SecureIntent.

Configuration
-------------
- TELEGRAM_BOT_TOKEN (required):
    The bot token provided by BotFather.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from loguru import logger


async def send_message(
    *,
    chat_id: str,
    text: str,
    token: Optional[str] = None,
    **kwargs: Any,
) -> dict:
    """
    Send a message to a Telegram chat.

    Args:
        chat_id: The unique identifier for the target chat or username of the target channel.
        text: Text of the message to be sent.
        token: Optional override for the bot token. If not provided,
               TELEGRAM_BOT_TOKEN from environment is used.

    Returns:
        {
            "success": bool,
            "status_code": int,
            "error": str | None,
        }
    """
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        msg = "TELEGRAM_BOT_TOKEN not configured"
        logger.error("Telegram message failed: %s", msg)
        return {"success": False, "status_code": 0, "error": msg}

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        
        if 200 <= resp.status_code < 300:
            logger.info("Telegram message sent successfully to {}", chat_id)
            return {"success": True, "status_code": resp.status_code, "error": None}

        body = resp.json()
        error_msg = body.get("description", resp.text)
        logger.error(
            "Telegram message failed for chat_id={} with status={} body={}",
            chat_id,
            resp.status_code,
            error_msg,
        )
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": f"Telegram API error (chat_id={chat_id}): {error_msg}",
        }
    except Exception as exc:
        logger.error("Telegram message crashed: %s", exc)
        return {"success": False, "status_code": 0, "error": str(exc)}
