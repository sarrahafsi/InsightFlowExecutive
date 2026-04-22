from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from core.store import ItemStore
from application.deps import get_store
from data.analytics import compute_overview, ANALYTICS_REGISTRY
from integrations.connectors.schemas import SourceType

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    store: Annotated[ItemStore, Depends(get_store)],
    since_days: int = Query(30, ge=1, le=365),
):
    return compute_overview(store, since_days)


@router.get("/jira/debug")
async def jira_debug(
    store: Annotated[ItemStore, Depends(get_store)],
):
    """Debug: montre les données brutes des items Jira dans le store."""
    items = store.all(source=SourceType.JIRA, limit=200)
    return {
        "total_in_store": len(items),
        "sample": [
            {
                "id": i.id,
                "title": i.title,
                "status":     (i.metadata or {}).get("status", "MISSING"),
                "priority":   (i.metadata or {}).get("priority", "MISSING"),
                "issue_type": (i.metadata or {}).get("issue_type", "MISSING"),
                "metadata_keys": list((i.metadata or {}).keys()),
            }
            for i in items[:20]
        ],
    }


@router.get("/{source}")
async def source_analytics(
    source: str,
    store: Annotated[ItemStore, Depends(get_store)],
    since_days: int = Query(30, ge=1, le=365),
):
    fn = ANALYTICS_REGISTRY.get(source)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"No analytics for source '{source}'")
    return fn(store, since_days)
