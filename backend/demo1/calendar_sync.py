"""
calendar_sync.py
================
ParaIQ — Calendar sync layer: iCal export, Google Calendar, Outlook Calendar.

Endpoints:
  GET  /calendar/sync/ical.ics       — Download iCal feed for the firm
  GET  /calendar/sync/ical-url       — Get a persistent iCal subscription URL
  POST /calendar/sync/google/start   — Start Google Calendar OAuth flow
  GET  /calendar/sync/google/callback — Google OAuth callback
  POST /calendar/sync/google/push    — Push events to Google Calendar
  POST /calendar/sync/outlook/start   — Start Outlook Calendar OAuth flow
  GET  /calendar/sync/outlook/callback — Outlook OAuth callback
  POST /calendar/sync/outlook/push    — Push events to Outlook Calendar
  GET  /calendar/sync/status          — Check sync status for all providers
  POST /calendar/sync/disconnect      — Disconnect a provider
"""
import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_user, get_current_firm_id

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID", "")       # reuse same Google OAuth app
GOOGLE_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI",
                                  os.getenv("GMAIL_REDIRECT_URI", ""))

OUTLOOK_CLIENT_ID     = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_REDIRECT_URI  = os.getenv("OUTLOOK_CALENDAR_REDIRECT_URI",
                                   os.getenv("OUTLOOK_REDIRECT_URI", ""))
OUTLOOK_TENANT_ID     = os.getenv("OUTLOOK_TENANT_ID", "common")

# iCal feed tokens — stored per firm for persistent subscription URLs
_ICAL_TOKENS: Dict[str, str] = {}  # firm_id → token (in production, store in DB)


# ── iCal Generation ───────────────────────────────────────────────────────────

def _escape_ical(text: str) -> str:
    """Escape special characters for iCal format."""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _format_ical_dt(dt_str: str, has_time: bool = False) -> str:
    """Convert a date/datetime string to iCal format."""
    try:
        if has_time:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%Y%m%dT%H%M%S")
        else:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%Y%m%d")
    except (ValueError, TypeError):
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            return dt.strftime("%Y%m%d")
        except (ValueError, TypeError):
            return datetime.now().strftime("%Y%m%d")


def _get_firm_events_for_ical(firm_id: str, days_ahead: int = 365) -> List[dict]:
    """Fetch all upcoming events for a firm, for iCal export."""
    cutoff = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today  = datetime.now().strftime("%Y-%m-%d")
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute(
                """
                SELECT id, matter_id, title, event_type, due_date, due_time,
                       location, description, status, is_court_date,
                       reminder_days, attendees
                FROM calendar_events
                WHERE due_date BETWEEN %s AND %s
                  AND status NOT IN ('cancelled')
                ORDER BY due_date ASC
                """,
                (today, cutoff)
            ).fetchall()
            return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"[CalendarSync] Failed to fetch events for iCal: {e}")
        return []


def generate_ical_feed(firm_id: str) -> str:
    """Generate a complete iCal feed for a firm's calendar events."""
    events = _get_firm_events_for_ical(firm_id)
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ParaIQ//Legal Intelligence Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:ParaIQ Deadlines ({firm_id})",
        "X-WR-TIMEZONE:America/New_York",
    ]

    for ev in events:
        has_time = bool(ev.get("due_time"))
        dt_start = _format_ical_dt(ev["due_date"], has_time)
        dt_end_val = ev["due_date"]
        if has_time:
            try:
                start_dt = datetime.fromisoformat(f"{ev['due_date']}T{ev['due_time']}")
                end_dt = start_dt + timedelta(hours=1)
                dt_end = end_dt.strftime("%Y%m%dT%H%M%S")
            except (ValueError, TypeError):
                dt_end = dt_start
        else:
            try:
                start_dt = datetime.strptime(ev["due_date"], "%Y-%m-%d")
                end_dt = start_dt + timedelta(days=1)
                dt_end = end_dt.strftime("%Y%m%d")
            except (ValueError, TypeError):
                dt_end = dt_start

        uid = f"paraiq-{ev['id']}@paraiq.legal"
        summary = ev.get("title", "ParaIQ Event")
        if ev.get("is_court_date"):
            summary = f"[Court] {summary}"
        if ev.get("event_type"):
            summary = f"[{ev['event_type'].upper()}] {summary}"

        desc_parts = []
        if ev.get("description"):
            desc_parts.append(ev["description"])
        if ev.get("matter_id"):
            desc_parts.append(f"Matter ID: {ev['matter_id']}")
        if ev.get("attendees"):
            desc_parts.append(f"Attendees: {ev['attendees']}")
        desc_parts.append("Synced from ParaIQ Legal Intelligence Platform")
        description = "\\n".join(desc_parts)

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{'VALUE=DATE:' if not has_time else ''}{dt_start}",
            f"DTEND:{'VALUE=DATE:' if not has_time else ''}{dt_end}",
            f"SUMMARY:{_escape_ical(summary)}",
            f"DESCRIPTION:{_escape_ical(description)}",
        ])

        if ev.get("location"):
            lines.append(f"LOCATION:{_escape_ical(ev['location'])}")

        if ev.get("reminder_days") and ev["reminder_days"] > 0:
            lines.extend([
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_escape_ical(summary)}",
                f"TRIGGER:-P{ev['reminder_days']}D",
                "END:VALARM",
            ])

        # Status
        if ev.get("status") == "completed":
            lines.append("STATUS:COMPLETED")
        elif ev.get("status") == "rescheduled":
            lines.append("STATUS:TENTATIVE")
        else:
            lines.append("STATUS:CONFIRMED")

        # Categories
        if ev.get("event_type"):
            lines.append(f"CATEGORIES:{_escape_ical(ev['event_type'].upper())}")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


# ── iCal Routes ───────────────────────────────────────────────────────────────

@router.get("/sync/ical.ics")
async def export_ical(
    token: str = Query(..., description="Firm iCal token"),
):
    """Download the firm's calendar as an iCal (.ics) file."""
    # Find firm_id by token
    firm_id = None
    for fid, tok in _ICAL_TOKENS.items():
        if tok == token:
            firm_id = fid
            break

    if not firm_id:
        raise HTTPException(401, "Invalid iCal token")

    ical_content = generate_ical_feed(firm_id)
    return PlainTextResponse(
        content=ical_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f"attachment; filename=paraiq-calendar-{firm_id}.ics"
        }
    )


@router.get("/sync/ical-url")
async def get_ical_url(
    request: Request,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Get or generate a persistent iCal subscription URL for the firm."""
    if firm_id not in _ICAL_TOKENS:
        _ICAL_TOKENS[firm_id] = secrets.token_urlsafe(32)

    token = _ICAL_TOKENS[firm_id]
    base_url = str(request.base_url).rstrip("/")
    url = f"{base_url}/calendar/sync/ical.ics?token={token}"

    return {
        "url": url,
        "token": token,
        "instructions": "Add this URL to Google Calendar, Apple Calendar, or Outlook as a new calendar subscription.",
    }


# ── Google Calendar OAuth ─────────────────────────────────────────────────────

@router.post("/sync/google/start")
async def google_calendar_start(
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Start the Google Calendar OAuth flow."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google Calendar integration is not configured. Set GMAIL_CLIENT_ID env var.")

    state = secrets.token_urlsafe(16)
    # Store state → firm_id mapping (in production, use DB or Redis)
    _GOOGLE_STATES[state] = firm_id

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar.events",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"auth_url": auth_url}


_GOOGLE_STATES: Dict[str, str] = {}  # state → firm_id (in production, use DB)


@router.get("/sync/google/callback")
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle Google OAuth callback — exchanges code for tokens."""
    firm_id = _GOOGLE_STATES.pop(state, None)
    if not firm_id:
        raise HTTPException(400, "Invalid or expired OAuth state")

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=15
            )
            resp.raise_for_status()
            tokens = resp.json()

        # In production, store tokens in DB encrypted per firm
        _GOOGLE_TOKENS[firm_id] = tokens

        return RedirectResponse(
            url="/calendar?sync=google&status=connected",
            status_code=302
        )
    except httpx.HTTPError as e:
        logger.error(f"[CalendarSync] Google OAuth failed: {e}")
        raise HTTPException(400, f"Google Calendar connection failed: {e}")


_GOOGLE_TOKENS: Dict[str, dict] = {}  # firm_id → tokens (in production, use DB)


@router.post("/sync/google/push")
async def google_calendar_push(
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Push all upcoming ParaIQ events to Google Calendar."""
    tokens = _GOOGLE_TOKENS.get(firm_id)
    if not tokens:
        raise HTTPException(400, "Google Calendar not connected. Run /sync/google/start first.")

    access_token = tokens.get("access_token")
    events = _get_firm_events_for_ical(firm_id, days_ahead=90)

    if not events:
        return {"pushed": 0, "message": "No events to push"}

    pushed = 0
    errors = 0

    async with httpx.AsyncClient() as http:
        for ev in events:
            # Check if already synced (by UID in extended properties)
            uid = f"paraiq-{ev['id']}@paraiq.legal"
            has_time = bool(ev.get("due_time"))

            # Build event body
            start = {"date": ev["due_date"]} if not has_time else {
                "dateTime": f"{ev['due_date']}T{ev['due_time']}:00"
            }
            end = {"date": ev["due_date"]} if not has_time else {
                "dateTime": f"{ev['due_date']}T{ev['due_time']}:00",
                "timeZone": "America/New_York",
            }
            if not has_time:
                try:
                    end_date = (datetime.strptime(ev["due_date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                    end = {"date": end_date}
                except (ValueError, TypeError):
                    pass

            body = {
                "summary": f"[{ev.get('event_type', 'event').upper()}] {ev['title']}",
                "description": ev.get("description", "") + "\n\nSynced from ParaIQ",
                "location": ev.get("location", ""),
                "start": start,
                "end": end,
                "extendedProperties": {
                    "private": {"paraiq_id": str(ev["id"]), "paraiq_uid": uid}
                },
            }

            try:
                # Try to find existing event by iCalUID
                search_resp = await http.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    params={"iCalUID": uid},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10
                )

                if search_resp.status_code == 200 and search_resp.json().get("items"):
                    # Update existing
                    existing_id = search_resp.json()["items"][0]["id"]
                    resp = await http.put(
                        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{existing_id}",
                        json=body,
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=10
                    )
                else:
                    # Create new
                    body["iCalUID"] = uid
                    resp = await http.post(
                        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                        json=body,
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=10
                    )

                if resp.status_code in (200, 201):
                    pushed += 1
                else:
                    errors += 1
                    logger.warning(f"[CalendarSync] Google push failed for event {ev['id']}: {resp.status_code}")

            except (httpx.HTTPError, httpx.TimeoutException) as e:
                errors += 1
                logger.error(f"[CalendarSync] Google push error for event {ev['id']}: {e}")

    return {
        "pushed": pushed,
        "errors": errors,
        "total": len(events),
        "provider": "google",
    }


# ── Outlook Calendar OAuth ────────────────────────────────────────────────────

_OUTLOOK_STATES: Dict[str, str] = {}
_OUTLOOK_TOKENS: Dict[str, dict] = {}


@router.post("/sync/outlook/start")
async def outlook_calendar_start(
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Start the Outlook Calendar OAuth flow."""
    if not OUTLOOK_CLIENT_ID:
        raise HTTPException(500, "Outlook Calendar integration is not configured. Set OUTLOOK_CLIENT_ID env var.")

    state = secrets.token_urlsafe(16)
    _OUTLOOK_STATES[state] = firm_id

    params = {
        "client_id": OUTLOOK_CLIENT_ID,
        "redirect_uri": OUTLOOK_REDIRECT_URI,
        "response_type": "code",
        "scope": "Calendars.ReadWrite offline_access",
        "state": state,
    }
    auth_url = f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/authorize?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/sync/outlook/callback")
async def outlook_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle Outlook OAuth callback."""
    firm_id = _OUTLOOK_STATES.pop(state, None)
    if not firm_id:
        raise HTTPException(400, "Invalid or expired OAuth state")

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "code": code,
                    "client_id": OUTLOOK_CLIENT_ID,
                    "client_secret": OUTLOOK_CLIENT_SECRET,
                    "redirect_uri": OUTLOOK_REDIRECT_URI,
                    "grant_type": "authorization_code",
                    "scope": "Calendars.ReadWrite offline_access",
                },
                timeout=15
            )
            resp.raise_for_status()
            tokens = resp.json()

        _OUTLOOK_TOKENS[firm_id] = tokens
        return RedirectResponse(
            url="/calendar?sync=outlook&status=connected",
            status_code=302
        )
    except httpx.HTTPError as e:
        logger.error(f"[CalendarSync] Outlook OAuth failed: {e}")
        raise HTTPException(400, f"Outlook Calendar connection failed: {e}")


@router.post("/sync/outlook/push")
async def outlook_calendar_push(
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Push all upcoming ParaIQ events to Outlook Calendar."""
    tokens = _OUTLOOK_TOKENS.get(firm_id)
    if not tokens:
        raise HTTPException(400, "Outlook Calendar not connected. Run /sync/outlook/start first.")

    access_token = tokens.get("access_token")
    events = _get_firm_events_for_ical(firm_id, days_ahead=90)

    if not events:
        return {"pushed": 0, "message": "No events to push"}

    pushed = 0
    errors = 0

    async with httpx.AsyncClient() as http:
        for ev in events:
            has_time = bool(ev.get("due_time"))
            uid = f"paraiq-{ev['id']}@paraiq.legal"

            if has_time:
                start = {"dateTime": f"{ev['due_date']}T{ev['due_time']}:00", "timeZone": "America/New_York"}
                end_dt = datetime.fromisoformat(f"{ev['due_date']}T{ev['due_time']}") + timedelta(hours=1)
                end = {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "America/New_York"}
            else:
                start = {"date": ev["due_date"], "timeZone": "America/New_York"}
                try:
                    end_date = (datetime.strptime(ev["due_date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    end_date = ev["due_date"]
                end = {"date": end_date, "timeZone": "America/New_York"}

            body = {
                "subject": f"[{ev.get('event_type', 'event').upper()}] {ev['title']}",
                "body": {"contentType": "Text", "content": ev.get("description", "") + "\n\nSynced from ParaIQ"},
                "location": {"displayName": ev.get("location", "")},
                "start": start,
                "end": end,
                "categories": [ev.get("event_type", "other")],
                "iCalUId": uid,
            }

            try:
                # Check if event already exists by iCalUId
                search_resp = await http.get(
                    "https://graph.microsoft.com/v1.0/me/events",
                    params={"$filter": f"iCalUId eq '{uid}'"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10
                )

                if search_resp.status_code == 200 and search_resp.json().get("value"):
                    existing_id = search_resp.json()["value"][0]["id"]
                    resp = await http.patch(
                        f"https://graph.microsoft.com/v1.0/me/events/{existing_id}",
                        json=body,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        timeout=10
                    )
                else:
                    resp = await http.post(
                        "https://graph.microsoft.com/v1.0/me/events",
                        json=body,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        timeout=10
                    )

                if resp.status_code in (200, 201):
                    pushed += 1
                else:
                    errors += 1
                    logger.warning(f"[CalendarSync] Outlook push failed for event {ev['id']}: {resp.status_code}")

            except (httpx.HTTPError, httpx.TimeoutException) as e:
                errors += 1
                logger.error(f"[CalendarSync] Outlook push error for event {ev['id']}: {e}")

    return {
        "pushed": pushed,
        "errors": errors,
        "total": len(events),
        "provider": "outlook",
    }


# ── Status & Disconnect ───────────────────────────────────────────────────────

@router.get("/sync/status")
async def sync_status(
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Check calendar sync status for all providers."""
    ical_token = _ICAL_TOKENS.get(firm_id)
    return {
        "ical": {
            "connected": ical_token is not None,
            "has_url": ical_token is not None,
        },
        "google": {
            "connected": firm_id in _GOOGLE_TOKENS,
        },
        "outlook": {
            "connected": firm_id in _OUTLOOK_TOKENS,
        },
    }


class DisconnectRequest(BaseModel):
    provider: str  # "google", "outlook", "ical"


@router.post("/sync/disconnect")
async def disconnect_sync(
    req: DisconnectRequest,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Disconnect a calendar sync provider."""
    if req.provider == "google":
        _GOOGLE_TOKENS.pop(firm_id, None)
    elif req.provider == "outlook":
        _OUTLOOK_TOKENS.pop(firm_id, None)
    elif req.provider == "ical":
        _ICAL_TOKENS.pop(firm_id, None)
    else:
        raise HTTPException(400, f"Unknown provider: {req.provider}")

    return {"disconnected": req.provider}
