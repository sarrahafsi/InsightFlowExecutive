from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import User
from core.security import require_plan

router = APIRouter(tags=["health"])


@router.get("/api/health/ohs")
def get_ohs(
    window_days: int = 7,
    current_user: User = Depends(require_plan("ohs")),
    db: Session = Depends(get_db),
):
    from intelligence.health.scorer import compute_ohs
    return compute_ohs(db, window_days=window_days, org_id=current_user.org_id)
