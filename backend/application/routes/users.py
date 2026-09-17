"""
User authentication endpoints.

POST /auth/login               — email + password → JWT token
POST /auth/register             — create account (no org yet, email unverified)
POST /auth/verify-email         — confirm email via token, unlocks org creation
POST /auth/resend-verification  — regenerate + resend the verification email
POST /organisations             — create the user's organisation (once, post-verification)
GET  /auth/me                   — current user profile
PUT  /auth/me/password          — change own password
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.email import generate_verification_token, send_verification_email
from core.email_verification import verify_email_exists
from core.models import Organisation, User
from core.plans import PLAN_FEATURES
from core.security import (
    create_access_token,
    get_current_org_user,
    get_current_user,
    hash_password,
    require_ceo,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


class CreateOrganisationRequest(BaseModel):
    name: str
    plan: str = "free"
    sector: str | None = None
    company_size: str | None = None
    country: str | None = None
    website: str | None = None


def _user_out(u: User) -> dict:
    return {
        "id":             u.id,
        "email":          u.email,
        "full_name":      u.full_name,
        "role":           u.role,
        "org_id":         u.org_id,
        "org_plan":       u.organisation.plan if u.organisation else "free",
        "is_active":      u.is_active,
        "email_verified": u.email_verified,
        "created_at":     u.created_at.isoformat() if u.created_at else None,
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
    """Create the account. No organisation yet, email unverified — see /auth/verify-email and /organisations."""
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email déjà utilisé.")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Le mot de passe doit faire au moins 6 caractères.")

    is_valid, reason = verify_email_exists(body.email)
    if not is_valid:
        raise HTTPException(status_code=422, detail=reason or "Cette adresse email semble invalide.")

    token, expires_at = generate_verification_token()
    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role="ceo",
        org_id=None,
        email_verified=False,
        verification_token=token,
        verification_token_expires_at=expires_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("[auth] new account (unverified): %s", user.email)

    send_verification_email(user.email, user.full_name, token)

    access_token = create_access_token(user.id, user.role)
    return {"access_token": access_token, "token_type": "bearer", "user": _user_out(user)}


@router.post("/auth/verify-email")
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == body.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Lien de vérification invalide.")
    if not user.verification_token_expires_at or user.verification_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Lien de vérification expiré — demandez-en un nouveau.")

    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    db.commit()
    db.refresh(user)
    logger.info("[auth] email verified: %s", user.email)
    return _user_out(user)


@router.post("/auth/resend-verification")
def resend_verification(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.email_verified:
        return {"status": "already_verified"}

    token, expires_at = generate_verification_token()
    current_user.verification_token = token
    current_user.verification_token_expires_at = expires_at
    db.commit()

    send_verification_email(current_user.email, current_user.full_name, token)
    logger.info("[auth] verification email resent: %s", current_user.email)
    return {"status": "sent"}


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


# ── Organisation creation (post-verification, once) ────────────────────────────

@router.post("/organisations", status_code=201)
def create_organisation(
    body: CreateOrganisationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.email_verified:
        raise HTTPException(status_code=400, detail="Vérifiez votre email avant de créer votre organisation.")
    if current_user.org_id:
        raise HTTPException(status_code=400, detail="Vous appartenez déjà à une organisation.")
    if len(body.name.strip()) < 2:
        raise HTTPException(status_code=422, detail="Le nom de l'organisation est trop court.")
    if body.plan not in PLAN_FEATURES:
        raise HTTPException(status_code=422, detail=f"Plan invalide : {set(PLAN_FEATURES.keys())}")

    org = Organisation(
        name=body.name.strip(),
        plan=body.plan,
        sector=(body.sector or "").strip() or None,
        company_size=body.company_size or None,
        country=(body.country or "").strip() or None,
        website=(body.website or "").strip() or None,
        # Enterprise : données privées par défaut. Free/Pro : contribue par défaut,
        # modifiable à tout moment par le CEO dans ses paramètres.
        contributes_to_shared_training=(body.plan != "enterprise"),
    )
    db.add(org)
    db.flush()

    current_user.org_id = org.id
    db.commit()
    db.refresh(current_user)
    logger.info("[auth] org '%s' created by %s", org.name, current_user.email)

    return _user_out(current_user)


# ── Organisation settings (self-service, CEO only) ──────────────────────────

def _org_out(org: Organisation) -> dict:
    return {
        "id":                              org.id,
        "name":                            org.name,
        "plan":                            org.plan,
        "contributes_to_shared_training":  org.contributes_to_shared_training,
    }


@router.get("/organisations/me")
def get_my_organisation(
    current_user: User = Depends(get_current_org_user),
    db: Session = Depends(get_db),
):
    org = db.query(Organisation).filter(Organisation.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    return _org_out(org)


class UpdateTrainingConsentRequest(BaseModel):
    contributes_to_shared_training: bool


@router.patch("/organisations/me/training-consent")
def update_training_consent(
    body: UpdateTrainingConsentRequest,
    current_user: User = Depends(require_ceo),
    db: Session = Depends(get_db),
):
    """
    Contrôle si les corrections humaines de cette organisation alimentent le
    dataset de fine-tuning du modèle NLP partagé. Décision du CEO uniquement —
    la plateforme (superadmin) ne peut pas l'activer à sa place.
    """
    org = db.query(Organisation).filter(Organisation.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    org.contributes_to_shared_training = body.contributes_to_shared_training
    db.commit()
    logger.info(
        "[org] %s (%s) set contributes_to_shared_training=%s",
        org.id, org.name, body.contributes_to_shared_training,
    )
    return _org_out(org)
