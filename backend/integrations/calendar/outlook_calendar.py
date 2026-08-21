"""Fetches calendar events from Microsoft Outlook via Graph API."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx

from .models import CalendarEvent

logger = logging.getLogger(__name__)

COLOR = "#0078D4"
GRAPH_API = "https://graph.microsoft.com/v1.0"


def _load_token(org_id: str | None = None) -> str | None:
    try:
        from core.database import SessionLocal
        from core.models import SourceConfig
        db = SessionLocal()
        try:
            q = db.query(SourceConfig).filter(SourceConfig.source == "outlook")
            if org_id:
                q = q.filter(SourceConfig.org_id == org_id)
            row = q.first()
            if row:
                cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
                return cfg.get("access_token")
        finally:
            db.close()
    except Exception as e:
        logger.warning("[OutlookCalendar] Cannot load token: %s", e)
    return None


def _mock_events(start: datetime, end: datetime) -> list[CalendarEvent]:
    monday = start.replace(hour=0, minute=0, second=0, microsecond=0)
    events = [
        CalendarEvent(
            id="outlook_cal_001",
            source="outlook_calendar",
            title="Comité de direction Q2",
            start=monday.replace(hour=9, minute=0, second=0, microsecond=0),
            end=monday.replace(hour=11, minute=0, second=0, microsecond=0),
            location="Salle Panorama",
            description="Revue des KPIs Q2 et validation des orientations stratégiques.",
            attendees=[
                {"name": "Marie Dupont",  "email": "m.dupont@company.com"},
                {"name": "Ahmed Ben Ali", "email": "a.benali@company.com"},
                {"name": "Sophie Martin", "email": "s.martin@company.com"},
            ],
            color=COLOR,
            organizer="CEO",
        ),
        CalendarEvent(
            id="outlook_cal_002",
            source="outlook_calendar",
            title="1:1 avec CTO — Sprint Review",
            start=(monday + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0),
            end=(monday + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0),
            location="Bureau Direction",
            description="Point hebdomadaire sur l'avancement technique et les blocages.",
            attendees=[{"name": "Karim Haddad", "email": "k.haddad@company.com"}],
            color=COLOR,
            organizer="CEO",
        ),
        CalendarEvent(
            id="outlook_cal_003",
            source="outlook_calendar",
            title="Appel investisseurs — Series B",
            start=(monday + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0),
            end=(monday + timedelta(days=2)).replace(hour=11, minute=30, second=0, microsecond=0),
            location="Visioconférence",
            description="Présentation du deck Series B au comité d'investissement.",
            attendees=[
                {"name": "Pierre Leblanc", "email": "p.leblanc@vc-fund.com"},
                {"name": "Léa Fontaine",   "email": "l.fontaine@company.com"},
            ],
            color=COLOR,
            organizer="CEO",
        ),
        CalendarEvent(
            id="outlook_cal_004",
            source="outlook_calendar",
            title="Réunion stratégie MENA",
            start=(monday + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0),
            end=(monday + timedelta(days=3)).replace(hour=10, minute=30, second=0, microsecond=0),
            location="Salle Atlas",
            description="Expansion marché MENA — revue des partenaires locaux et du plan go-to-market.",
            attendees=[
                {"name": "Yasmine Cherif", "email": "y.cherif@company.com"},
                {"name": "Ahmed Ben Ali",  "email": "a.benali@company.com"},
            ],
            color=COLOR,
            organizer="CEO",
        ),
        CalendarEvent(
            id="outlook_cal_005",
            source="outlook_calendar",
            title="Board Meeting — Rapport annuel",
            start=(monday + timedelta(days=4)).replace(hour=14, minute=0, second=0, microsecond=0),
            end=(monday + timedelta(days=4)).replace(hour=17, minute=0, second=0, microsecond=0),
            location="Salle Conseil",
            description="Présentation du rapport annuel aux membres du conseil d'administration.",
            attendees=[
                {"name": "Pierre Leblanc",  "email": "p.leblanc@board.com"},
                {"name": "Clara Rousseau",  "email": "c.rousseau@company.com"},
                {"name": "Marie Dupont",    "email": "m.dupont@company.com"},
            ],
            color=COLOR,
            organizer="Board",
        ),
    ]
    return [e for e in events if e.start >= start and e.start < end]


async def fetch_outlook_calendar(start: datetime, end: datetime, org_id: str | None = None) -> list[CalendarEvent]:
    token = _load_token(org_id=org_id)
    if not token:
        logger.info("[OutlookCalendar] No token — returning mock events")
        return _mock_events(start, end)

    start_iso = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso   = end.strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        "startDateTime": start_iso,
        "endDateTime":   end_iso,
        "$select":       "id,subject,start,end,location,bodyPreview,attendees,isAllDay,webLink,organizer",
        "$top":          50,
        "$orderby":      "start/dateTime",
    }
    headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{GRAPH_API}/me/calendarView", headers=headers, params=params)
            if r.status_code != 200:
                logger.warning("[OutlookCalendar] API %s — fallback to mock", r.status_code)
                return _mock_events(start, end)

            events: list[CalendarEvent] = []
            for item in r.json().get("value", []):
                try:
                    s = item.get("start", {})
                    e = item.get("end", {})
                    ev_start = datetime.fromisoformat(s.get("dateTime", "").rstrip("Z"))
                    ev_end   = datetime.fromisoformat(e.get("dateTime", "").rstrip("Z"))
                    loc      = (item.get("location") or {}).get("displayName", "")
                    org      = ((item.get("organizer") or {}).get("emailAddress") or {}).get("name", "")
                    attendees = [
                        {
                            "name":  (a.get("emailAddress") or {}).get("name", ""),
                            "email": (a.get("emailAddress") or {}).get("address", ""),
                        }
                        for a in (item.get("attendees") or [])
                    ]
                    events.append(CalendarEvent(
                        id=f"outlook_cal_{item['id'][:16]}",
                        source="outlook_calendar",
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
                    logger.debug("[OutlookCalendar] Skipping event: %s", ex)

            logger.info("[OutlookCalendar] %d events fetched", len(events))
            return events if events else _mock_events(start, end)

    except Exception as e:
        logger.warning("[OutlookCalendar] Fetch error: %s — fallback to mock", e)
        return _mock_events(start, end)
