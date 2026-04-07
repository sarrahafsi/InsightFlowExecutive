from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from connectors.schemas import DataItem, ItemType, SourceType
from store import ItemStore
from api.deps import get_store

router = APIRouter(prefix="/items", tags=["items"])


class ItemsResponse(DataItem):
    pass


@router.get("", response_model=list[DataItem])
async def list_items(
    store: Annotated[ItemStore, Depends(get_store)],
    source: SourceType | None = Query(None, description="Filter by source (slack, gmail, jira)"),
    type: ItemType | None = Query(None, description="Filter by type (message, email, ticket)"),
    since: datetime | None = Query(None, description="ISO datetime — only items after this date"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List all synced data items with optional filters.

    Examples:
    - `GET /api/items?source=slack`
    - `GET /api/items?type=ticket&since=2026-04-01T00:00:00`
    - `GET /api/items?limit=10&offset=0`
    """
    return store.all(source=source, type=type, since=since, limit=limit, offset=offset)


@router.get("/stats", tags=["items"])
async def items_stats(store: Annotated[ItemStore, Depends(get_store)]):
    """Returns item counts broken down by source and type."""
    all_items = store.all(limit=10_000)

    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for item in all_items:
        by_source[item.source] = by_source.get(item.source, 0) + 1
        by_type[item.type] = by_type.get(item.type, 0) + 1

    return {
        "total": len(all_items),
        "by_source": by_source,
        "by_type": by_type,
    }


@router.get("/{item_id}", response_model=DataItem)
async def get_item(
    item_id: str,
    store: Annotated[ItemStore, Depends(get_store)],
):
    """Get a single item by its ID (e.g. `slack_1234`, `jira_PROJ-142`)."""
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return item
