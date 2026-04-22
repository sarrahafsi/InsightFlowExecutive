"""
NLP Tasks — traitement asynchrone des messages
"""
import logging
from core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.nlp_tasks.analyze_message", max_retries=3)
def analyze_message(self, message_id: str):
    """Analyser un message unique : sentiment + émotion + topics + behavioral."""
    try:
        from core.database import SessionLocal
        from core.models import MessageRaw
        from intelligence.nlp.pipeline import NLPPipeline

        db = SessionLocal()
        try:
            msg = db.query(MessageRaw).filter(MessageRaw.id == message_id).first()
            if not msg:
                logger.warning("[NLP] Message %s introuvable", message_id)
                return {"status": "not_found", "id": message_id}

            pipeline = NLPPipeline()
            result = pipeline.process(msg.content or "")

            msg.sentiment_label    = result.get("sentiment_label")
            msg.sentiment_score    = result.get("sentiment_score")
            msg.emotion_label      = result.get("emotion_label")
            msg.emotion_score      = result.get("emotion_score")
            msg.topic              = result.get("topic")
            msg.burnout_score      = result.get("burnout_score")
            db.commit()

            logger.info("[NLP] Message %s analysé — sentiment=%s", message_id, result.get("sentiment_label"))
            return {"status": "ok", "id": message_id, "sentiment": result.get("sentiment_label")}
        finally:
            db.close()

    except Exception as exc:
        logger.error("[NLP] Erreur message %s : %s", message_id, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.nlp_tasks.detect_burnout_signals")
def detect_burnout_signals():
    """Détecter les signaux de burnout sur les messages récents (dernières 24h)."""
    from datetime import datetime, timedelta
    from core.database import SessionLocal
    from core.models import MessageRaw

    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(hours=24)
        messages = db.query(MessageRaw).filter(
            MessageRaw.timestamp >= since,
            MessageRaw.burnout_score.isnot(None),
            MessageRaw.burnout_score >= 0.7,
        ).all()

        high_risk = [
            {"id": m.id, "author": m.author, "score": m.burnout_score}
            for m in messages
        ]

        logger.info("[Burnout] %d signaux détectés (dernières 24h)", len(high_risk))
        return {"status": "ok", "burnout_signals": high_risk, "count": len(high_risk)}
    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.nlp_tasks.reprocess_unenriched", max_retries=2)
def reprocess_unenriched(self, limit: int = 100):
    """Ré-analyser les messages sans NLP (batch)."""
    try:
        from core.database import SessionLocal
        from data.etl.loader import reprocess_unenriched as _reprocess

        db = SessionLocal()
        try:
            n = _reprocess(db, limit=limit)
            logger.info("[NLP] %d messages ré-enrichis", n)
            return {"status": "ok", "reprocessed": n}
        finally:
            db.close()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
