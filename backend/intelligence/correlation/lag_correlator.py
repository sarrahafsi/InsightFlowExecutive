"""
Cross-source Lag Correlator — détecte les corrélations temporelles entre sources.

Principe : pour chaque paire de sources (ex: jira ↔ gmail), on calcule la
corrélation de Pearson entre un signal A au jour T et un signal B au jour T+lag,
pour des lags de 0 à MAX_LAG jours. On retient le lag avec la corrélation
absolue la plus forte, uniquement si elle est statistiquement significative
(p-value < 0.05, test bilatéral de Student).

Signaux suivis par source :
  - sentiment  : moyenne quotidienne (positive=1, neutral=0.5, negative=0)
  - volume     : nombre de messages par jour
  - burnout    : score moyen de surcharge par jour
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

MAX_LAG    = 7     # jours de décalage maximum à tester
MIN_POINTS = 5     # minimum de points pour calculer une corrélation
P_THRESHOLD = 0.05 # seuil de significativité statistique (test bilatéral)


# ── Corrélation de Pearson ────────────────────────────────────────────────────

def _pearson(x: list[float], y: list[float]) -> tuple[float, int]:
    """Retourne (r, n) — corrélation et nombre de points utilisés."""
    n = len(x)
    if n < MIN_POINTS:
        return 0.0, n
    mx = sum(x) / n
    my = sum(y) / n
    num  = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx   = sum((xi - mx) ** 2 for xi in x)
    dy   = sum((yi - my) ** 2 for yi in y)
    denom = (dx * dy) ** 0.5
    return (0.0 if denom == 0 else num / denom), n


# ── P-value (test bilatéral de Student) ──────────────────────────────────────

def _p_value(r: float, n: int) -> float:
    """
    P-value du test de significativité de la corrélation de Pearson.
    H0 : la corrélation est nulle (due au hasard).
    Si p < 0.05, on rejette H0 → corrélation significative.
    """
    if n <= 2:
        return 1.0
    r_c = max(-1 + 1e-10, min(1 - 1e-10, r))
    t   = abs(r_c) * math.sqrt(n - 2) / math.sqrt(1 - r_c ** 2)

    # Utilise scipy si disponible (installé via sklearn/transformers)
    try:
        from scipy.stats import t as t_dist
        return float(t_dist.sf(t, df=n - 2) * 2)
    except ImportError:
        pass

    # Fallback : approximation par loi normale (fiable pour n > 30)
    if n > 30:
        p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(t / math.sqrt(2.0))))
        return max(0.0, min(1.0, p))

    # Pour petits n : approximation conservative via beta incomplète
    df  = n - 2
    x   = df / (df + t * t)
    p   = _betai(df / 2.0, 0.5, x)
    return max(0.0, min(1.0, p))


def _betai(a: float, b: float, x: float) -> float:
    """Fonction bêta incomplète régularisée — fraction continue de Lentz."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    TINY  = 1e-30
    f = C = 1.0
    D = 0.0
    for m in range(1, 150):
        for step in (0, 1):
            if step == 0:
                num = m * (b - m) * x / ((a + 2*m - 1) * (a + 2*m))
            else:
                num = -(a + m) * (a + b + m) * x / ((a + 2*m) * (a + 2*m + 1))
            D = 1.0 + num * D
            if abs(D) < TINY:
                D = TINY
            C = 1.0 + num / C
            if abs(C) < TINY:
                C = TINY
            D = 1.0 / D
            delta = C * D
            f *= delta
        if abs(delta - 1.0) < 1e-8:
            break
    return front * f


# ── Extraction des signaux journaliers par source ─────────────────────────────

def _daily_signals(db, source: str, since: datetime, until: datetime) -> dict[int, dict]:
    """Retourne {offset_jour: {sentiment, volume, burnout}} pour une source."""
    from core.models import MessageRaw

    rows = (
        db.query(
            MessageRaw.timestamp,
            MessageRaw.sentiment_label,
            MessageRaw.burnout_score,
        )
        .filter(
            MessageRaw.source == source,
            MessageRaw.timestamp >= since,
            MessageRaw.timestamp < until,
        )
        .all()
    )

    buckets: dict[int, list] = {}
    for row in rows:
        day = (row.timestamp.date() - since.date()).days
        if day < 0:
            continue
        buckets.setdefault(day, []).append(row)

    result = {}
    total_days = (until.date() - since.date()).days

    for day in range(total_days):
        msgs = buckets.get(day, [])
        if msgs:
            sentiment_vals = []
            for m in msgs:
                lbl = (m.sentiment_label or "").lower()
                if lbl == "positive":
                    sentiment_vals.append(1.0)
                elif lbl == "negative":
                    sentiment_vals.append(0.0)
                else:
                    sentiment_vals.append(0.5)
            burnout_vals = [m.burnout_score for m in msgs if m.burnout_score is not None]
            result[day] = {
                "sentiment": sum(sentiment_vals) / len(sentiment_vals),
                "volume":    float(len(msgs)),
                "burnout":   sum(burnout_vals) / len(burnout_vals) if burnout_vals else 0.0,
            }
        else:
            result[day] = {"sentiment": 0.5, "volume": 0.0, "burnout": 0.0}

    return result


# ── Libellés lisibles ─────────────────────────────────────────────────────────

_METRIC_LABELS = {
    "sentiment": "sentiment moyen",
    "volume":    "volume de messages",
    "burnout":   "score de surcharge",
}

_SOURCE_LABELS = {"gmail": "Gmail", "jira": "Jira", "slack": "Slack"}


def _insight(source_a: str, metric_a: str, source_b: str, metric_b: str,
             lag: int, r: float, p: float) -> str:
    sa  = _SOURCE_LABELS.get(source_a, source_a)
    sb  = _SOURCE_LABELS.get(source_b, source_b)
    ma  = _METRIC_LABELS.get(metric_a, metric_a)
    mb  = _METRIC_LABELS.get(metric_b, metric_b)
    dir = "hausse" if r > 0 else "baisse"
    sig = "significatif" if p < 0.01 else "probablement significatif"

    if lag == 0:
        return (f"Le {ma} de {sa} est corrélé au {mb} de {sb} "
                f"(r={r:+.2f}, p={p:.3f} — {sig}).")
    lag_str = f"{lag} jour{'s' if lag > 1 else ''} plus tard"
    return (f"Une variation du {ma} de {sa} entraîne une {dir} du {mb} de {sb}, "
            f"{lag_str} (r={r:+.2f}, p={p:.3f} — {sig}).")


def _strength(r: float) -> str:
    a = abs(r)
    if a >= 0.7:
        return "forte"
    if a >= 0.5:
        return "modérée"
    return "faible"


# ── Calcul principal ──────────────────────────────────────────────────────────

def compute_correlations(db, window_days: int = 30) -> dict[str, Any]:
    now   = datetime.utcnow()
    since = now - timedelta(days=window_days)

    from core.models import MessageRaw
    from sqlalchemy import distinct
    sources_in_db = [
        r[0] for r in db.query(distinct(MessageRaw.source)).all()
        if r[0] in ("gmail", "jira", "slack")
    ]

    if len(sources_in_db) < 2:
        return {
            "correlations": [],
            "computed_at":  now.isoformat(),
            "window_days":  window_days,
            "note": "Pas assez de sources connectées pour calculer des corrélations.",
        }

    signals: dict[str, dict] = {src: _daily_signals(db, src, since, now) for src in sources_in_db}

    metrics = ["sentiment", "volume", "burnout"]
    found: list[dict] = []

    for i, src_a in enumerate(sources_in_db):
        for src_b in sources_in_db[i + 1:]:
            for metric_a in metrics:
                for metric_b in metrics:
                    best_r   = 0.0
                    best_lag = 0
                    best_n   = 0

                    for lag in range(MAX_LAG + 1):
                        days_a = sorted(signals[src_a].keys())
                        x, y = [], []
                        for day in days_a:
                            shifted = day + lag
                            if shifted in signals[src_b]:
                                x.append(signals[src_a][day][metric_a])
                                y.append(signals[src_b][shifted][metric_b])

                        r, n = _pearson(x, y)
                        if abs(r) > abs(best_r):
                            best_r, best_lag, best_n = r, lag, n

                    if best_n < MIN_POINTS:
                        continue

                    p = _p_value(best_r, best_n)

                    # On n'affiche que les corrélations statistiquement significatives
                    if p >= P_THRESHOLD:
                        continue

                    found.append({
                        "source_a":  src_a,
                        "source_b":  src_b,
                        "metric_a":  metric_a,
                        "metric_b":  metric_b,
                        "lag_days":  best_lag,
                        "r":         round(best_r, 3),
                        "p_value":   round(p, 4),
                        "n_points":  best_n,
                        "strength":  _strength(best_r),
                        "direction": "positive" if best_r > 0 else "negative",
                        "insight":   _insight(src_a, metric_a, src_b, metric_b, best_lag, best_r, p),
                    })

    found.sort(key=lambda c: abs(c["r"]), reverse=True)
    found = found[:8]

    return {
        "correlations": found,
        "computed_at":  now.isoformat(),
        "window_days":  window_days,
        "sources":      sources_in_db,
        "p_threshold":  P_THRESHOLD,
    }
