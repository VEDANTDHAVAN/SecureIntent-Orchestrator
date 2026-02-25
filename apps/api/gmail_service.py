"""
gmail_service.py
----------------
Thin wrapper around the Google API Python client for Gmail.

Responsibilities:
- Build an authenticated Gmail API service from a stored refresh token
- Fetch new message IDs since a given historyId
- Fetch and parse a full message into a plain dict
"""

import base64
import email as email_lib
import os
from datetime import datetime, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def build_gmail_service(refresh_token: str):
    """
    Build an authenticated Gmail API service using the stored refresh token
    and the app's client credentials from environment variables.

    Returns a Google API Resource object ready for API calls.
    """
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=GMAIL_SCOPES,
    )
    # Force a token refresh so the access_token is valid
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_calendar_service(refresh_token: str):
    """
    Build an authenticated Google Calendar API service from a stored refresh token.
    Reuses the same multi-scope credentials as Gmail.
    """
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=GMAIL_SCOPES,
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_new_message_ids(service, user_email: str, history_id: str) -> list[str]:
    """
    Use users.history.list() to get all messages added since history_id.

    Returns a list of message IDs (strings).
    """
    try:
        response = (
            service.users()
            .history()
            .list(
                userId=user_email,
                startHistoryId=str(history_id),
                historyTypes=["messageAdded"],
            )
            .execute()
        )
    except Exception as exc:
        # historyId may be too old (410 Gone) — caller should handle
        raise RuntimeError(f"history.list failed: {exc}") from exc

    message_ids: list[str] = []
    for record in response.get("history", []):
        for added in record.get("messagesAdded", []):
            msg_id = added.get("message", {}).get("id")
            if msg_id and msg_id not in message_ids:
                message_ids.append(msg_id)

    return message_ids


def fetch_message(service, user_email: str, message_id: str) -> dict[str, Any]:
    """
    Fetch a full message by ID using format=full.
    Returns the raw Gmail API message dict.
    """
    return (
        service.users()
        .messages()
        .get(userId=user_email, id=message_id, format="full")
        .execute()
    )


def parse_message(raw_message: dict[str, Any]) -> dict[str, Any]:
    """
    Extract subject, sender, body (plain text), and received_at
    from a raw Gmail API message dict.

    Returns:
        {
            "sender": str,
            "subject": str,
            "body": str,
            "received_at": ISO-8601 str,
            "raw_payload": dict,   # full raw Gmail payload for audit
        }
    """
    headers = {
        h["name"].lower(): h["value"]
        for h in raw_message.get("payload", {}).get("headers", [])
    }

    subject = headers.get("subject", "(no subject)")
    sender = headers.get("from", "unknown")

    # timestamp is in milliseconds since epoch
    ts_ms = int(raw_message.get("internalDate", 0))
    received_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

    body = _extract_body(raw_message.get("payload", {}))

    return {
        "sender": sender,
        "subject": subject,
        "body": body,
        "received_at": received_at,
        "raw_payload": raw_message,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _decode_part(data: str) -> str:
    """Base64url-decode a Gmail message part's data field."""
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body(payload: dict[str, Any]) -> str:
    """
    Walk the MIME tree to find a text/plain part.
    Falls back to text/html stripped of tags, then empty string.
    """
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return _decode_part(body_data)

    # Walk multipart
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result

    # Last resort: decode whatever body data exists
    if body_data:
        return _decode_part(body_data)

    return ""
