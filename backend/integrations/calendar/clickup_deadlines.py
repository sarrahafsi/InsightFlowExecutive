"""Extracts ClickUp task due dates from the database as calendar events."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from .models import CalendarEvent

logger = logging.getLogger(__name__)

COLOR = "#7B68EE"


def fetch_clickup_deadlines(start: datetime, end: datetime) -> list[CalendarEvent]:
    try:
        from core.database import SessionLocal
        from core.models import MessageRaw

        db = SessionLocal()
        try:
            rows = (
                db.query(MessageRaw)
                .filter(
                    MessageRaw.source == "clickup",
                    MessageRaw.timestamp >= start,
                    MessageRaw.timestamp <= end,
                )
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
                        id=f"clickup_deadline_{row.id}",
                        source="clickup",
                        title=f"[ClickUp] {row.title or '(tâche)'}",
                        start=day,
                        end=day,
                        all_day=True,
                        description=row.content or "",
                        url=row.url or "",
                        color=COLOR,
                        organizer=row.author or "",
                    ))
                except Exception as ex:
                    logger.debug("[ClickUpDeadlines] Skipping row %s: %s", row.id, ex)

            logger.info("[ClickUpDeadlines] %d deadlines found", len(events))
            return events
        finally:
            db.close()
    except Exception as e:
        logger.warning("[ClickUpDeadlines] Error: %s", e)
        return []
