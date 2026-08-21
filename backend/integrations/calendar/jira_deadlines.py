"""Extracts Jira ticket deadlines from the database as calendar events."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from .models import CalendarEvent

logger = logging.getLogger(__name__)

COLOR = "#0052CC"


def fetch_jira_deadlines(start: datetime, end: datetime, org_id: str | None = None) -> list[CalendarEvent]:
    try:
        from core.database import SessionLocal
        from core.models import MessageRaw

        db = SessionLocal()
        try:
            q = db.query(MessageRaw).filter(
                MessageRaw.source == "jira",
                MessageRaw.timestamp >= start,
                MessageRaw.timestamp <= end,
            )
            if org_id:
                q = q.filter(MessageRaw.org_id == org_id)
            rows = (
                q
                .order_by(MessageRaw.timestamp)
                .limit(100)
                .all()
            )

            events: list[CalendarEvent] = []
            for row in rows:
                try:
                    meta = row.metadata_json or {}
                    if isinstance(meta, str):
                        meta = json.loads(meta)

                    # Use due_date from metadata if present, else fall back to timestamp
                    raw_date = meta.get("due_date") or meta.get("dueDate")
                    if raw_date:
                        try:
                            ev_date = datetime.fromisoformat(str(raw_date).rstrip("Z"))
                        except Exception:
                            ev_date = row.timestamp
                    else:
                        ev_date = row.timestamp

                    if not (start <= ev_date <= end):
                        continue

                    day = ev_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    events.append(CalendarEvent(
                        id=f"jira_deadline_{row.id}",
                        source="jira",
                        title=f"[Jira] {row.title or '(ticket)'}",
                        start=day,
                        end=day,
                        all_day=True,
                        description=row.content or "",
                        url=row.url or "",
                        color=COLOR,
                        organizer=row.author or "",
                    ))
                except Exception as ex:
                    logger.debug("[JiraDeadlines] Skipping row %s: %s", row.id, ex)

            logger.info("[JiraDeadlines] %d deadlines found", len(events))
            return events
        finally:
            db.close()
    except Exception as e:
        logger.warning("[JiraDeadlines] Error: %s", e)
        return []
