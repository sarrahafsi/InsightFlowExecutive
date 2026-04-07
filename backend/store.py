"""
In-memory store for synced DataItems.
Acts as a simple repository layer — easy to swap for PostgreSQL later.
"""
from datetime import datetime
from connectors.schemas import DataItem, SourceType, ItemType


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
