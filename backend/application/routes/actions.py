"""
Action Items — tracker des messages Blocked/Urgent à traiter par le CEO.
"""
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import ActionItem

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionCreate(BaseModel):
    message_id: Optional[str] = None
    title: str
    author: Optional[str] = None
    source: Optional[str] = None
    business_label: Optional[str] = None


class ActionUpdate(BaseModel):
    done: Optional[bool] = None
    note: Optional[str] = None


@router.get("")
def list_actions(db: Session = Depends(get_db)):
    rows = (
        db.query(ActionItem)
        .order_by(ActionItem.done.asc(), ActionItem.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id":             r.id,
            "message_id":     r.message_id,
            "title":          r.title,
            "author":         r.author,
            "source":         r.source,
            "business_label": r.business_label,
            "note":           r.note,
            "done":           r.done,
            "created_at":     r.created_at,
            "done_at":        r.done_at,
        }
        for r in rows
    ]


@router.post("", status_code=201)
def create_action(body: ActionCreate, db: Session = Depends(get_db)):
    row = ActionItem(
        message_id=body.message_id,
        title=body.title,
        author=body.author,
        source=body.source,
        business_label=body.business_label,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id":             row.id,
        "message_id":     row.message_id,
        "title":          row.title,
        "author":         row.author,
        "source":         row.source,
        "business_label": row.business_label,
        "note":           row.note,
        "done":           row.done,
        "created_at":     row.created_at,
    }


@router.patch("/{action_id}")
def update_action(action_id: int, body: ActionUpdate, db: Session = Depends(get_db)):
    row = db.query(ActionItem).filter(ActionItem.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action non trouvée")

    if body.done is not None:
        row.done = body.done
        row.done_at = datetime.utcnow() if body.done else None
    if body.note is not None:
        row.note = body.note

    db.commit()
    db.refresh(row)
    return {
        "id":             row.id,
        "message_id":     row.message_id,
        "title":          row.title,
        "author":         row.author,
        "source":         row.source,
        "business_label": row.business_label,
        "note":           row.note,
        "done":           row.done,
        "created_at":     row.created_at,
        "done_at":        row.done_at,
    }


@router.delete("/{action_id}", status_code=204)
def delete_action(action_id: int, db: Session = Depends(get_db)):
    row = db.query(ActionItem).filter(ActionItem.id == action_id).first()
    if row:
        db.delete(row)
        db.commit()
