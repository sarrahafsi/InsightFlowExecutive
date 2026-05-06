"""Fetches scheduled Teams meetings via Microsoft Graph calendarView."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx

from .models import CalendarEvent

logger = logging.getLogger(__name__)

COLOR = "#6264A7"
GRAPH_API = "https://graph.microsoft.com/v1.0"


def _load_token() -> str | None:
    try:
        from core.database import SessionLocal
        from core.models import SourceConfig
        db = SessionLocal()
        try:
            row = db.query(SourceConfig).filter(SourceConfig.source == "teams").first()
            if row:
                cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
                return cfg.get("access_token")
        finally:
            db.close()
    except Exception as e:
        logger.warning("[TeamsCalendar] Cannot load token: %s", e)
    return None


def _mock_events(start: datetime, end: datetime) -> list[CalendarEvent]:
    monday = start - timedelta(days=start.weekday())
    events = []

    # Daily Standup every weekday 9h-9h30
    for day_offset in range(7):
        day = monday + timedelta(days=day_offset)
        if day.weekday() < 5:  # Mon–Fri only
            ev_start = day.replace(hour=9, minute=0, second=0, microsecond=0)
            ev_end   = day.replace(hour=9, minute=30, second=0, microsecond=0)
            if ev_start >= start and ev_start < end:
                events.append(CalendarEvent(
                    id=f"teams_standup_{day.strftime('%Y%m%d')}",
                    source="teams",
                    title="Daily Standup",
                    start=ev_start,
                    end=ev_end,
                    location="Microsoft Teams",
                    description="Point quotidien d'équipe — blocages, avancement, priorités.",
                    attendees=[
                        {"name": "Sophie Martin",  "email": "s.martin@company.com"},
                        {"name": "Karim Haddad",   "email": "k.haddad@company.com"},
                        {"name": "Ahmed Ben Ali",  "email": "a.benali@company.com"},
                    ],
                    color=COLOR,
                    organizer="CEO",
                ))

    # Sprint Planning on Monday
    sprint_start = monday.replace(hour=13, minute=0, second=0, microsecond=0)
    sprint_end   = monday.replace(hour=15, minute=0, second=0, microsecond=0)
    if sprint_start >= start and sprint_start < end:
        events.append(CalendarEvent(
            id="teams_sprint_planning",
            source="teams",
            title="Sprint Planning",
            start=sprint_start,
            end=sprint_end,
            location="Microsoft Teams",
            description="Planification du sprint — attribution des tickets, estimation de la vélocité.",
            attendees=[
                {"name": "Karim Haddad",  "email": "k.haddad@company.com"},
                {"name": "Sophie Martin", "email": "s.martin@company.com"},
            ],
            color=COLOR,
            organizer="CTO",
        ))

    return events


async def fetch_teams_meetings(start: datetime, end: datetime) -> list[CalendarEvent]:
    token = _load_token()
    if not token:
        logger.info("[TeamsCalendar] No token — returning mock events")
        return _mock_events(start, end)

    start_iso = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso   = end.strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        "startDateTime": start_iso,
        "endDateTime":   end_iso,
        "$select":       "id,subject,start,end,location,bodyPreview,attendees,isAllDay,webLink,organizer,isOnlineMeeting",
        "$top":          50,
    }
    headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{GRAPH_API}/me/calendarView", headers=headers, params=params)
            if r.status_code != 200:
                logger.warning("[TeamsCalendar] API %s — fallback to mock", r.status_code)
                return _mock_events(start, end)

            events: list[CalendarEvent] = []
            for item in r.json().get("value", []):
                # Only include online meetings (Teams meetings)
                if not item.get("isOnlineMeeting", False):
                    continue
                try:
                    s = item.get("start", {})
                    e = item.get("end", {})
                    ev_start = datetime.fromisoformat(s.get("dateTime", "").rstrip("Z"))
                    ev_end   = datetime.fromisoformat(e.get("dateTime", "").rstrip("Z"))
                    loc      = (item.get("location") or {}).get("displayName", "Microsoft Teams")
                    org      = ((item.get("organizer") or {}).get("emailAddress") or {}).get("name", "")
                    attendees = [
                        {
                            "name":  (a.get("emailAddress") or {}).get("name", ""),
                            "email": (a.get("emailAddress") or {}).get("address", ""),
                        }
                        for a in (item.get("attendees") or [])
                    ]
                    events.append(CalendarEvent(
                        id=f"teams_{item['id'][:16]}",
                        source="teams",
                        title=item.get("subject") or "(sans titre)",
                        start=ev_start,
                        end=ev_end,
                        all_day=item.get("isAllDay", False),
                        location=loc,
                        description=item.get("bodyPreview", ""),
                        url=item.get("webLink", ""),
                        attendees=attendees,
                        color=COLOR,
                        organizer=org,
                    ))
                except Exception as ex:
                    logger.debug("[TeamsCalendar] Skipping event: %s", ex)

            logger.info("[TeamsCalendar] %d meetings fetched", len(events))
            return events if events else _mock_events(start, end)

    except Exception as e:
        logger.warning("[TeamsCalendar] Fetch error: %s — fallback to mock", e)
        return _mock_events(start, end)
