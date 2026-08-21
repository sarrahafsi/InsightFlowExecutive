"""Fetches calendar events from Google Calendar API."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx

from .models import CalendarEvent

logger = logging.getLogger(__name__)

COLOR = "#EA4335"
GCAL_API = "https://www.googleapis.com/calendar/v3"


def _load_token(org_id: str | None = None) -> str | None:
    try:
        from application.routes.auth import get_gmail_credentials
        creds = get_gmail_credentials(org_id=org_id)
        if creds and creds.valid:
            return creds.token
    except Exception as e:
        logger.warning("[GoogleCalendar] Cannot load token: %s", e)
    return None


def _mock_events(start: datetime, end: datetime) -> list[CalendarEvent]:
    monday = start.replace(hour=0, minute=0, second=0, microsecond=0)
    events = [
        CalendarEvent(
            id="gcal_mock_001",
            source="google_calendar",
            title="Weekly Team Sync",
            start=monday.replace(hour=11, minute=0, second=0, microsecond=0),
            end=monday.replace(hour=12, minute=0, second=0, microsecond=0),
            location="Google Meet",
            description="Sync hebdomadaire de toute l'équipe.",
            attendees=[
                {"name": "Sophie Martin",  "email": "s.martin@company.com"},
                {"name": "Karim Haddad",   "email": "k.haddad@company.com"},
            ],
            color=COLOR,
            organizer="CEO",
        ),
        CalendarEvent(
            id="gcal_mock_002",
            source="google_calendar",
            title="Product Review",
            start=(monday + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0),
            end=(monday + timedelta(days=2)).replace(hour=16, minute=0, second=0, microsecond=0),
            location="Google Meet",
            description="Revue des nouvelles fonctionnalités produit avec l'équipe.",
            attendees=[
                {"name": "Léa Fontaine", "email": "l.fontaine@company.com"},
                {"name": "Karim Haddad", "email": "k.haddad@company.com"},
            ],
            color=COLOR,
            organizer="CEO",
        ),
        CalendarEvent(
            id="gcal_mock_003",
            source="google_calendar",
            title="OKR Planning",
            start=(monday + timedelta(days=4)).replace(hour=9, minute=0, second=0, microsecond=0),
            end=(monday + timedelta(days=4)).replace(hour=10, minute=0, second=0, microsecond=0),
            location="Salle Strategy",
            description="Définition et alignement des OKRs pour le prochain trimestre.",
            attendees=[
                {"name": "Marie Dupont",  "email": "m.dupont@company.com"},
                {"name": "Ahmed Ben Ali", "email": "a.benali@company.com"},
            ],
            color=COLOR,
            organizer="CEO",
        ),
    ]
    return [e for e in events if e.start >= start and e.start < end]


async def fetch_google_calendar(start: datetime, end: datetime, org_id: str | None = None) -> list[CalendarEvent]:
    token = _load_token(org_id=org_id)
    if not token:
        logger.info("[GoogleCalendar] No token — returning mock events")
        return _mock_events(start, end)

    time_min = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "timeMin":      time_min,
        "timeMax":      time_max,
        "singleEvents": "true",
        "orderBy":      "startTime",
        "maxResults":   50,
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{GCAL_API}/calendars/primary/events", headers=headers, params=params)
            if r.status_code == 403 or r.status_code == 401:
                # Token exists but calendar scope not granted — silent mock fallback
                logger.info("[GoogleCalendar] Scope not granted (%s) — returning mock", r.status_code)
                return _mock_events(start, end)
            if r.status_code != 200:
                logger.warning("[GoogleCalendar] API %s — fallback to mock", r.status_code)
                return _mock_events(start, end)

            events: list[CalendarEvent] = []
            for item in r.json().get("items", []):
                try:
                    s = item.get("start", {})
                    e = item.get("end", {})
                    all_day   = "date" in s and "dateTime" not in s
                    start_str = s.get("dateTime") or s.get("date", "") + "T00:00:00"
                    end_str   = e.get("dateTime") or e.get("date", "") + "T00:00:00"
                    ev_start  = datetime.fromisoformat(start_str.rstrip("Z"))
                    ev_end    = datetime.fromisoformat(end_str.rstrip("Z"))

                    creator  = item.get("creator", {})
                    org_name = creator.get("displayName") or creator.get("email", "")
                    attendees = [
                        {
                            "name":  a.get("displayName") or a.get("email", ""),
                            "email": a.get("email", ""),
                        }
                        for a in item.get("attendees", [])
                        if not a.get("self", False)
                    ]
                    events.append(CalendarEvent(
                        id=f"gcal_{item['id'][:16]}",
                        source="google_calendar",
                        title=item.get("summary") or "(sans titre)",
                        start=ev_start,
                        end=ev_end,
                        all_day=all_day,
                        location=item.get("location", ""),
                        description=item.get("description", ""),
                        url=item.get("htmlLink", ""),
                        attendees=attendees,
                        color=COLOR,
                        organizer=org_name,
                    ))
                except Exception as ex:
                    logger.debug("[GoogleCalendar] Skipping event: %s", ex)

            logger.info("[GoogleCalendar] %d events fetched", len(events))
            return events if events else _mock_events(start, end)

    except Exception as e:
        logger.warning("[GoogleCalendar] Fetch error: %s — fallback to mock", e)
        return _mock_events(start, end)
