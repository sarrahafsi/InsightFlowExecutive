"""
Search + Priority Inbox + Authors + Compare
All endpoints are org-scoped — each CEO sees only their own data.
"""
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from fastapi import APIRouter, Depends, Query
from core.models import User
from core.security import get_current_user
from core.store import OrgScopedItemStore
from pydantic import BaseModel

router = APIRouter(prefix="/search", tags=["search"])


class RagSearchRequest(BaseModel):
    query:         str
    top_k:         int = 5
    source_filter: str | None = None


@router.post("/rag")
async def rag_search(body: RagSearchRequest):
    """Endpoint HTTP pour le MCP knowledge_server — évite de charger ChromaDB dans le subprocess."""
    from intelligence.rag.retriever import retrieve
    docs = retrieve(body.query, top_k=body.top_k, source_filter=body.source_filter)
    relevant = [d for d in docs if d.score <= 0.75]
    return {
        "results": [
            {
                "id":        d.id,
                "title":     d.title,
                "author":    d.author,
                "source":    d.source,
                "timestamp": d.timestamp,
                "excerpt":   d.text[:300],
                "sentiment": d.sentiment_label,
                "business":  d.business_label,
                "score":     round(d.score, 3),
            }
            for d in relevant
        ],
        "count": len(relevant),
    }


def _since_from_days(since_days: int) -> datetime:
    now = datetime.utcnow()
    if since_days == 1:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=since_days)


# ── Recherche textuelle ────────────────────────────────────────

@router.get("")
async def search(
    current_user: User = Depends(get_current_user),
    q: str = Query("", description="Mot-clé à rechercher"),
    topic: str = Query("", description="Filtrer par topic"),
    business_label: str = Query("", description="Filtrer par label business"),
    source: str = Query("", description="Filtrer par source"),
    since_days: int = Query(90, ge=1, le=365),
    limit: int = Query(30, ge=1, le=100),
):
    """Recherche full-text + filtres NLP sur les messages de l'org."""
    store = OrgScopedItemStore(current_user.org_id)
    since = _since_from_days(since_days)
    items = store.all(since=since, limit=5000)

    q_lower = q.lower().strip()
    results = []
    for item in items:
        m = item.metadata or {}
        if source and item.source != source:
            continue
        if topic and m.get("topic") != topic:
            continue
        if business_label and m.get("business_label") != business_label:
            continue
        if q_lower:
            haystack = f"{item.title} {item.content} {item.author}".lower()
            if q_lower not in haystack:
                continue
        results.append({
            "id":              item.id,
            "source":          item.source,
            "title":           (item.title or "")[:120],
            "author":          item.author or "",
            "timestamp":       item.timestamp.isoformat(),
            "sentiment_label": m.get("sentiment_label"),
            "business_label":  m.get("business_label"),
            "emotion_label":   m.get("emotion_label"),
            "topic":           m.get("topic"),
            "business_reason": m.get("business_reason", ""),
            "is_after_hours":  m.get("is_after_hours", False),
            "is_weekend":      m.get("is_weekend", False),
            "burnout_score":   m.get("burnout_score"),
            "snippet":         (item.content or "")[:200],
        })

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"query": q, "total": len(results), "items": results[:limit]}


# ── Priority Inbox ─────────────────────────────────────────────

URGENCY_SCORE = {
    "Blocked": 10, "Urgent": 9, "Risk": 7,
    "Conflict": 6, "Overload": 5, "Concern": 3,
    "Progress": 1, "Neutral Update": 0,
}
SENTIMENT_SCORE = {"NEGATIVE": 3, "NEUTRAL": 1, "POSITIVE": 0}
EMOTION_SCORE   = {"frustration": 3, "urgency": 3, "concern": 2, "neutral": 0, "satisfaction": 0}


@router.get("/priority")
async def priority_inbox(
    current_user: User = Depends(get_current_user),
    since_days: int = 7,
    limit: int = 10,
    source: str = "",
):
    """Top messages prioritaires à lire — classés par score IA, scoped à l'org."""
    store = OrgScopedItemStore(current_user.org_id)
    since = _since_from_days(since_days)
    items = store.all(since=since, limit=2000)
    if source:
        items = [i for i in items if i.source == source]

    scored = []
    for item in items:
        m = item.metadata or {}
        score = 0
        score += URGENCY_SCORE.get(m.get("business_label", ""), 0) * 3
        score += SENTIMENT_SCORE.get(m.get("sentiment_label", ""), 0) * 2
        score += EMOTION_SCORE.get(m.get("emotion_label", ""), 0) * 2
        if m.get("is_after_hours"): score += 2
        if m.get("is_weekend"):     score += 3
        score += int((m.get("burnout_score") or 0) * 4)
        age_h = (datetime.utcnow() - item.timestamp).total_seconds() / 3600
        if age_h < 24:   score += 3
        elif age_h < 72: score += 1
        scored.append({
            "id":             item.id,
            "source":         item.source,
            "title":          (item.title or "")[:100],
            "author":         item.author or "",
            "timestamp":      item.timestamp.isoformat(),
            "priority_score": score,
            "business_label": m.get("business_label", "Neutral Update"),
            "sentiment_label":m.get("sentiment_label"),
            "emotion_label":  m.get("emotion_label"),
            "business_reason":m.get("business_reason", ""),
            "is_after_hours": m.get("is_after_hours", False),
            "is_weekend":     m.get("is_weekend", False),
            "snippet":        (item.content or "")[:180],
        })

    scored.sort(key=lambda x: x["priority_score"], reverse=True)
    return {"since_days": since_days, "items": scored[:limit]}


# ── Author Profiles ────────────────────────────────────────────

@router.get("/authors")
async def list_authors(
    current_user: User = Depends(get_current_user),
    since_days: int = 30,
):
    """Liste tous les auteurs avec leurs stats NLP agrégées — scoped à l'org."""
    store = OrgScopedItemStore(current_user.org_id)
    since = datetime.utcnow() - timedelta(days=since_days)
    items = store.all(since=since, limit=5000)

    authors: dict = defaultdict(lambda: {
        "count": 0, "sentiment": Counter(), "business": Counter(),
        "emotion": Counter(), "after_hours": 0, "weekend": 0,
        "burnout_scores": [], "topics": Counter(), "email": "",
        "timestamps": [],
    })

    for item in items:
        m = item.metadata or {}
        a = authors[item.author or "Inconnu"]
        a["count"] += 1
        a["email"] = m.get("from_email", a["email"])
        a["timestamps"].append(item.timestamp)
        if m.get("sentiment_label"): a["sentiment"][m["sentiment_label"]] += 1
        if m.get("business_label"):  a["business"][m["business_label"]]  += 1
        if m.get("emotion_label"):   a["emotion"][m["emotion_label"]]    += 1
        if m.get("topic"):           a["topics"][m["topic"]]             += 1
        if m.get("is_after_hours"):  a["after_hours"] += 1
        if m.get("is_weekend"):      a["weekend"] += 1
        if m.get("burnout_score") is not None:
            a["burnout_scores"].append(float(m["burnout_score"]))

    result = []
    for name, d in authors.items():
        total = max(d["count"], 1)
        bs = d["burnout_scores"]
        result.append({
            "name":               name,
            "email":              d["email"],
            "message_count":      d["count"],
            "sentiment":          dict(d["sentiment"]),
            "dominant_sentiment": d["sentiment"].most_common(1)[0][0] if d["sentiment"] else None,
            "dominant_business":  d["business"].most_common(1)[0][0] if d["business"] else None,
            "dominant_emotion":   d["emotion"].most_common(1)[0][0] if d["emotion"] else None,
            "top_topic":          d["topics"].most_common(1)[0][0] if d["topics"] else None,
            "after_hours_rate":   round(d["after_hours"] / total * 100),
            "weekend_rate":       round(d["weekend"] / total * 100),
            "avg_burnout":        round(sum(bs) / len(bs), 2) if bs else 0.0,
            "last_message":       max(d["timestamps"]).isoformat() if d["timestamps"] else None,
        })

    result.sort(key=lambda x: x["message_count"], reverse=True)
    return {"since_days": since_days, "authors": result}


@router.get("/authors/{author_name}")
async def author_detail(
    author_name: str,
    current_user: User = Depends(get_current_user),
    since_days: int = 90,
):
    """Profil détaillé d'un auteur — scoped à l'org."""
    store = OrgScopedItemStore(current_user.org_id)
    since = datetime.utcnow() - timedelta(days=since_days)
    items = [i for i in store.all(since=since, limit=5000) if i.author == author_name]

    if not items:
        return {"author": author_name, "found": False, "messages": []}

    by_hour: list[int] = [0] * 24
    by_day:  list[int] = [0] * 7
    business_trend: dict = defaultdict(int)
    messages = []

    for item in items:
        m = item.metadata or {}
        by_hour[item.timestamp.hour] += 1
        by_day[item.timestamp.weekday()] += 1
        if m.get("business_label"):
            business_trend[m["business_label"]] += 1
        messages.append({
            "id":              item.id,
            "title":           (item.title or "")[:100],
            "timestamp":       item.timestamp.isoformat(),
            "sentiment_label": m.get("sentiment_label"),
            "business_label":  m.get("business_label"),
            "emotion_label":   m.get("emotion_label"),
            "topic":           m.get("topic"),
            "is_after_hours":  m.get("is_after_hours", False),
            "is_weekend":      m.get("is_weekend", False),
        })

    messages.sort(key=lambda x: x["timestamp"], reverse=True)
    return {
        "author":         author_name,
        "found":          True,
        "total":          len(items),
        "by_hour":        [{"hour": h, "count": c} for h, c in enumerate(by_hour)],
        "by_day":         [{"day": d, "count": c} for d, c in enumerate(by_day)],
        "business_trend": dict(business_trend),
        "messages":       messages[:50],
    }


# ── Mode Comparaison ───────────────────────────────────────────

@router.get("/compare")
async def compare_periods(
    current_user: User = Depends(get_current_user),
    period_a: int = 7,
    period_b: int = 14,
):
    """Compare deux périodes glissantes côte à côte — scoped à l'org."""
    from data.analytics.engine import compute_overview
    store = OrgScopedItemStore(current_user.org_id)
    now = datetime.utcnow()

    stats_a = compute_overview(store, since_days=period_a)
    since_b = now - timedelta(days=period_b)
    until_b = now - timedelta(days=period_a)
    items_b = [i for i in store.all(since=since_b, limit=5000) if i.timestamp <= until_b]

    total_b = max(len(items_b), 1)
    sent_b  = Counter()
    risk_b  = 0
    for i in items_b:
        sl = (i.metadata or {}).get("sentiment_label", "NEUTRAL")
        sent_b[sl] += 1
        if (i.metadata or {}).get("business_label") in {"Risk", "Blocked", "Urgent", "Conflict", "Overload"}:
            risk_b += 1

    return {
        "period_a": {
            "label":         f"J-{period_a} → aujourd'hui",
            "total_items":   stats_a["total_items"],
            "risk_index":    stats_a["risk_index"],
            "sentiment":     stats_a["sentiment"],
            "velocity":      stats_a["velocity"]["this_week"],
            "risk_count":    stats_a["intelligence"]["risk_count"],
            "climate_label": stats_a["intelligence"]["climate_label"],
        },
        "period_b": {
            "label":         f"J-{period_b} → J-{period_a}",
            "total_items":   len(items_b),
            "risk_index":    min(100, round(risk_b / total_b * 100)),
            "sentiment": {
                "positive": round(sent_b["POSITIVE"] / total_b * 100),
                "neutral":  round(sent_b["NEUTRAL"]  / total_b * 100),
                "negative": round(sent_b["NEGATIVE"] / total_b * 100),
            },
            "velocity":      len(items_b),
            "risk_count":    risk_b,
            "climate_label": None,
        },
    }
