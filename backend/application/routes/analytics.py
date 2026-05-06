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


@router.get("/team/overload")
def team_overload(
    since_days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=50),
):
    """Top N auteurs les plus surchargés sur la période."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, Integer
    from sqlalchemy import cast
    from core.models import MessageRaw
    from core.database import SessionLocal

    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=since_days)
        rows = (
            db.query(
                MessageRaw.author,
                func.count(MessageRaw.id).label("total_msgs"),
                func.avg(MessageRaw.burnout_score).label("avg_burnout"),
                func.sum(cast(MessageRaw.is_after_hours, Integer)).label("after_hours_msgs"),
                func.sum(cast(MessageRaw.is_weekend,     Integer)).label("weekend_msgs"),
            )
            .filter(
                MessageRaw.timestamp >= since,
                MessageRaw.author.isnot(None),
                MessageRaw.burnout_score.isnot(None),
            )
            .group_by(MessageRaw.author)
            .order_by(func.avg(MessageRaw.burnout_score).desc())
            .limit(limit)
            .all()
        )

        people = []
        for r in rows:
            avg_b = float(r.avg_burnout or 0)
            level = "high" if avg_b >= 0.5 else "medium" if avg_b >= 0.25 else "low"
            people.append({
                "author":           r.author,
                "total_msgs":       r.total_msgs,
                "avg_burnout":      round(avg_b, 3),
                "burnout_pct":      round(avg_b * 100),
                "after_hours_msgs": int(r.after_hours_msgs or 0),
                "weekend_msgs":     int(r.weekend_msgs or 0),
                "level":            level,
            })

        return {
            "people":      people,
            "since_days":  since_days,
            "computed_at": datetime.utcnow().isoformat(),
        }
    finally:
        db.close()


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
