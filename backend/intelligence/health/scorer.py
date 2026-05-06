"""
Organizational Health Score (OHS) — composite 0-100.

5 dimensions, each scored 0-100:
  1. sentiment_health   (25%) — % positive messages
  2. anomaly_health     (20%) — absence of recent anomalies
  3. burnout_health     (25%) — inverse of avg burnout level
  4. project_health     (15%) — avg health of active projects
  5. communication_health (15%) — % of after-hours messages (lower = healthier)

Trend = current 7-day score minus previous 7-day score.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

WEIGHTS = {
    "sentiment":     0.25,
    "anomaly":       0.20,
    "burnout":       0.25,
    "projects":      0.15,
    "communication": 0.15,
}

DIMENSION_LABELS = {
    "sentiment":     "Sentiment positif",
    "anomaly":       "Absence d'anomalies",
    "burnout":       "Niveau de surcharge équipe",
    "projects":      "Santé des projets",
    "communication": "Fluidité communication",
}


def _score_label(score: int) -> tuple[str, str]:
    if score >= 70:
        return "Sain", "#22c55e"
    if score >= 40:
        return "Tendu", "#f59e0b"
    return "Critique", "#ef4444"


def _compute_dimensions(db, since: datetime, until: datetime) -> dict[str, float]:
    from core.models import MessageRaw, AnomalyEvent, Project

    # ── 1. Sentiment health ──────────────────────────────────────────────────
    msgs = (
        db.query(MessageRaw.sentiment_label)
        .filter(MessageRaw.timestamp >= since, MessageRaw.timestamp < until)
        .all()
    )
    total = len(msgs)
    if total > 0:
        positive = sum(1 for m in msgs if (m.sentiment_label or "").lower() == "positive")
        negative = sum(1 for m in msgs if (m.sentiment_label or "").lower() == "negative")
        neutral  = total - positive - negative
        # positive=100pts, neutral=60pts (expected norm), negative=0pts
        sentiment_score = max(0.0, min(100.0,
            (positive * 100.0 + neutral * 60.0) / total
        ))
    else:
        sentiment_score = 60.0

    # ── 2. Anomaly health ────────────────────────────────────────────────────
    # Count DISTINCT sources with anomalies — prevents runaway penalty from daily reruns
    anomalies = (
        db.query(AnomalyEvent.source, AnomalyEvent.severity)
        .filter(AnomalyEvent.detected_at >= since, AnomalyEvent.detected_at < until)
        .all()
    )
    high_sources   = len({a.source for a in anomalies if a.severity == "high"})
    medium_sources = len({a.source for a in anomalies if a.severity == "medium"})
    anomaly_score = max(0.0, 100.0 - high_sources * 22.0 - medium_sources * 10.0)

    # ── 3. Burnout health ────────────────────────────────────────────────────
    burnout_rows = (
        db.query(MessageRaw.burnout_score)
        .filter(
            MessageRaw.timestamp >= since,
            MessageRaw.timestamp < until,
            MessageRaw.burnout_score.isnot(None),
        )
        .all()
    )
    if burnout_rows:
        avg_burnout = sum(r.burnout_score for r in burnout_rows) / len(burnout_rows)
        burnout_score = max(0.0, min(100.0, (1.0 - avg_burnout) * 100.0))
    else:
        burnout_score = 70.0

    # ── 4. Project health ────────────────────────────────────────────────────
    projects = db.query(Project.status, Project.risk_level, Project.blockers, Project.progress).all()
    if projects:
        proj_scores = []
        for p in projects:
            if p.status == "on_track":
                s = 100
            elif p.status == "at_risk":
                s = 55
            else:
                s = 15  # off_track
            # Penalise blockers
            s = max(0, s - (p.blockers or 0) * 8)
            proj_scores.append(s)
        project_score = sum(proj_scores) / len(proj_scores)
    else:
        project_score = 75.0

    # ── 5. Communication health ──────────────────────────────────────────────
    if total > 0:
        after_rows = (
            db.query(MessageRaw.is_after_hours)
            .filter(MessageRaw.timestamp >= since, MessageRaw.timestamp < until)
            .all()
        )
        after_hours = sum(1 for m in after_rows if m.is_after_hours)
        after_pct = after_hours / total
        # 0% → 100, 50% → 50, 100% → 0  (linear — CEO naturally has after-hours emails)
        comm_score = max(0.0, min(100.0, 100.0 - after_pct * 100.0))
    else:
        comm_score = 70.0

    return {
        "sentiment":     round(sentiment_score, 1),
        "anomaly":       round(anomaly_score, 1),
        "burnout":       round(burnout_score, 1),
        "projects":      round(project_score, 1),
        "communication": round(comm_score, 1),
    }


def _compute_sentiment_trend(db, since: datetime, until: datetime) -> dict:
    """
    Calcule la tendance du sentiment sur la fenêtre :
    compare les 3 premiers jours aux 3 derniers jours.
    Retourne delta (-1.0 à +1.0) et direction ('improving'|'degrading'|'stable').
    """
    from core.models import MessageRaw

    total_days = (until - since).days
    mid = total_days // 2
    mid_date = since + timedelta(days=mid)

    def _avg_sentiment(start, end) -> float:
        rows = (
            db.query(MessageRaw.sentiment_label)
            .filter(MessageRaw.timestamp >= start, MessageRaw.timestamp < end)
            .all()
        )
        if not rows:
            return 0.5
        scores = []
        for r in rows:
            lbl = (r.sentiment_label or "").lower()
            scores.append(1.0 if lbl == "positive" else 0.0 if lbl == "negative" else 0.5)
        return sum(scores) / len(scores)

    first_half = _avg_sentiment(since, mid_date)
    last_half  = _avg_sentiment(mid_date, until)
    delta      = round(last_half - first_half, 3)

    if delta > 0.05:
        direction = "improving"
    elif delta < -0.05:
        direction = "degrading"
    else:
        direction = "stable"

    return {"delta": delta, "direction": direction,
            "first_half": round(first_half, 3), "last_half": round(last_half, 3)}


def compute_ohs(db, window_days: int = 7) -> dict[str, Any]:
    now    = datetime.utcnow()
    since  = now - timedelta(days=window_days)
    prev_s = now - timedelta(days=window_days * 2)

    current_dims  = _compute_dimensions(db, since, now)
    previous_dims = _compute_dimensions(db, prev_s, since)

    def _weighted(dims: dict) -> float:
        return sum(dims[k] * WEIGHTS[k] for k in WEIGHTS)

    current_score  = round(_weighted(current_dims))
    previous_score = round(_weighted(previous_dims))
    trend = current_score - previous_score

    label, color = _score_label(current_score)
    sentiment_trend = _compute_sentiment_trend(db, since, now)

    breakdown = [
        {
            "key":    k,
            "label":  DIMENSION_LABELS[k],
            "score":  current_dims[k],
            "weight": int(WEIGHTS[k] * 100),
        }
        for k in WEIGHTS
    ]

    return {
        "score":           current_score,
        "label":           label,
        "color":           color,
        "trend":           trend,
        "sentiment_trend": sentiment_trend,
        "window_days":     window_days,
        "computed_at":     now.isoformat(),
        "breakdown":       breakdown,
    }
