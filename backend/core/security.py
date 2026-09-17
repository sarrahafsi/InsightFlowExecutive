"""
JWT authentication + password hashing utilities.
"""
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.access_token_expire_hours)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _decode_and_load_user(token: str | None, db: Session):
    """Decode a JWT and load the matching active User — shared by HTTP and WebSocket auth."""
    from core.models import User

    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise exc
    user = _decode_and_load_user(credentials.credentials, db)
    if user is None:
        raise exc
    return user


def get_current_user_ws(token: str | None, db: Session):
    """Same decode/lookup as get_current_user, for WebSocket handshakes (token via query param)."""
    return _decode_and_load_user(token, db)


def require_superadmin(user=Depends(get_current_user)):
    """Platform management only — no org data access, never gated on email/org state."""
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


def get_current_org_user(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Authenticated + email verified + attached to an organisation.
    The real gate for business-data routes — use instead of get_current_user
    everywhere org-scoped data is read or written.
    """
    if not user.email_verified:
        raise HTTPException(status_code=403, detail={"detail": "email_not_verified"})
    if not user.org_id:
        raise HTTPException(status_code=403, detail={"detail": "organisation_required"})
    return user


def require_ceo(user=Depends(get_current_org_user)):
    """Org-level admin — CEO manages their own organisation only."""
    if user.role != "ceo":
        raise HTTPException(status_code=403, detail="CEO access required")
    return user


# Public webmail domains — shared by millions of unrelated accounts, so matching
# the domain alone proves nothing. An exact email match is required for these.
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "hotmail.fr", "live.com", "live.fr", "msn.com",
    "yahoo.com", "yahoo.fr",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me", "gmx.com", "gmx.fr",
}


def is_same_org_account(connected_email: str | None, requesting_email: str | None) -> bool:
    """
    True if `connected_email` (the OAuth account that just authorized) may be linked
    to `requesting_email` (the InsightFlow user who started the connect flow).

    On a company domain (acme.com), sharing the domain is enough — anyone on it is
    presumably company-controlled. On a public webmail domain (gmail.com, outlook.com…)
    that assumption is false, since anyone can register @gmail.com — so we fall back
    to requiring the exact same email address there.
    """
    def _norm(e: str | None) -> str:
        return (e or "").strip().lower()

    a, b = _norm(connected_email), _norm(requesting_email)
    if not a or not b or "@" not in a or "@" not in b:
        return False

    domain_a = a.rsplit("@", 1)[-1]
    domain_b = b.rsplit("@", 1)[-1]
    if domain_a != domain_b:
        return False

    if domain_a in PUBLIC_EMAIL_DOMAINS:
        return a == b

    return True


def require_plan(feature: str):
    """Factory — gates a route behind a plan feature flag (see core/plans.py)."""
    def _dep(user=Depends(get_current_org_user), db: Session = Depends(get_db)):
        from core.models import Organisation
        from core.plans import get_plan_features, min_plan_for

        org = db.query(Organisation).filter(Organisation.id == user.org_id).first()
        plan = org.plan if org else "free"
        if not get_plan_features(plan).get(feature, False):
            raise HTTPException(status_code=403, detail={
                "detail": "upgrade_required",
                "feature": feature,
                "required_plan": min_plan_for(feature),
                "current_plan": plan,
            })
        return user
    return _dep
