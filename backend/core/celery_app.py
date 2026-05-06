"""
Celery Application — InsightFlow Executive
==========================================
Async task queue with Redis as broker.

Usage:
  Start worker:  celery -A core.celery_app worker --loglevel=info
  Start beat:    celery -A core.celery_app beat --loglevel=info
"""
import sys
import os

# Ensure backend/ is in sys.path regardless of where Celery is launched from
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "insightflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "tasks.nlp_tasks",
        "tasks.sync_tasks",
        "tasks.report_tasks",
        "tasks.orchestrate_tasks",
        "tasks.anomaly_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    worker_pool="solo",
)

# ── Tâches planifiées (Celery Beat) ──────────────────────────
celery_app.conf.beat_schedule = {
    # Sync Gmail toutes les 30 minutes
    "sync-gmail-every-30min": {
        "task": "tasks.sync_tasks.sync_gmail",
        "schedule": crontab(minute="*/30"),
    },
    # Brief hebdomadaire tous les lundis à 07h00
    "monday-brief-weekly": {
        "task": "tasks.report_tasks.generate_monday_brief",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
    },
    # Détection burnout toutes les heures
    "burnout-check-hourly": {
        "task": "tasks.nlp_tasks.detect_burnout_signals",
        "schedule": crontab(minute=0),
    },
    # Détection d'anomalies Isolation Forest — chaque jour à 06h00
    "anomaly-detection-daily": {
        "task": "tasks.anomaly_tasks.detect_anomalies",
        "schedule": crontab(hour=6, minute=0),
    },
}
