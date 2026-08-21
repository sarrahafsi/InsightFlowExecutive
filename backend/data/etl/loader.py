"""
ETL Loader — DataItem → PostgreSQL (messages_raw)
Stockage brut + enrichissement NLP (sentiment · emotion · topic · business).
"""
from __future__ import annotations
import json as _json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from integrations.connectors.schemas import DataItem
from core.models import MessageRaw

logger = logging.getLogger(__name__)

# NLP pipeline — initialisé en lazy (None jusqu'au premier appel)
_nlp_pipeline = None


def get_nlp_pipeline():
    """Lazy init du pipeline NLP — chargé une seule fois."""
    global _nlp_pipeline
    if _nlp_pipeline is None:
        from intelligence.nlp.pipeline import NLPPipeline
        from intelligence.nlp.sentiment import SentimentProcessor
        from intelligence.nlp.emotion import EmotionProcessor
        from intelligence.nlp.topics import TopicProcessor
        from intelligence.nlp.behavioral import BehavioralProcessor
        from intelligence.nlp.business import BusinessClassifier
        _nlp_pipeline = NLPPipeline(steps=[
            SentimentProcessor(),    # HuggingFace : POSITIVE/NEGATIVE/NEUTRAL
            EmotionProcessor(),      # HuggingFace : anger/joy/frustration...
            TopicProcessor(),        # HuggingFace zero-shot : deadline/budget...
            BehavioralProcessor(),   # Python pur : burnout/delay/volume signals
            BusinessClassifier(),    # Ollama : BLOCKED/RISK/URGENT + context
        ])
    return _nlp_pipeline


# ── Helpers ──────────────────────────────────────────────────

def _build_source_meta(item: DataItem) -> dict:
    """Extrait les métadonnées source-specific (Jira KPIs, Teams channels, etc.)."""
    source_meta: dict = {}
    if item.metadata:
        for k in ("key", "status", "priority", "issue_type", "story_points",
                  "assignee", "assignee_name", "reporter", "created",
                  "cycle_time_days", "channel", "channel_id",
                  "team_id", "team_name", "channel_name", "importance"):
            if item.metadata.get(k) is not None:
                source_meta[k] = item.metadata[k]
    return source_meta


# ── Loader principal ─────────────────────────────────────────

def load_items(items: list[DataItem], db: Session, run_nlp: bool = True, org_id: str | None = None, index_rag: bool = True) -> int:
    """
    Upsert les DataItems dans messages_raw avec enrichissement NLP.
    - Nouveaux items : insertion complète avec NLP.
    - Items existants : mise à jour de metadata_json + champs de base.
    Retourne le nombre de nouveaux items insérés.
    """
    if not items:
        return 0

    # Séparer nouveaux / existants
    item_ids = [i.id for i in items]
    existing_ids: set[str] = {
        row.id for row in db.query(MessageRaw.id).filter(MessageRaw.id.in_(item_ids)).all()
    }

    new_items      = [i for i in items if i.id not in existing_ids]
    existing_items = [i for i in items if i.id in existing_ids]

    # ── NLP enrichissement sur les nouveaux items ────────────
    enriched_map: dict[str, object] = {}
    if run_nlp and new_items:
        try:
            pipeline = get_nlp_pipeline()
            new_items_for_nlp = [i for i in new_items if "SENT" not in (i.tags or [])]
            enriched_list = pipeline.run_batch(new_items_for_nlp)
            enriched_map = {e.id: e for e in enriched_list}
            logger.info("[ETL] NLP enrichment: %d/%d items processed.", len(enriched_map), len(new_items))
        except Exception as e:
            logger.warning("[ETL] NLP pipeline failed, inserting without enrichment: %s", e)

    # ── Insert nouveaux items ─────────────────────────────────
    inserted = 0
    for item in new_items:
        nlp = enriched_map.get(item.id)
        row = MessageRaw(
            id=item.id,
            org_id=org_id,
            source=item.source,
            author=item.author,
            author_email=item.metadata.get("from_email", "") if item.metadata else "",
            timestamp=item.timestamp,
            title=item.title,
            content=(item.content or "")[:10000],
            item_type=item.type,
            tags=item.tags or [],
            thread_id=item.metadata.get("thread_id") if item.metadata else None,
            url=item.url,
            # NLP
            sentiment_label=getattr(nlp, "sentiment_label", None),
            sentiment_score=getattr(nlp, "sentiment_score", None),
            emotion_label=getattr(nlp, "emotion_label", None),
            emotion_score=getattr(nlp, "emotion_score", None),
            topic=getattr(nlp, "topic", None),
            business_label=getattr(nlp, "business_label", None),
            business_confidence=getattr(nlp, "business_confidence", None),
            business_reason=getattr(nlp, "business_reason", None),
            # Behavioral
            hour_sent=nlp.metadata.get("hour_sent")          if nlp else None,
            is_weekend=nlp.metadata.get("is_weekend")        if nlp else None,
            is_after_hours=nlp.metadata.get("is_after_hours") if nlp else None,
            response_delay_min=nlp.metadata.get("response_delay_min") if nlp else None,
            thread_depth=nlp.metadata.get("thread_depth")    if nlp else None,
            daily_volume=nlp.metadata.get("daily_volume")    if nlp else None,
            burnout_score=nlp.metadata.get("burnout_score")  if nlp else None,
            metadata_json=_build_source_meta(item),
        )
        db.add(row)
        inserted += 1

    # ── Update items existants ────────────────────────────────
    updated = 0
    for item in existing_items:
        update: dict = {
            "title":         item.title,
            "content":       (item.content or "")[:10000],
            "tags":          item.tags or [],
            "url":           item.url,
            "author":        item.author,
            "timestamp":     item.timestamp,
            "metadata_json": _build_source_meta(item),
        }
        if org_id is not None:
            # Migrates items previously inserted with org_id=NULL
            update["org_id"] = org_id
        db.query(MessageRaw).filter(MessageRaw.id == item.id).update(
            update, synchronize_session=False
        )
        updated += 1

    db.commit()
    if inserted:
        logger.info("[ETL] %d nouveaux items insérés.", inserted)
    if updated:
        logger.info("[ETL] %d items existants mis à jour (metadata_json).", updated)

    # ── Indexer les nouveaux items dans ChromaDB (RAG) ────────
    if inserted > 0 and index_rag:
        try:
            from intelligence.rag.embedder import index_items
            to_index = [enriched_map.get(i.id, i) for i in new_items]
            index_items(to_index)
        except Exception as e:
            logger.warning("[ETL] ChromaDB indexation ignorée : %s", e)

    return inserted


# ── Re-enrichissement NLP des items existants ────────────

def reprocess_unenriched(db: Session, limit: int = 500) -> int:
    """
    Re-run NLP on items that have NULL sentiment_label.
    Returns number of items updated.
    """
    rows = db.query(MessageRaw).filter(
        MessageRaw.sentiment_label.is_(None)
    ).limit(limit).all()

    if not rows:
        logger.info("[ETL/Reprocess] No unenriched items found.")
        return 0

    logger.info("[ETL/Reprocess] Found %d items to re-enrich with NLP...", len(rows))

    from integrations.connectors.schemas import DataItem
    items = []
    for r in rows:
        try:
            items.append(DataItem(
                id=r.id, source=r.source,
                type=r.item_type or "email",
                title=r.title or "", content=r.content or "",
                author=r.author or "", timestamp=r.timestamp,
                metadata={},
            ))
        except Exception:
            pass

    if not items:
        return 0

    try:
        pipeline = get_nlp_pipeline()
        enriched_list = pipeline.run_batch(items)
        enriched_map = {e.id: e for e in enriched_list}
    except Exception as e:
        logger.warning("[ETL/Reprocess] NLP pipeline failed: %s", e)
        return 0

    updated = 0
    for item in items:
        nlp = enriched_map.get(item.id)
        if not nlp:
            continue
        try:
            db.query(MessageRaw).filter(MessageRaw.id == item.id).update({
                "sentiment_label":     getattr(nlp, "sentiment_label", None),
                "sentiment_score":     getattr(nlp, "sentiment_score", None),
                "emotion_label":       getattr(nlp, "emotion_label", None),
                "emotion_score":       getattr(nlp, "emotion_score", None),
                "topic":               getattr(nlp, "topic", None),
                "business_label":      getattr(nlp, "business_label", None),
                "business_confidence": getattr(nlp, "business_confidence", None),
                "business_reason":     getattr(nlp, "business_reason", None),
                "hour_sent":           nlp.metadata.get("hour_sent"),
                "is_weekend":          nlp.metadata.get("is_weekend"),
                "is_after_hours":      nlp.metadata.get("is_after_hours"),
                "burnout_score":       nlp.metadata.get("burnout_score"),
            }, synchronize_session=False)
            updated += 1
        except Exception as e:
            logger.warning("[ETL/Reprocess] Update failed for %s: %s", item.id, e)

    db.commit()
    logger.info("[ETL/Reprocess] %d items re-enriched with NLP.", updated)
    return updated


# ── Force re-enrichissement NLP de TOUS les items ───────────

def reprocess_all(db: Session, limit: int = 500) -> int:
    """
    Re-run NLP on ALL existing rows (regardless of existing labels).
    Returns number of items updated.
    """
    rows = db.query(MessageRaw).order_by(
        MessageRaw.timestamp.desc()
    ).limit(limit).all()

    if not rows:
        return 0

    logger.info("[ETL/ReprocessAll] Re-enriching %d items with updated NLP...", len(rows))

    from integrations.connectors.schemas import DataItem
    items = []
    for r in rows:
        try:
            items.append(DataItem(
                id=r.id, source=r.source,
                type=r.item_type or "email",
                title=r.title or "", content=r.content or "",
                author=r.author or "", timestamp=r.timestamp,
                metadata={},
            ))
        except Exception:
            pass

    if not items:
        return 0

    try:
        pipeline = get_nlp_pipeline()
        enriched_list = pipeline.run_batch(items)
        enriched_map = {e.id: e for e in enriched_list}
    except Exception as e:
        logger.warning("[ETL/ReprocessAll] NLP pipeline failed: %s", e)
        return 0

    updated = 0
    for item in items:
        nlp = enriched_map.get(item.id)
        if not nlp:
            continue
        try:
            db.query(MessageRaw).filter(MessageRaw.id == item.id).update({
                "sentiment_label":     getattr(nlp, "sentiment_label", None),
                "sentiment_score":     getattr(nlp, "sentiment_score", None),
                "emotion_label":       getattr(nlp, "emotion_label", None),
                "emotion_score":       getattr(nlp, "emotion_score", None),
                "topic":               getattr(nlp, "topic", None),
                "business_label":      getattr(nlp, "business_label", None),
                "business_confidence": getattr(nlp, "business_confidence", None),
                "business_reason":     getattr(nlp, "business_reason", None),
                "hour_sent":           nlp.metadata.get("hour_sent"),
                "is_weekend":          nlp.metadata.get("is_weekend"),
                "is_after_hours":      nlp.metadata.get("is_after_hours"),
                "burnout_score":       nlp.metadata.get("burnout_score"),
            }, synchronize_session=False)
            updated += 1
        except Exception as e:
            logger.warning("[ETL/ReprocessAll] Update failed for %s: %s", item.id, e)

    db.commit()
    logger.info("[ETL/ReprocessAll] %d items re-enriched.", updated)
    return updated


# ── Force reset + re-enrichissement complet ─────────────────

def force_reprocess_all(db: Session, limit: int = 500) -> int:
    """
    Reset ALL NLP columns to NULL, then re-run the full NLP pipeline.
    Returns number of items re-enriched.
    """
    db.query(MessageRaw).update({
        "sentiment_label":     None,
        "sentiment_score":     None,
        "emotion_label":       None,
        "emotion_score":       None,
        "topic":               None,
        "business_label":      None,
        "business_confidence": None,
        "business_reason":     None,
        "burnout_score":       None,
    }, synchronize_session=False)
    db.commit()
    logger.info("[ETL/ForceReprocess] All NLP labels reset to NULL.")

    return reprocess_unenriched(db, limit=limit)


# ── Lecture depuis PostgreSQL ────────────────────────────────

def load_from_db(
    db: Session,
    source: Optional[str] = None,
    since_days: int = 30,
) -> list[dict]:
    """
    Recharge les messages depuis PostgreSQL dans l'ItemStore au démarrage.
    """
    since = datetime.utcnow() - timedelta(days=since_days)

    query = db.query(MessageRaw).filter(MessageRaw.timestamp >= since)
    if source:
        query = query.filter(MessageRaw.source == source)
    query = query.order_by(MessageRaw.timestamp.desc()).limit(5000)

    rows = query.all()
    result = []
    for r in rows:
        result.append({
            "id":                   r.id,
            "source":               r.source,
            "author":               r.author,
            "author_email":         r.author_email,
            "timestamp":            r.timestamp,
            "title":                r.title,
            "content":              r.content,
            "item_type":            r.item_type,
            "tags":                 r.tags,
            "thread_id":            r.thread_id,
            "url":                  r.url,
            "sentiment_label":      r.sentiment_label,
            "sentiment_score":      r.sentiment_score,
            "emotion_label":        r.emotion_label,
            "emotion_score":        r.emotion_score,
            "topic":                r.topic,
            "business_label":       r.business_label,
            "business_confidence":  r.business_confidence,
            "business_reason":      r.business_reason,
            "hour_sent":            r.hour_sent,
            "is_weekend":           r.is_weekend,
            "is_after_hours":       r.is_after_hours,
            "burnout_score":        r.burnout_score,
            "metadata_json":        r.metadata_json or {},
        })
    return result
