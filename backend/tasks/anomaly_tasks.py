"""
Anomaly Tasks — détection quotidienne d'anomalies comportementales
"""
import logging
from core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.anomaly_tasks.detect_anomalies")
def detect_anomalies(user_id: str = "default", window_days: int = 14):
    """
    Lance la détection Isolation Forest sur toutes les sources
    et persiste les AnomalyEvent détectés en base.
    """
    from core.database import SessionLocal
    from core.models import AnomalyEvent
    from intelligence.anomaly.detector import run_detection

    db = SessionLocal()
    try:
        anomalies = run_detection(db, user_id=user_id, window_days=window_days)

        saved = 0
        for a in anomalies:
            event = AnomalyEvent(**a)
            db.add(event)
            saved += 1

        db.commit()
        logger.info("[Anomaly] %d anomalie(s) détectée(s) et sauvegardées", saved)
        return {"status": "ok", "anomalies_detected": saved}

    except Exception as e:
        db.rollback()
        logger.error("[Anomaly] Erreur : %s", e)
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()
