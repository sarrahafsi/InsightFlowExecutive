from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from store import ItemStore
from api.deps import get_store
from analytics import compute_overview, ANALYTICS_REGISTRY

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    store: Annotated[ItemStore, Depends(get_store)],
    since_days: int = Query(30, ge=1, le=365),
):
    return compute_overview(store, since_days)


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
