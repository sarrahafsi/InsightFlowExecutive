"""
Feature extractor for anomaly detection.

Produces one row per (source, day) with behavioral metrics:
  - nb_messages      : total messages
  - nb_blocked       : Blocked / Urgent / Risk / Conflict labels
  - nb_night_msgs    : messages sent between 20h-6h
  - nb_weekend_msgs  : messages sent on weekends
  - avg_burnout      : average burnout score
  - nb_senders       : unique senders
  - avg_thread_depth : average thread depth

No NLP content analysis — only structural / behavioral signals.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List

import numpy as np

RISK_LABELS = {"Blocked", "Urgent", "Risk", "Conflict", "Overload"}


def extract_daily_features(
    db,
    source: str,
    window_days: int = 14,
    org_id: str | None = None,
) -> tuple[np.ndarray, List[str], List[datetime]]:
    """
    Query messages_raw for the given source over the last `window_days` days.
    Returns:
        X          : ndarray shape (n_days, n_features)
        feat_names : list of feature names
        dates      : list of dates (one per row)
    """
    from core.models import MessageRaw

    since = datetime.utcnow() - timedelta(days=window_days)
    q = db.query(MessageRaw).filter(
        MessageRaw.source == source,
        MessageRaw.timestamp >= since,
    )
    if org_id:
        q = q.filter(MessageRaw.org_id == org_id)
    rows = q.all()

    # Bucket by day
    buckets: dict[datetime, dict] = defaultdict(lambda: {
        "nb_messages":  0,
        "nb_blocked":   0,
        "nb_night_msgs": 0,
        "burnout_scores": [],
        "senders": set(),
    })

    for r in rows:
        day = r.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        b = buckets[day]
        b["nb_messages"] += 1
        if r.business_label in RISK_LABELS:
            b["nb_blocked"] += 1
        if r.is_after_hours or (r.hour_sent is not None and (r.hour_sent >= 20 or r.hour_sent < 6)):
            b["nb_night_msgs"] += 1
        if r.burnout_score is not None:
            b["burnout_scores"].append(r.burnout_score)
        if r.author:
            b["senders"].add(r.author)

    if not buckets:
        return np.empty((0, len(_FEAT_NAMES))), _FEAT_NAMES, []

    dates = sorted(buckets.keys())
    X = []
    for d in dates:
        b = buckets[d]
        bs = b["burnout_scores"]
        X.append([
            b["nb_messages"],
            b["nb_blocked"],
            b["nb_night_msgs"],
            round(sum(bs) / len(bs), 3) if bs else 0.0,
            len(b["senders"]),
        ])

    return np.array(X, dtype=float), _FEAT_NAMES, dates


_FEAT_NAMES = [
    "nb_messages",     # volume total
    "nb_blocked",      # tickets bloqués / urgents / à risque
    "nb_night_msgs",   # messages après 20h ou avant 6h
    "avg_burnout",     # score moyen de surcharge de l'équipe
    "nb_senders",      # nombre d'expéditeurs distincts
]
