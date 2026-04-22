from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from integrations.connectors.schemas import DataItem, ItemType, SourceType
from core.store import ItemStore
from application.deps import get_store
from core.database import get_db
from core.models import MessageRaw, HumanCorrection

router = APIRouter(prefix="/items", tags=["items"])

VALID_BUSINESS_LABELS = [
    "Progress", "Neutral Update", "Concern",
    "Risk", "Blocked", "Overload", "Conflict", "Urgent",
]
VALID_SENTIMENT_LABELS = ["POSITIVE", "NEUTRAL", "NEGATIVE"]
VALID_TOPICS = [
    "deadline", "budget", "hiring", "technical", "customer",
    "product", "strategy", "conflict", "other",
]

class CorrectionRequest(BaseModel):
    business_label:  Optional[str] = None
    sentiment_label: Optional[str] = None
    topic:           Optional[str] = None


class ItemsResponse(DataItem):
    pass


@router.get("", response_model=list[DataItem])
async def list_items(
    store: Annotated[ItemStore, Depends(get_store)],
    source: SourceType | None = Query(None, description="Filter by source (slack, gmail, jira)"),
    type: ItemType | None = Query(None, description="Filter by type (message, email, ticket)"),
    since: datetime | None = Query(None, description="ISO datetime — only items after this date"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List all synced data items with optional filters.

    Examples:
    - `GET /api/items?source=slack`
    - `GET /api/items?type=ticket&since=2026-04-01T00:00:00`
    - `GET /api/items?limit=10&offset=0`
    """
    return store.all(source=source, type=type, since=since, limit=limit, offset=offset)


@router.get("/stats", tags=["items"])
async def items_stats(store: Annotated[ItemStore, Depends(get_store)]):
    """Returns item counts broken down by source and type."""
    all_items = store.all(limit=10_000)

    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for item in all_items:
        by_source[item.source] = by_source.get(item.source, 0) + 1
        by_type[item.type] = by_type.get(item.type, 0) + 1

    return {
        "total": len(all_items),
        "by_source": by_source,
        "by_type": by_type,
    }


@router.get("/{item_id}", response_model=DataItem)
async def get_item(
    item_id: str,
    store: Annotated[ItemStore, Depends(get_store)],
):
    """Get a single item by its ID (e.g. `slack_1234`, `jira_PROJ-142`)."""
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return item


@router.patch("/{item_id}/correct")
async def correct_item(
    item_id: str,
    body: CorrectionRequest,
    store: Annotated[ItemStore, Depends(get_store)],
    db: Session = Depends(get_db),
):
    """
    Correction manuelle des labels NLP pour un message.
    Permet à l'utilisateur de corriger topic, business_label ou sentiment_label.
    """
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")

    # Validation
    if body.business_label and body.business_label not in VALID_BUSINESS_LABELS:
        raise HTTPException(status_code=422, detail=f"business_label invalide. Valeurs : {VALID_BUSINESS_LABELS}")
    if body.sentiment_label and body.sentiment_label not in VALID_SENTIMENT_LABELS:
        raise HTTPException(status_code=422, detail=f"sentiment_label invalide. Valeurs : {VALID_SENTIMENT_LABELS}")
    if body.topic and body.topic not in VALID_TOPICS:
        raise HTTPException(status_code=422, detail=f"topic invalide. Valeurs : {VALID_TOPICS}")

    updates: dict = {}
    if body.business_label  is not None: updates["business_label"]  = body.business_label
    if body.sentiment_label is not None: updates["sentiment_label"] = body.sentiment_label
    if body.topic           is not None: updates["topic"]           = body.topic

    if not updates:
        raise HTTPException(status_code=422, detail="Aucun champ à corriger fourni.")

    meta = item.metadata or {}

    # ── 1. Mettre à jour PostgreSQL ───────────────────────────
    db.query(MessageRaw).filter(MessageRaw.id == item_id).update(
        updates, synchronize_session=False
    )

    # ── 2. Logger dans human_corrections (continuous learning) ──
    correction = HumanCorrection(
        message_id=item_id,
        original_sentiment=meta.get("sentiment_label"),
        original_emotion=meta.get("emotion_label"),
        original_business=meta.get("business_label"),
        original_topic=meta.get("topic"),
        corrected_sentiment=body.sentiment_label,
        corrected_emotion=None,  # non exposée dans CorrectionModal pour l'instant
        corrected_business=body.business_label,
        corrected_topic=body.topic,
        text_snapshot=(item.content or "")[:2000],
    )
    db.add(correction)
    db.commit()

    # ── 3. Mettre à jour le store en mémoire ─────────────────
    new_meta = dict(meta)
    new_meta.update(updates)
    item.metadata = new_meta
    store.upsert([item])

    return {
        "id": item_id,
        "corrected": updates,
        "message": "Labels corrigés avec succès.",
    }
