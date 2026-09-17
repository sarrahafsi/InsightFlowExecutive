"""
Configuration des plans d'abonnement (free / pro / enterprise).

Source de vérité unique pour les fonctionnalités et quotas activés par plan.
Pas de table DB — config en dur, éditable directement ici.
"""
from fastapi import HTTPException

DEFAULT_PLAN = "free"

PLAN_FEATURES: dict[str, dict[str, bool]] = {
    "free": {
        "anomaly": False,
        "ohs": False,
        "recommendations": False,
        "websocket": False,
        "calendar": False,
        "brief": False,
    },
    "pro": {
        "anomaly": True,
        "ohs": True,
        "recommendations": True,
        "websocket": True,
        "calendar": True,
        "brief": True,
    },
    "enterprise": {
        "anomaly": True,
        "ohs": True,
        "recommendations": True,
        "websocket": True,
        "calendar": True,
        "brief": True,
    },
}

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free":       {"max_connectors": 1},
    "pro":        {"max_connectors": 4},
    "enterprise": {"max_connectors": None},  # None = illimité
}

# Ordre croissant — utilisé pour trouver le plan minimal qui débloque une feature
_PLAN_ORDER = ["free", "pro", "enterprise"]


def get_plan_features(plan: str | None) -> dict[str, bool]:
    return PLAN_FEATURES.get(plan or DEFAULT_PLAN, PLAN_FEATURES[DEFAULT_PLAN])


def get_plan_limits(plan: str | None) -> dict[str, int | None]:
    return PLAN_LIMITS.get(plan or DEFAULT_PLAN, PLAN_LIMITS[DEFAULT_PLAN])


def min_plan_for(feature: str) -> str:
    """Plus petit plan (dans l'ordre free < pro < enterprise) qui active `feature`."""
    for plan in _PLAN_ORDER:
        if PLAN_FEATURES.get(plan, {}).get(feature):
            return plan
    return _PLAN_ORDER[-1]


def check_org_limit(db, org_id: str | None, limit_key: str, current_count: int) -> None:
    """Lève HTTPException(403) si current_count atteint déjà la limite du plan de l'org."""
    from core.models import Organisation

    org = db.query(Organisation).filter(Organisation.id == org_id).first() if org_id else None
    plan = org.plan if org else DEFAULT_PLAN
    limit = get_plan_limits(plan).get(limit_key)
    if limit is not None and current_count >= limit:
        raise HTTPException(status_code=403, detail={
            "detail": "upgrade_required",
            "feature": limit_key,
            "current_plan": plan,
            "limit": limit,
        })
