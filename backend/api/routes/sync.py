from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from connectors import ConnectorManager, SourceType, SyncResult
from store import ItemStore
from api.deps import get_manager, get_store

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncRequest(BaseModel):
    sources: list[SourceType] | None = None
    since_days: int = 7  # how far back to fetch


class SyncResponse(BaseModel):
    triggered_at: datetime
    total_items_stored: int
    results: list[dict]


@router.post("", response_model=SyncResponse)
async def trigger_sync(
    body: SyncRequest,
    manager: Annotated[ConnectorManager, Depends(get_manager)],
    store: Annotated[ItemStore, Depends(get_store)],
):
    """
    Trigger a data sync from all (or specific) connectors.

    - **sources**: optional list to restrict which connectors run
    - **since_days**: how many days back to pull data (default 7)
    """
    since = datetime.utcnow() - timedelta(days=body.since_days)
    results: list[SyncResult] = await manager.sync_all(
        since=since, sources=body.sources
    )

    new_items = store.upsert(ConnectorManager.collect_items(results))

    now = datetime.utcnow()
    for r in results:
        if r.success:
            store.set_last_sync(r.source, now)

    summary = manager.summary(results)

    return SyncResponse(
        triggered_at=now,
        total_items_stored=store.count(),
        results=[
            {
                "source": source,
                "items_fetched": info["items"],
                "success": info["success"],
                "error": info.get("error"),
            }
            for source, info in summary["by_source"].items()
        ],
    )


@router.get("/status", tags=["sync"])
async def sync_status(
    store: Annotated[ItemStore, Depends(get_store)],
):
    """Returns last sync timestamps and total item count per source."""
    return {
        "total_items": store.count(),
        "last_sync": {
            source.value: store.last_sync(source)
            for source in SourceType
        },
    }
