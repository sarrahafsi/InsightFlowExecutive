from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/api/health/ohs")
def get_ohs(window_days: int = 7, db: Session = Depends(get_db)):
    from intelligence.health.scorer import compute_ohs
    return compute_ohs(db, window_days=window_days)
