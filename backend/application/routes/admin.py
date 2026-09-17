"""
Super Admin API — InsightFlow Executive
All endpoints require role=superadmin.
SuperAdmin manages the PLATFORM, not individual org data.

Orgs      : GET /admin/orgs · PATCH /admin/orgs/{id} · DELETE /admin/orgs/{id}
Users     : GET /admin/users · PATCH /admin/users/{id}
Connectors: GET /admin/connectors · PATCH /admin/connectors/{key}
AI/ML     : GET /admin/ai/status · POST /admin/ai/retrain
Monitoring: GET /admin/ai/drift · GET /admin/ai/scheduler · GET /admin/ai/agent
            POST /admin/ai/drift/refresh · POST /admin/ai/auto-retrain/trigger
Stats     : GET /admin/stats
"""
import asyncio

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import ConnectorCatalog, Organisation, User, SourceConfig, MessageRaw, DemoRequest
from core.security import require_superadmin

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_PLANS = {"free", "pro", "enterprise"}
VALID_ROLES = {"ceo"}
VALID_DEMO_STATUSES = {"NEW", "CONTACTED", "DEMO_SCHEDULED", "CLOSED"}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def system_stats(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return {
        "total_orgs":     db.query(Organisation).count(),
        "total_users":    db.query(User).filter(User.is_active == True).count(),
        "total_messages": db.query(MessageRaw).count(),
        "total_sources":  db.query(SourceConfig).count(),
    }


# ── Organisations ─────────────────────────────────────────────────────────────

@router.get("/orgs")
def list_orgs(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    orgs = db.query(Organisation).order_by(Organisation.created_at.desc()).all()
    result = []
    for org in orgs:
        ceo           = db.query(User).filter(User.org_id == org.id, User.role == "ceo").first()
        user_count    = db.query(User).filter(User.org_id == org.id, User.is_active == True).count()
        source_count  = db.query(SourceConfig).filter(SourceConfig.org_id == org.id).count()
        message_count = db.query(MessageRaw).filter(MessageRaw.org_id == org.id).count()
        result.append({
            "id":            org.id,
            "name":          org.name,
            "plan":          org.plan or "free",
            "created_at":    org.created_at.isoformat() if org.created_at else None,
            "ceo_email":     ceo.email     if ceo else None,
            "ceo_name":      ceo.full_name if ceo else None,
            "user_count":    user_count,
            "source_count":  source_count,
            "message_count": message_count,
        })
    return result


class UpdateOrg(BaseModel):
    plan: str | None = None
    name: str | None = None


@router.patch("/orgs/{org_id}")
def update_org(
    org_id: str,
    body: UpdateOrg,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    if body.plan is not None:
        if body.plan not in VALID_PLANS:
            raise HTTPException(status_code=422, detail=f"Plan invalide : {VALID_PLANS}")
        org.plan = body.plan
    if body.name is not None and body.name.strip():
        org.name = body.name.strip()
    db.commit()
    return {"id": org.id, "name": org.name, "plan": org.plan}


@router.delete("/orgs/{org_id}", status_code=204)
def delete_org(
    org_id: str,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    db.delete(org)
    db.commit()


# ── Users (all orgs) ──────────────────────────────────────────────────────────

@router.get("/users")
def list_all_users(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    orgs  = {o.id: o.name for o in db.query(Organisation).all()}
    return [
        {
            "id":         u.id,
            "email":      u.email,
            "full_name":  u.full_name,
            "role":       u.role,
            "org_id":     u.org_id,
            "org_name":   orgs.get(u.org_id, "—") if u.org_id else "—",
            "is_active":  u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class UpdateUser(BaseModel):
    role:      str | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UpdateUser,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if body.role is not None:
        if body.role not in (*VALID_ROLES, "superadmin"):
            raise HTTPException(status_code=422, detail=f"Rôle invalide")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    return {"id": user.id, "role": user.role, "is_active": user.is_active}


# ── Connector Catalog ─────────────────────────────────────────────────────────

@router.get("/connectors")
def list_connectors(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    connectors = db.query(ConnectorCatalog).order_by(ConnectorCatalog.category, ConnectorCatalog.name).all()
    return [
        {
            "key":         c.key,
            "name":        c.name,
            "icon":        c.icon,
            "color":       c.color,
            "category":    c.category,
            "auth_type":   c.auth_type,
            "description": c.description,
            "enabled":     c.enabled,
            "coming_soon": c.coming_soon,
        }
        for c in connectors
    ]


class UpdateConnector(BaseModel):
    enabled:     bool | None = None
    coming_soon: bool | None = None
    name:        str  | None = None
    description: str  | None = None


@router.patch("/connectors/{key}")
def update_connector(
    key: str,
    body: UpdateConnector,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    conn = db.query(ConnectorCatalog).filter(ConnectorCatalog.key == key).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connecteur introuvable")
    if body.enabled     is not None: conn.enabled     = body.enabled
    if body.coming_soon is not None: conn.coming_soon = body.coming_soon
    if body.name        is not None: conn.name        = body.name
    if body.description is not None: conn.description = body.description
    db.commit()
    return {"key": conn.key, "enabled": conn.enabled, "coming_soon": conn.coming_soon}


# ── Demandes de démo (leads commerciaux) ────────────────────────────────────────

@router.get("/demo-requests")
def list_demo_requests(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    reqs = db.query(DemoRequest).order_by(DemoRequest.created_at.desc()).all()
    return [
        {
            "id":           r.id,
            "first_name":   r.first_name,
            "last_name":    r.last_name,
            "email":        r.email,
            "company":      r.company,
            "job_title":    r.job_title,
            "company_size": r.company_size,
            "sources":      r.sources or [],
            "message":      r.message,
            "status":       r.status,
            "created_at":   r.created_at.isoformat() if r.created_at else None,
        }
        for r in reqs
    ]


class UpdateDemoRequest(BaseModel):
    status: str


@router.patch("/demo-requests/{req_id}")
def update_demo_request(
    req_id: int,
    body: UpdateDemoRequest,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    if body.status not in VALID_DEMO_STATUSES:
        raise HTTPException(status_code=422, detail=f"Statut invalide : {VALID_DEMO_STATUSES}")
    req = db.query(DemoRequest).filter(DemoRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    req.status = body.status
    db.commit()
    return {"id": req.id, "status": req.status}


# ── AI / ML Supervision ───────────────────────────────────────────────────────

@router.get("/ai/status")
async def ai_status(_: User = Depends(require_superadmin)):
    """Proxy to ML status endpoint — superadmin sees all model metrics."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("http://localhost:8000/api/ml/status")
            return r.json()
    except Exception as e:
        return {"error": str(e), "note": "ML service may not be running"}


@router.post("/ai/retrain")
async def ai_retrain(
    body: dict,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_superadmin),
):
    """Trigger continuous learning retraining — superadmin only."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post("http://localhost:8000/api/ml/retrain", json=body)
            if r.status_code == 200:
                return r.json()
            raise HTTPException(status_code=r.status_code, detail=r.json().get("detail", "Erreur"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── AI / ML Monitoring (drift, scheduler, agent autonome) ──────────────────────

@router.get("/ai/drift")
async def ai_drift(_: User = Depends(require_superadmin)):
    """Proxy — derniers rapports de drift sauvegardés (sentiment + emotion), sans recalcul."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            sentiment_r, emotion_r = await asyncio.gather(
                client.get("http://localhost:8000/api/ml/drift/last", params={"task": "sentiment"}),
                client.get("http://localhost:8000/api/ml/drift/last", params={"task": "emotion"}),
            )
            return {"sentiment": sentiment_r.json(), "emotion": emotion_r.json()}
    except Exception as e:
        return {"error": str(e), "note": "ML service may not be running"}


class DriftRefreshRequest(BaseModel):
    task: str = "all"          # sentiment | emotion | all
    window_days: int = 30


@router.post("/ai/drift/refresh")
async def ai_drift_refresh(
    body: DriftRefreshRequest,
    _: User = Depends(require_superadmin),
):
    """Recalcule le drift maintenant (peut prendre quelques secondes — évalue le modèle)."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(
                "http://localhost:8000/api/ml/drift",
                params={"task": body.task, "window_days": body.window_days},
            )
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/ai/scheduler")
async def ai_scheduler(_: User = Depends(require_superadmin)):
    """Proxy — état du scheduler auto-retraining (prochain run, dernier run)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("http://localhost:8000/api/ml/scheduler")
            return r.json()
    except Exception as e:
        return {"error": str(e), "note": "ML service may not be running"}


@router.get("/ai/agent")
async def ai_agent(_: User = Depends(require_superadmin)):
    """Proxy — dernière décision de l'agent autonome de continuous learning."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("http://localhost:8000/api/ml/agent/status")
            return r.json()
    except Exception as e:
        return {"error": str(e), "note": "ML service may not be running"}


@router.post("/ai/auto-retrain/trigger")
async def ai_auto_retrain_trigger(_: User = Depends(require_superadmin)):
    """Force immédiatement un check auto-retraining (scheduler nightly), sans attendre 2h."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post("http://localhost:8000/api/ml/auto-retrain/trigger")
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
