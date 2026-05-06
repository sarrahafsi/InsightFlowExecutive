"""
Anomaly Detector — Isolation Forest per user/source.

Flow:
  1. Extract daily feature vectors from messages_raw
  2. Fit Isolation Forest on the historical window (or load cached model)
  3. Score the LAST day — if score below threshold → anomaly
  4. Persist AnomalyEvent in DB

Model is stored in memory per (user_id, source).
Refit automatically when new data arrives (daily Celery task).

Minimum data: 7 days before activating detection (warmup period).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# (user_id, source) → fitted IsolationForest
_model_cache: Dict[Tuple[str, str], object] = {}

SOURCES = ["gmail", "jira", "slack"]
MIN_DAYS_WARMUP = 7          # need at least this many days before detecting
CONTAMINATION = 0.05         # 5% anomaly rate — moins de faux positifs
MIN_DEVIATION_PCT = 50       # ignorer si déviation < 50% sur la feature principale
SEVERITY_THRESHOLDS = {
    "high":   -0.15,
    "medium": -0.10,
}


def _get_model(user_id: str, source: str):
    return _model_cache.get((user_id, source))


def _set_model(user_id: str, source: str, model):
    _model_cache[(user_id, source)] = model


def run_detection(db, user_id: str = "default", window_days: int = 14) -> list[dict]:
    """
    Run anomaly detection for all sources for the given user.
    Returns list of anomaly dicts (not yet persisted — caller persists).
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        logger.error("[Anomaly] scikit-learn not installed — pip install scikit-learn")
        return []

    from intelligence.anomaly.features import extract_daily_features, _FEAT_NAMES

    anomalies = []

    for source in SOURCES:
        try:
            X, feat_names, dates = extract_daily_features(db, source, window_days=window_days)

            if len(X) < MIN_DAYS_WARMUP:
                logger.info(
                    "[Anomaly/%s] Warmup — only %d days (need %d)",
                    source, len(X), MIN_DAYS_WARMUP,
                )
                continue

            # Fit on all data except last day
            X_train = X[:-1]
            X_last  = X[-1:]
            day     = dates[-1]

            model = IsolationForest(
                n_estimators=100,
                contamination=CONTAMINATION,
                random_state=42,
            )
            model.fit(X_train)
            _set_model(user_id, source, model)

            # Score last day (-1 = most anomalous, 0 = borderline, +1 = normal)
            score = float(model.score_samples(X_last)[0])
            baseline = X_train.mean(axis=0)

            severity = _severity(score)
            if severity is None:
                logger.debug("[Anomaly/%s] Score %.3f → normal", source, score)
                continue

            # Find which feature deviates most
            deviations = _top_deviations(X_last[0], baseline, feat_names)

            # Skip if top deviation is too small to be actionable
            if deviations:
                top_curr, top_base = deviations[0][1], deviations[0][2]
                if top_base > 0.01:
                    top_pct = abs((top_curr - top_base) / top_base * 100)
                    if top_pct < MIN_DEVIATION_PCT:
                        logger.debug("[Anomaly/%s] Déviation %.0f%% < seuil %d%% — ignoré", source, top_pct, MIN_DEVIATION_PCT)
                        continue
            description = _build_description(source, day, deviations, score)

            # Store values for the TOP anomalous feature (not always index 0)
            if deviations:
                top_feat = deviations[0][0]
                top_idx  = feat_names.index(top_feat) if top_feat in feat_names else 0
            else:
                top_idx = 0

            anomalies.append({
                "user_id":        user_id,
                "source":         source,
                "metric":         deviations[0][0] if deviations else "unknown",
                "current_value":  round(float(X_last[0][top_idx]), 2),
                "baseline_value": round(float(baseline[top_idx]), 2),
                "anomaly_score":  score,
                "severity":       severity,
                "description":    description,
                "detected_at":    datetime.utcnow(),
                "window_days":    window_days,
            })
            logger.info("[Anomaly/%s] %s détectée (score=%.3f)", source, severity, score)

        except Exception as e:
            logger.error("[Anomaly/%s] Erreur : %s", source, e)

    return anomalies


def _severity(score: float) -> str | None:
    if score <= SEVERITY_THRESHOLDS["high"]:
        return "high"
    if score <= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    return None


def _top_deviations(
    current: np.ndarray,
    baseline: np.ndarray,
    feat_names: list[str],
    top_k: int = 3,
) -> list[tuple[str, float, float]]:
    """Return top-k features with largest relative deviation."""
    devs = []
    for i, name in enumerate(feat_names):
        base = baseline[i]
        curr = current[i]
        if base > 0:
            ratio = (curr - base) / base
        else:
            ratio = curr
        devs.append((name, curr, base, ratio))
    devs.sort(key=lambda x: abs(x[3]), reverse=True)
    return [(d[0], d[1], d[2]) for d in devs[:top_k]]


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.1f}"


# CEO-friendly labels
_LABEL_FR = {
    "nb_messages":     "volume de messages",
    "nb_blocked":      "tickets bloqués / urgents",
    "nb_night_msgs":   "messages envoyés la nuit",
    "nb_weekend_msgs": "messages envoyés le week-end",
    "avg_burnout":     "score de surcharge",
    "nb_senders":      "expéditeurs actifs",
}

_LABEL_SOURCE = {
    "gmail": "boîte mail",
    "jira":  "Jira",
    "slack": "Slack",
}


def _build_description(
    source: str,
    day: datetime,
    deviations: list[tuple[str, float, float]],
    score: float,
) -> str:
    if not deviations:
        return f"Comportement inhabituel détecté sur {_LABEL_SOURCE.get(source, source)}."

    # Pick the most significant deviation
    feat, curr, base = deviations[0]
    label  = _LABEL_FR.get(feat, feat)
    src_fr = _LABEL_SOURCE.get(source, source)

    if base > 0.01:
        pct  = round((curr - base) / base * 100)
        sign = "+" if pct >= 0 else ""
        if abs(pct) >= 50:
            headline = (
                f"Activité inhabituelle sur {src_fr} — {label} : "
                f"{_fmt(curr)} aujourd'hui ({sign}{pct}% par rapport à la normale de {_fmt(base)}/jour)."
            )
        else:
            headline = (
                f"Légère déviation sur {src_fr} — {label} : "
                f"{_fmt(curr)} aujourd'hui (normale : {_fmt(base)}/jour)."
            )
    else:
        headline = (
            f"Signal inhabituel sur {src_fr} — {label} : "
            f"{_fmt(curr)} aujourd'hui (habituellement quasi nul)."
        )

    # Add secondary signals if meaningful
    extras = []
    for f2, c2, b2 in deviations[1:]:
        if b2 > 0.01 and abs((c2 - b2) / b2) >= 0.3:
            pct2 = round((c2 - b2) / b2 * 100)
            sign2 = "+" if pct2 >= 0 else ""
            extras.append(f"{_LABEL_FR.get(f2, f2)} : {_fmt(c2)} ({sign2}{pct2}%)")

    if extras:
        return headline + " Aussi : " + ", ".join(extras) + "."
    return headline
