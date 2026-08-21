"""
In-memory store for synced DataItems.
Acts as a simple repository layer — easy to swap for PostgreSQL later.
"""
from datetime import datetime
from integrations.connectors.schemas import DataItem, SourceType, ItemType


def _row_to_item(row) -> DataItem:
    """Convert a MessageRaw ORM row to DataItem."""
    import json as _json
    raw_meta = row.metadata_json or {}
    if isinstance(raw_meta, str):
        try:
            raw_meta = _json.loads(raw_meta)
        except Exception:
            raw_meta = {}
    meta: dict = {
        "from_email":          row.author_email or "",
        "thread_id":           row.thread_id,
        "sentiment_label":     row.sentiment_label,
        "sentiment_score":     row.sentiment_score,
        "emotion_label":       row.emotion_label,
        "emotion_score":       row.emotion_score,
        "topic":               row.topic,
        "business_label":      row.business_label,
        "business_confidence": row.business_confidence,
        "business_reason":     row.business_reason,
        "burnout_score":       row.burnout_score,
        "hour_sent":           row.hour_sent,
        "is_weekend":          row.is_weekend,
        "is_after_hours":      row.is_after_hours,
    }
    if isinstance(raw_meta, dict):
        meta.update(raw_meta)
    return DataItem(
        id=row.id,
        source=row.source,
        type=row.item_type or "message",
        title=row.title or "",
        content=row.content or "",
        author=row.author or "",
        timestamp=row.timestamp,
        url=row.url,
        tags=list(row.tags or []),
        metadata={k: v for k, v in meta.items() if v is not None},
    )


class OrgScopedItemStore:
    """
    Per-org view of messages_raw, matching ItemStore's query interface.
    Analytics always reads from PostgreSQL filtered by org_id — no cross-tenant leakage.
    """

    def __init__(self, org_id: str | None):
        self._org_id = org_id

    def _base_query(self, db, source=None, type=None, since=None):
        from core.models import MessageRaw
        from sqlalchemy import desc
        q = db.query(MessageRaw).filter(MessageRaw.org_id == self._org_id)
        if source is not None:
            q = q.filter(MessageRaw.source == (source.value if hasattr(source, "value") else source))
        if type is not None:
            q = q.filter(MessageRaw.item_type == (type.value if hasattr(type, "value") else type))
        if since is not None:
            q = q.filter(MessageRaw.timestamp >= since)
        return q

    def all(self, source=None, type=None, since=None, limit=100, offset=0) -> list[DataItem]:
        from core.database import SessionLocal
        from sqlalchemy import desc
        from core.models import MessageRaw
        db = SessionLocal()
        try:
            rows = (
                self._base_query(db, source=source, type=type, since=since)
                .order_by(desc(MessageRaw.timestamp))
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [_row_to_item(r) for r in rows]
        finally:
            db.close()

    def get(self, item_id: str) -> DataItem | None:
        from core.database import SessionLocal
        from core.models import MessageRaw
        db = SessionLocal()
        try:
            row = db.query(MessageRaw).filter(
                MessageRaw.id == item_id,
                MessageRaw.org_id == self._org_id,
            ).first()
            return _row_to_item(row) if row else None
        finally:
            db.close()

    def count(self) -> int:
        from core.database import SessionLocal
        db = SessionLocal()
        try:
            return self._base_query(db).count()
        finally:
            db.close()

    def count_source(self, source) -> int:
        from core.database import SessionLocal
        db = SessionLocal()
        try:
            return self._base_query(db, source=source).count()
        finally:
            db.close()

    def last_sync(self, source) -> None:
        return None

    def set_last_sync(self, source, at) -> None:
        pass  # Not tracked per-org in this store

    def upsert(self, items) -> int:
        return 0  # Writes go through ETL loader directly


class ItemStore:
    """Thread-safe (for asyncio) in-memory store with upsert by item id."""

    def __init__(self):
        self._items: dict[str, DataItem] = {}
        self._last_sync: dict[SourceType, datetime] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(self, items: list[DataItem]) -> int:
        """Insert or update items. Returns count of new items added."""
        before = len(self._items)
        for item in items:
            self._items[item.id] = item
        return len(self._items) - before

    def set_last_sync(self, source: SourceType, at: datetime) -> None:
        self._last_sync[source] = at

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all(
        self,
        source: SourceType | None = None,
        type: ItemType | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DataItem]:
        items = list(self._items.values())

        if source:
            items = [i for i in items if i.source == source]
        if type:
            items = [i for i in items if i.type == type]
        if since:
            items = [i for i in items if i.timestamp >= since]

        items.sort(key=lambda x: x.timestamp, reverse=True)
        return items[offset: offset + limit]

    def get(self, item_id: str) -> DataItem | None:
        return self._items.get(item_id)

    def count(self) -> int:
        return len(self._items)

    def last_sync(self, source: SourceType) -> datetime | None:
        return self._last_sync.get(source)


# Singleton — shared across the whole app
item_store = ItemStore()
