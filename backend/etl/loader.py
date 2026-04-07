"""
ETL Loader — DataItem → PostgreSQL (messages_raw)
Stockage brut + enrichissement NLP (sentiment · emotion · topic · business).
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from connectors.schemas import DataItem

logger = logging.getLogger(__name__)

# NLP pipeline — initialisé en lazy (None jusqu'au premier appel)
_nlp_pipeline = None


def get_nlp_pipeline():
    """Lazy init du pipeline NLP — chargé une seule fois."""
    global _nlp_pipeline
    if _nlp_pipeline is None:
        from nlp.pipeline import NLPPipeline
        from nlp.sentiment import SentimentProcessor
        from nlp.emotion import EmotionProcessor
        from nlp.topics import TopicProcessor
        from nlp.behavioral import BehavioralProcessor
        from nlp.business import BusinessClassifier
        _nlp_pipeline = NLPPipeline(steps=[
            SentimentProcessor(),    # HuggingFace : POSITIVE/NEGATIVE/NEUTRAL
            EmotionProcessor(),      # HuggingFace : anger/joy/frustration...
            TopicProcessor(),        # HuggingFace zero-shot : deadline/budget...
            BehavioralProcessor(),   # Python pur : burnout/delay/volume signals
            BusinessClassifier(),    # Ollama : BLOCKED/RISK/URGENT + context
        ])
    return _nlp_pipeline


# ── Helpers ──────────────────────────────────────────────────

def _to_pg_array(lst: list[str]) -> str:
    if not lst:
        return "{}"
    escaped = [s.replace("\\", "\\\\").replace('"', '\\"') for s in lst]
    return "{" + ",".join(escaped) + "}"


# ── Loader principal ─────────────────────────────────────────

def load_items(items: list[DataItem], db: Session, run_nlp: bool = True) -> int:
    """
    Insère les DataItems dans messages_raw avec enrichissement NLP.
    - Idempotent (skip si id déjà présent).
    - run_nlp=False pour désactiver le pipeline NLP (tests, dev).
    Retourne le nombre d'items réellement insérés.
    """
    if not items:
        return 0

    # Séparer les nouveaux items des doublons
    new_items = []
    for item in items:
        exists = db.execute(
            text("SELECT 1 FROM messages_raw WHERE id = :id"),
            {"id": item.id}
        ).fetchone()
        if not exists:
            new_items.append(item)

    if not new_items:
        return 0

    # ── NLP enrichissement ────────────────────────────────────
    enriched_map: dict[str, object] = {}
    if run_nlp:
        try:
            pipeline = get_nlp_pipeline()
            enriched_list = pipeline.run_batch(new_items)
            enriched_map = {e.id: e for e in enriched_list}
            logger.info("[ETL] NLP enrichment: %d/%d items processed.", len(enriched_map), len(new_items))
        except Exception as e:
            logger.warning("[ETL] NLP pipeline failed, inserting without enrichment: %s", e)

    # ── Insert ────────────────────────────────────────────────
    inserted = 0
    for item in new_items:
        nlp = enriched_map.get(item.id)
        db.execute(
            text("""
                INSERT INTO messages_raw (
                    id, source, author, author_email,
                    timestamp, title, content, item_type,
                    tags, thread_id, url,
                    sentiment_label, sentiment_score,
                    emotion_label, emotion_score,
                    topic,
                    business_label, business_confidence, business_reason,
                    hour_sent, is_weekend, is_after_hours,
                    response_delay_min, thread_depth,
                    daily_volume, burnout_score
                ) VALUES (
                    :id, :source, :author, :author_email,
                    :timestamp, :title, :content, :item_type,
                    CAST(:tags AS text[]), :thread_id, :url,
                    :sentiment_label, :sentiment_score,
                    :emotion_label, :emotion_score,
                    :topic,
                    :business_label, :business_confidence, :business_reason,
                    :hour_sent, :is_weekend, :is_after_hours,
                    :response_delay_min, :thread_depth,
                    :daily_volume, :burnout_score
                )
            """),
            {
                "id":                   item.id,
                "source":               item.source,
                "author":               item.author,
                "author_email":         item.metadata.get("from_email", "") if item.metadata else "",
                "timestamp":            item.timestamp,
                "title":                item.title,
                "content":              (item.content or "")[:10000],
                "item_type":            item.type,
                "tags":                 _to_pg_array(item.tags or []),
                "thread_id":            item.metadata.get("thread_id") if item.metadata else None,
                "url":                  item.url,
                # NLP results (None si pipeline désactivé)
                "sentiment_label":      getattr(nlp, "sentiment_label", None),
                "sentiment_score":      getattr(nlp, "sentiment_score", None),
                "emotion_label":        getattr(nlp, "emotion_label", None),
                "emotion_score":        getattr(nlp, "emotion_score", None),
                "topic":                getattr(nlp, "topic", None),
                "business_label":       getattr(nlp, "business_label", None),
                "business_confidence":  getattr(nlp, "business_confidence", None),
                "business_reason":      getattr(nlp, "business_reason", None),
                # Behavioral signals
                "hour_sent":            nlp.metadata.get("hour_sent")         if nlp else None,
                "is_weekend":           nlp.metadata.get("is_weekend")        if nlp else None,
                "is_after_hours":       nlp.metadata.get("is_after_hours")    if nlp else None,
                "response_delay_min":   nlp.metadata.get("response_delay_min") if nlp else None,
                "thread_depth":         nlp.metadata.get("thread_depth")      if nlp else None,
                "daily_volume":         nlp.metadata.get("daily_volume")      if nlp else None,
                "burnout_score":        nlp.metadata.get("burnout_score")     if nlp else None,
            },
        )
        inserted += 1

    db.commit()
    logger.info("[ETL] %d nouveaux messages insérés.", inserted)
    return inserted


# ── Lecture depuis PostgreSQL ────────────────────────────────

def load_from_db(
    db: Session,
    source: Optional[str] = None,
    since_days: int = 30,
) -> list[dict]:
    """
    Recharge les messages depuis PostgreSQL dans l'ItemStore au démarrage.
    Inclut les résultats NLP pour éviter de re-classifier au restart.
    """
    since = datetime.utcnow() - timedelta(days=since_days)

    query = """
        SELECT id, source, author, author_email,
               timestamp, title, content, item_type,
               tags, thread_id, url,
               sentiment_label, sentiment_score,
               emotion_label, emotion_score,
               topic,
               business_label, business_confidence, business_reason
        FROM messages_raw
        WHERE timestamp >= :since
    """
    params: dict = {"since": since}

    if source:
        query += " AND source = :source"
        params["source"] = source

    query += " ORDER BY timestamp DESC LIMIT 5000"

    rows = db.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]
