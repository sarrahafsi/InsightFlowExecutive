"""
Decision Log — journal des décisions prises par le CEO.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import DecisionLog

router = APIRouter(prefix="/decisions", tags=["decisions"])


class DecisionCreate(BaseModel):
    title: str
    context: Optional[str] = None


class DecisionUpdate(BaseModel):
    title: Optional[str] = None
    context: Optional[str] = None
    status: Optional[str] = None   # pending | decided | cancelled


def _fmt(r: DecisionLog) -> dict:
    return {
        "id":         r.id,
        "title":      r.title,
        "context":    r.context,
        "status":     r.status,
        "created_at": r.created_at,
        "decided_at": r.decided_at,
    }


@router.get("")
def list_decisions(db: Session = Depends(get_db)):
    rows = db.query(DecisionLog).order_by(DecisionLog.created_at.desc()).limit(100).all()
    return [_fmt(r) for r in rows]


@router.post("", status_code=201)
def create_decision(body: DecisionCreate, db: Session = Depends(get_db)):
    row = DecisionLog(title=body.title, context=body.context)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _fmt(row)


@router.patch("/{decision_id}")
def update_decision(decision_id: int, body: DecisionUpdate, db: Session = Depends(get_db)):
    row = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Décision non trouvée")
    if body.title is not None:
        row.title = body.title
    if body.context is not None:
        row.context = body.context
    if body.status is not None:
        row.status = body.status
        if body.status == "decided" and not row.decided_at:
            row.decided_at = datetime.utcnow()
        elif body.status == "pending":
            row.decided_at = None
    db.commit()
    db.refresh(row)
    return _fmt(row)


@router.delete("/{decision_id}", status_code=204)
def delete_decision(decision_id: int, db: Session = Depends(get_db)):
    row = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
    if row:
        db.delete(row)
        db.commit()
