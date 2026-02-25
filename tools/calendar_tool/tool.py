"""
calendar_tool/tool.py
---------------------
Google Calendar API integration.

Functions:
  check_availability()  — free/busy check for a time range
  suggest_slots()       — find 3 free slots in the coming week
  create_event()        — create a Calendar event and invite attendees
  cancel_event()        — cancel/delete a Calendar event
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger


def _build_service(refresh_token: str):
    """Build authenticated Google Calendar API service."""
    from apps.api.gmail_service import build_calendar_service
    return build_calendar_service(refresh_token)


# ── Public tool functions ──────────────────────────────────────────────────────

async def check_availability(
    *,
    refresh_token: str,
    start_iso: str,                 # ISO-8601 datetime string
    end_iso: str,
    calendar_id: str = "primary",
) -> dict:
    """
    Check free/busy for the user's primary calendar.

    Returns:
        { available: bool, busy_slots: list[{start, end}], error: str|None }
    """
    try:
        service = _build_service(refresh_token)
        body = {
            "timeMin": start_iso,
            "timeMax": end_iso,
            "items": [{"id": calendar_id}],
        }
        result = service.freebusy().query(body=body).execute()
        busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])
        available = len(busy) == 0
        logger.info("Availability check: available=%s busy_count=%d", available, len(busy))
        return {"available": available, "busy_slots": busy, "error": None}
    except Exception as exc:
        logger.error("check_availability failed: %s", exc)
        return {"available": False, "busy_slots": [], "error": str(exc)}


async def suggest_slots(
    *,
    refresh_token: str,
    duration_mins: int = 60,
    preferred_week_offset: int = 0,     # 0 = this week, 1 = next week
    calendar_id: str = "primary",
    working_hours: tuple[int, int] = (9, 18),   # 9 AM – 6 PM
) -> dict:
    """
    Suggest up to 3 free time slots in a given week.

    Returns:
        { slots: list[{start, end, label}], error: str|None }
    """
    try:
        service = _build_service(refresh_token)
        # Build the search window
        now = datetime.now(timezone.utc)
        week_start = now + timedelta(weeks=preferred_week_offset)
        # Align to Monday
        week_start = week_start - timedelta(days=week_start.weekday())
        week_start = week_start.replace(hour=working_hours[0], minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=5)   # Mon–Fri only

        body = {
            "timeMin": week_start.isoformat(),
            "timeMax": week_end.isoformat(),
            "items": [{"id": calendar_id}],
        }
        result = service.freebusy().query(body=body).execute()
        busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])

        # Build free slots by scanning the week in duration_mins increments
        busy_ranges = [
            (
                datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(b["end"].replace("Z", "+00:00")),
            )
            for b in busy
        ]

        slots = []
        cursor = week_start
        delta = timedelta(minutes=duration_mins)

        while cursor < week_end and len(slots) < 3:
            # Only suggest during working hours
            if cursor.hour < working_hours[0] or cursor.hour >= working_hours[1]:
                cursor = cursor.replace(hour=working_hours[0], minute=0) + timedelta(days=1)
                continue

            slot_end = cursor + delta
            overlap = any(bs < slot_end and be > cursor for bs, be in busy_ranges)
            if not overlap:
                slots.append({
                    "start": cursor.isoformat(),
                    "end": slot_end.isoformat(),
                    "label": cursor.strftime("%A %d %b, %I:%M %p"),
                })
            cursor += delta

        logger.info("Suggested %d slots", len(slots))
        return {"slots": slots, "error": None}
    except Exception as exc:
        logger.error("suggest_slots failed: %s", exc)
        return {"slots": [], "error": str(exc)}


async def create_event(
    *,
    refresh_token: str,
    title: str,
    start_iso: str,                 # ISO-8601 with timezone
    end_iso: str,
    attendees: list[str],
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
    send_invites: bool = True,
) -> dict:
    """
    Create a Google Calendar event and optionally send invites.

    Returns:
        { success: bool, event_id: str|None, event_link: str|None, error: str|None }
    """
    try:
        service = _build_service(refresh_token)
        event_body: dict[str, Any] = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end":   {"dateTime": end_iso,   "timeZone": "UTC"},
            "attendees": [{"email": e} for e in attendees],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email",  "minutes": 24 * 60},
                    {"method": "popup",  "minutes": 15},
                ],
            },
        }
        send_notifications = "all" if send_invites else "none"
        result = (
            service.events()
            .insert(calendarId=calendar_id, body=event_body, sendNotifications=send_notifications)
            .execute()
        )
        event_id   = result.get("id")
        event_link = result.get("htmlLink")
        logger.info("Calendar event created: id=%s link=%s", event_id, event_link)
        return {"success": True, "event_id": event_id, "event_link": event_link, "error": None}
    except Exception as exc:
        logger.error("create_event failed: %s", exc)
        return {"success": False, "event_id": None, "event_link": None, "error": str(exc)}


async def cancel_event(
    *,
    refresh_token: str,
    event_id: str,
    calendar_id: str = "primary",
) -> dict:
    """
    Cancel (delete) a Calendar event and send cancellation emails.

    Returns:
        { success: bool, error: str|None }
    """
    try:
        service = _build_service(refresh_token)
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendNotifications=True,
        ).execute()
        logger.info("Calendar event cancelled: event_id=%s", event_id)
        return {"success": True, "error": None}
    except Exception as exc:
        logger.error("cancel_event failed: %s", exc)
        return {"success": False, "error": str(exc)}
