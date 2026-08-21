"""
User authentication + management endpoints.

POST /auth/login          — email + password → JWT token
POST /auth/register       — create a new organisation + CEO account
GET  /auth/me             — current user profile
PUT  /auth/me/password    — change own password

GET    /users             — list org users (ceo only)
POST   /users             — create PM in same org (ceo only)
PUT    /users/{id}/role   — change a user's role (ceo only)
DELETE /users/{id}        — deactivate a user (ceo only)
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Organisation, User
from core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_ceo,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])

VALID_ROLES = {"ceo", "pm"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str
    org_name: str


class CreateUserRequest(BaseModel):
    email: str
    full_name: str
    password: str
    role: str = "pm"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangeRoleRequest(BaseModel):
    role: str


def _user_out(u: User) -> dict:
    return {
        "id":         u.id,
        "email":      u.email,
        "full_name":  u.full_name,
        "role":       u.role,
        "org_id":     u.org_id,
        "is_active":  u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# ── Auth endpoints ────────────────────────────────────────────────────────────

@router.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_access_token(user.id, user.role)
    logger.info("[auth] login: %s (%s)", user.email, user.role)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user":         _user_out(user),
    }


@router.post("/auth/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new organisation and its CEO account in a single transaction."""
    if len(body.org_name.strip()) < 2:
        raise HTTPException(status_code=422, detail="Le nom de l'organisation est trop court.")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email déjà utilisé.")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Le mot de passe doit faire au moins 6 caractères.")

    org = Organisation(name=body.org_name.strip())
    db.add(org)
    db.flush()  # get org.id without committing

    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role="ceo",
        org_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("[auth] new org '%s' created, CEO: %s", org.name, user.email)

    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@router.get("/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)


@router.put("/auth/me/password")
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=422, detail="Le mot de passe doit faire au moins 6 caractères")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


# ── User management (ceo only — scoped to same org) ───────────────────────────

@router.get("/users")
def list_users(
    current_user: User = Depends(require_ceo),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .filter(User.org_id == current_user.org_id)
        .order_by(User.created_at)
        .all()
    )
    return [_user_out(u) for u in users]


@router.post("/users", status_code=201)
def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(require_ceo),
    db: Session = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Rôle invalide. Valeurs acceptées : {VALID_ROLES}")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Le mot de passe doit faire au moins 6 caractères")

    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        org_id=current_user.org_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("[auth] user created: %s (%s) in org %s", user.email, user.role, current_user.org_id)
    return _user_out(user)


@router.put("/users/{user_id}/role")
def change_role(
    user_id: int,
    body: ChangeRoleRequest,
    current_user: User = Depends(require_ceo),
    db: Session = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Rôle invalide. Valeurs acceptées : {VALID_ROLES}")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas changer votre propre rôle")

    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.role = body.role
    db.commit()
    return _user_out(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(require_ceo),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")

    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.is_active = False
    db.commit()
    return {"status": "ok"}
