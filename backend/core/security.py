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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    from core.models import User

    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise exc
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise exc

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise exc
    return user


def require_superadmin(user=Depends(get_current_user)):
    """Platform management only — no org data access."""
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


def require_ceo(user=Depends(get_current_user)):
    """Org-level admin — CEO manages their own organisation only."""
    if user.role != "ceo":
        raise HTTPException(status_code=403, detail="CEO access required")
    return user


def require_pm_or_above(user=Depends(get_current_user)):
    """Any authenticated org member (CEO or PM)."""
    if user.role not in ("ceo", "pm"):
        raise HTTPException(status_code=403, detail="Access denied")
    return user
