from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db

router = APIRouter(tags=["correlation"])


@router.get("/api/intelligence/correlations")
def get_correlations(window_days: int = 30, db: Session = Depends(get_db)):
    from intelligence.correlation.lag_correlator import compute_correlations
    return compute_correlations(db, window_days=window_days)
