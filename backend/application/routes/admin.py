"""
Super Admin API — InsightFlow Executive
All endpoints require role=superadmin.
SuperAdmin manages the PLATFORM, not individual org data.

Orgs      : GET /admin/orgs · PATCH /admin/orgs/{id} · DELETE /admin/orgs/{id}
Users     : GET /admin/users · PATCH /admin/users/{id}
Connectors: GET /admin/connectors · PATCH /admin/connectors/{key}
AI/ML     : GET /admin/ai/status · POST /admin/ai/retrain
Stats     : GET /admin/stats
"""
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import ConnectorCatalog, Organisation, User, SourceConfig, MessageRaw
from core.security import require_superadmin

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_PLANS = {"free", "pro", "enterprise"}
VALID_ROLES = {"ceo", "pm"}


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
