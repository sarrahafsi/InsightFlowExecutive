"""
Anomaly — endpoints pour la détection d'anomalies comportementales
GET  /api/anomaly/events          → liste des anomalies récentes
GET  /api/anomaly/status          → statut warmup par source
POST /api/anomaly/run             → déclenche une détection manuelle
PATCH /api/anomaly/events/{id}/read → marquer comme lu
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import AnomalyEvent, User
from core.security import get_current_user

router = APIRouter(prefix="/anomaly", tags=["anomaly"])

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


@router.get("/events")
def list_anomaly_events(
    since_days: int = 7,
    source: str = "",
    severity: str = "",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retourne les anomalies détectées, triées par sévérité puis date."""
    since = datetime.utcnow() - timedelta(days=since_days)
    q = db.query(AnomalyEvent).filter(
        AnomalyEvent.detected_at >= since,
        AnomalyEvent.org_id == current_user.org_id,
    )

    if source:
        q = q.filter(AnomalyEvent.source == source)
    if severity:
        q = q.filter(AnomalyEvent.severity == severity)

    events = q.order_by(AnomalyEvent.detected_at.desc()).limit(limit).all()

    return {
        "total": len(events),
        "events": [
            {
                "id":             e.id,
                "source":         e.source,
                "metric":         e.metric,
                "current_value":  e.current_value,
                "baseline_value": e.baseline_value,
                "anomaly_score":  round(e.anomaly_score, 3),
                "severity":       e.severity,
                "description":    e.description,
                "detected_at":    e.detected_at.isoformat(),
                "is_read":        e.is_read,
            }
            for e in sorted(
                events,
                key=lambda x: (SEVERITY_ORDER.get(x.severity, 0), x.detected_at),
                reverse=True,
            )
        ],
    }


@router.get("/status")
def anomaly_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Indique pour chaque source si le warmup est terminé (≥7 jours de données).
    """
    from core.models import MessageRaw
    from intelligence.anomaly.detector import MIN_DAYS_WARMUP, SOURCES

    status = {}
    for source in SOURCES:
        oldest = (
            db.query(MessageRaw.timestamp)
            .filter(
                MessageRaw.source == source,
                MessageRaw.org_id == current_user.org_id,
            )
            .order_by(MessageRaw.timestamp.asc())
            .first()
        )
        if oldest:
            days_available = (datetime.utcnow() - oldest[0]).days
            ready = days_available >= MIN_DAYS_WARMUP
        else:
            days_available = 0
            ready = False

        status[source] = {
            "ready":          ready,
            "days_available": days_available,
            "days_needed":    MIN_DAYS_WARMUP,
        }

    return {"sources": status}


@router.post("/run")
def run_detection_now(
    window_days: int = 14,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Déclenche une détection manuelle (sans passer par Celery)."""
    from intelligence.anomaly.detector import run_detection
    from core.models import AnomalyEvent

    try:
        anomalies = run_detection(db, org_id=current_user.org_id, window_days=window_days)

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        for a in anomalies:
            db.query(AnomalyEvent).filter(
                AnomalyEvent.source == a["source"],
                AnomalyEvent.org_id == current_user.org_id,
                AnomalyEvent.detected_at >= today_start,
            ).delete()

        saved = 0
        for a in anomalies:
            db.add(AnomalyEvent(**a))
            saved += 1
        db.commit()
        return {"status": "ok", "anomalies_detected": saved, "details": [a["description"] for a in anomalies]}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/events/{event_id}/read")
def mark_as_read(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marquer une anomalie comme lue."""
    event = db.query(AnomalyEvent).filter(
        AnomalyEvent.id == event_id,
        AnomalyEvent.org_id == current_user.org_id,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Anomalie introuvable")
    event.is_read = True
    db.commit()
    return {"id": event_id, "is_read": True}
