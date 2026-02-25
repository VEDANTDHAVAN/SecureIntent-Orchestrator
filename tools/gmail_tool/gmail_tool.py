"""
gmail_tool.py
-------------
Gmail API integration — sends replies, creates drafts, and forwards emails.

Used by the tool orchestrator ONLY after trust + policy gates have passed
and human approval has been granted (when required).

Reuses build_gmail_service() from apps/api/gmail_service.py.
"""

from __future__ import annotations

import base64
import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger


def _build_service(refresh_token: str):
    """Build authenticated Gmail API service using stored refresh token."""
    from apps.api.gmail_service import build_gmail_service
    return build_gmail_service(refresh_token)


def _create_message(
    to: list[str],
    subject: str,
    body: str,
    thread_id: str | None = None,
    reply_to_message_id: str | None = None,
) -> dict:
    """Build a raw RFC2822 message dict for the Gmail API."""
    msg = MIMEMultipart("alternative")
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject

    # Threading headers — required for replies to stay in thread
    if reply_to_message_id:
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id

    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    return payload


# ── Public tool functions ──────────────────────────────────────────────────────

async def send_reply(
    *,
    to: list[str],
    subject: str,
    body: str,
    thread_id: str,
    reply_to_message_id: str | None = None,
    user_id: str = "me",
    refresh_token: str,
) -> dict:
    """
    Send a Gmail reply in an existing thread.

    Returns:
        { success: bool, message_id: str | None, error: str | None }
    """
    try:
        service = _build_service(refresh_token)
        message = _create_message(
            to=to,
            subject=subject,
            body=body,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
        )
        sent = service.users().messages().send(userId=user_id, body=message).execute()
        msg_id = sent.get("id", "")
        logger.info("Gmail reply sent: message_id=%s thread_id=%s", msg_id, thread_id)
        return {"success": True, "message_id": msg_id, "error": None}

    except Exception as exc:
        logger.error("Gmail send_reply failed: %s", exc)
        return {"success": False, "message_id": None, "error": str(exc)}


async def create_draft(
    *,
    to: list[str],
    subject: str,
    body: str,
    thread_id: str | None = None,
    user_id: str = "me",
    refresh_token: str,
) -> dict:
    """
    Create a Gmail draft (does NOT send).

    Returns:
        { success: bool, draft_id: str | None, error: str | None }
    """
    try:
        service = _build_service(refresh_token)
        message = _create_message(
            to=to, subject=subject, body=body, thread_id=thread_id
        )
        draft = (
            service.users()
            .drafts()
            .create(userId=user_id, body={"message": message})
            .execute()
        )
        draft_id = draft.get("id", "")
        logger.info("Gmail draft created: draft_id=%s", draft_id)
        return {"success": True, "draft_id": draft_id, "error": None}

    except Exception as exc:
        logger.error("Gmail create_draft failed: %s", exc)
        return {"success": False, "draft_id": None, "error": str(exc)}


async def forward_email(
    *,
    message_id: str,
    to: list[str],
    note: str = "",
    user_id: str = "me",
    refresh_token: str,
) -> dict:
    """
    Forward an existing email to new recipients.

    Returns:
        { success: bool, message_id: str | None, error: str | None }
    """
    try:
        service = _build_service(refresh_token)

        # Fetch the original message
        original = (
            service.users()
            .messages()
            .get(userId=user_id, id=message_id, format="raw")
            .execute()
        )
        raw_msg = base64.urlsafe_b64decode(original["raw"].encode("utf-8"))
        parsed = email_lib.message_from_bytes(raw_msg)

        # Build forward
        fwd = MIMEMultipart()
        fwd["To"] = ", ".join(to)
        fwd["Subject"] = "Fwd: " + parsed.get("Subject", "")
        if note:
            fwd.attach(MIMEText(note, "plain"))

        # Re-attach original body
        orig_body = ""
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_type() == "text/plain":
                    orig_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
        else:
            orig_body = parsed.get_payload(decode=True).decode("utf-8", errors="replace")

        fwd.attach(MIMEText(f"\n\n---------- Forwarded message ----------\n{orig_body}", "plain"))

        raw = base64.urlsafe_b64encode(fwd.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId=user_id, body={"raw": raw}).execute()
        sent_id = sent.get("id", "")
        logger.info("Gmail forwarded: new_message_id=%s", sent_id)
        return {"success": True, "message_id": sent_id, "error": None}

    except Exception as exc:
        logger.error("Gmail forward_email failed: %s", exc)
        return {"success": False, "message_id": None, "error": str(exc)}
