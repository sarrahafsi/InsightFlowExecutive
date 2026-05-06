"""Unified Calendar API — aggregates Outlook, Google, Teams, Jira, ClickUp events."""
import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from integrations.calendar.outlook_calendar import fetch_outlook_calendar
from integrations.calendar.google_calendar import fetch_google_calendar
from integrations.calendar.teams_meetings import fetch_teams_meetings
from integrations.calendar.jira_deadlines import fetch_jira_deadlines
from integrations.calendar.clickup_deadlines import fetch_clickup_deadlines

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
logger = logging.getLogger(__name__)


def _week_bounds(ref: datetime) -> tuple[datetime, datetime]:
    """Return Monday 00:00 and Sunday+1 00:00 for the week containing ref."""
    monday = ref - timedelta(days=ref.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_end = monday + timedelta(days=7)
    return monday, sunday_end


@router.get("/events")
async def get_calendar_events(
    start: str = Query(default=None, description="YYYY-MM-DD — defaults to Monday of current week"),
    end:   str = Query(default=None, description="YYYY-MM-DD — defaults to Sunday of current week"),
):
    now = datetime.utcnow()

    if start:
        try:
            week_start = datetime.strptime(start, "%Y-%m-%d")
        except ValueError:
            week_start, _ = _week_bounds(now)
    else:
        week_start, _ = _week_bounds(now)

    if end:
        try:
            week_end = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            _, week_end = _week_bounds(now)
    else:
        _, week_end = _week_bounds(now)

    # Run async fetchers in parallel, sync fetchers directly
    outlook_task  = fetch_outlook_calendar(week_start, week_end)
    google_task   = fetch_google_calendar(week_start, week_end)
    teams_task    = fetch_teams_meetings(week_start, week_end)

    outlook_events, google_events, teams_events = await asyncio.gather(
        outlook_task, google_task, teams_task,
        return_exceptions=True,
    )

    jira_events    = fetch_jira_deadlines(week_start, week_end)
    clickup_events = fetch_clickup_deadlines(week_start, week_end)

    all_events = []
    for batch in [outlook_events, google_events, teams_events, jira_events, clickup_events]:
        if isinstance(batch, Exception):
            logger.warning("[Calendar] Fetcher error: %s", batch)
            continue
        all_events.extend(batch)

    # Sort by start time — strip timezone info to compare uniformly
    def _naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    all_events.sort(key=lambda e: _naive(e.start))

    sources_present = list({e.source for e in all_events})

    return {
        "events":     [e.to_dict() for e in all_events],
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end":   (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "sources":    sources_present,
        "total":      len(all_events),
    }
