from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from core.store import ItemStore
from application.deps import get_store
from data.analytics import compute_overview, ANALYTICS_REGISTRY
from integrations.connectors.schemas import SourceType
from core.models import User
from core.security import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    store: Annotated[ItemStore, Depends(get_store)],
    current_user: User = Depends(get_current_user),
    since_days: int = Query(30, ge=1, le=365),
):
    result = compute_overview(store, since_days)
    # connected_sources = sources with credentials OR sources with any synced data (all-time)
    try:
        from core.database import SessionLocal
        from core.models import SourceConfig as _SC, MessageRaw as _MR
        import logging as _log
        db = SessionLocal()
        try:
            # Sources with saved credentials for this org
            cfg_rows = db.query(_SC.source).filter(
                _SC.org_id == current_user.org_id
            ).all()
            configured = {r.source for r in cfg_rows}

            # Sources that have any items ever synced for this org (no time filter)
            msg_rows = db.query(_MR.source).filter(
                _MR.org_id == current_user.org_id
            ).distinct().all()
            synced = {r.source for r in msg_rows}

            result["connected_sources"] = len(configured | synced)
        finally:
            db.close()
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("[analytics] connected_sources fallback: %s", e)
    return result


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
    current_user: User = Depends(get_current_user),
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
                MessageRaw.org_id == current_user.org_id,
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


@router.get("/attribution")
async def attribution(
    store: Annotated[ItemStore, Depends(get_store)],
    current_user: User = Depends(get_current_user),
    since_days: int = Query(7, ge=1, le=90),
):
    from data.analytics.engine import compute_attribution
    return compute_attribution(store, since_days)


@router.get("/messages")
async def filtered_messages(
    store: Annotated[ItemStore, Depends(get_store)],
    current_user: User = Depends(get_current_user),
    since_days: int = Query(30, ge=1, le=365),
    business_label: str | None = Query(None),
    emotion_label:  str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Messages filtrés par business_label et/ou emotion_label."""
    from data.analytics.engine import _since, _get_business_label
    since = _since(since_days)
    items = store.all(since=since, limit=10_000)

    result = []
    for item in items:
        if "SENT" in (item.tags or []):
            continue
        if business_label and _get_business_label(item) != business_label:
            continue
        emotion = (item.metadata or {}).get("emotion_label", "")
        if emotion_label and emotion != emotion_label:
            continue
        result.append({
            "id":             item.id,
            "title":          (item.title or "")[:120],
            "author":         item.author or "",
            "source":         item.source,
            "timestamp":      item.timestamp.isoformat(),
            "business_label": _get_business_label(item),
            "emotion_label":  emotion,
            "sentiment":      (item.metadata or {}).get("sentiment_label", ""),
            "content":        (item.content or "")[:400],
            "url":            item.url or "",
            "tags":           item.tags or [],
        })

    result.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"items": result[:limit], "total": len(result)}


@router.get("/heatmap")
async def heatmap(
    store: Annotated[ItemStore, Depends(get_store)],
    current_user: User = Depends(get_current_user),
    since_days: int = Query(30, ge=1, le=365),
):
    from data.analytics.engine import compute_heatmap
    return compute_heatmap(store, since_days)


@router.get("/priority-messages")
async def priority_messages(
    store: Annotated[ItemStore, Depends(get_store)],
    current_user: User = Depends(get_current_user),
    since_days: int = Query(7, ge=1, le=365),
    limit: int = Query(3, ge=1, le=10),
):
    from data.analytics.engine import compute_priority_messages
    return compute_priority_messages(store, since_days, limit)


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
