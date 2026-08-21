"""
InsightFlow — Auto-Retraining Scheduler
========================================
Lance automatiquement le pipeline MLOps quand les conditions sont réunies :
  - Assez de corrections humaines accumulées (>= AUTO_RETRAIN_MIN_SAMPLES)
  - ET/OU drift détecté par le monitoring

Schedule par défaut : chaque nuit à 02h00
Peut aussi être déclenché manuellement via POST /api/ml/auto-retrain/trigger

Config (variables d'environnement ou .env) :
  AUTO_RETRAIN_ENABLED      = true | false   (défaut: true)
  AUTO_RETRAIN_MIN_SAMPLES  = 20             (défaut: 20)
  AUTO_RETRAIN_CRON_HOUR    = 2              (défaut: 2 = 2h00 du matin)
  AUTO_RETRAIN_CRON_MINUTE  = 0
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
AUTO_RETRAIN_ENABLED     = os.getenv("AUTO_RETRAIN_ENABLED", "true").lower() == "true"
AUTO_RETRAIN_MIN_SAMPLES = int(os.getenv("AUTO_RETRAIN_MIN_SAMPLES", "20"))
AUTO_RETRAIN_CRON_HOUR   = int(os.getenv("AUTO_RETRAIN_CRON_HOUR",   "2"))
AUTO_RETRAIN_CRON_MINUTE = int(os.getenv("AUTO_RETRAIN_CRON_MINUTE", "0"))

# Anomaly detection schedule (default: 06:00 UTC every day)
ANOMALY_CRON_HOUR   = int(os.getenv("ANOMALY_CRON_HOUR",   "6"))
ANOMALY_CRON_MINUTE = int(os.getenv("ANOMALY_CRON_MINUTE", "0"))

ML_DIR      = Path(__file__).parent.parent / "ml"
SCRIPT_PATH = ML_DIR / "continuous_learning.py"

# ── État en mémoire ──────────────────────────────────────────────────────
_scheduler: AsyncIOScheduler | None = None

_last_run: dict = {
    "triggered_at":  None,   # datetime ISO du dernier déclenchement
    "trigger_reason": None,  # pourquoi ça a été lancé
    "status":        "never_run",
    "tasks_launched": [],
    "result":        None,
}


# ══════════════════════════════════════════════════════════════════════
# LOGIQUE DE DÉCISION
# ══════════════════════════════════════════════════════════════════════

def _count_pending_corrections() -> dict[str, int]:
    """Lit le nombre de corrections non utilisées depuis PostgreSQL."""
    try:
        from core.database import SessionLocal
        from sqlalchemy import func, text
        db = SessionLocal()
        try:
            row = db.execute(text("""
                SELECT
                  COUNT(*) FILTER (WHERE corrected_sentiment IS NOT NULL
                                   AND NOT used_in_training) AS sentiment,
                  COUNT(*) FILTER (WHERE corrected_emotion IS NOT NULL
                                   AND NOT used_in_training) AS emotion,
                  COUNT(*) FILTER (WHERE NOT used_in_training)         AS total
                FROM human_corrections
            """)).fetchone()
            return {
                "sentiment": row.sentiment or 0,
                "emotion":   row.emotion   or 0,
                "total":     row.total     or 0,
            }
        finally:
            db.close()
    except Exception as e:
        logger.warning("[AutoRetrain] Impossible de lire les corrections : %s", e)
        return {"sentiment": 0, "emotion": 0, "total": 0}


def _check_drift(task: str) -> bool:
    """
    Vérifie si un drift est détecté pour cette tâche.
    Utilise le dernier rapport de monitoring sauvegardé (pas de recalcul).
    Retourne True si alerte ou warning.
    """
    try:
        sys.path.insert(0, str(ML_DIR))
        from monitoring import get_last_monitoring_report
        report = get_last_monitoring_report(task)
        if not report:
            return False
        status = report.get("overall_status", "healthy")
        return status in ("alert", "warning")
    except Exception as e:
        logger.debug("[AutoRetrain] Drift check failed : %s", e)
        return False


def _decide_tasks_to_train(corrections: dict[str, int]) -> list[tuple[str, str]]:
    """
    Décide quelles tâches entraîner et pourquoi.
    Retourne une liste de (task, reason).
    """
    tasks = []

    for task in ("sentiment", "emotion"):
        count    = corrections.get(task, 0)
        drift    = _check_drift(task)
        reason_parts = []

        # Condition 1 : assez de corrections
        if count >= AUTO_RETRAIN_MIN_SAMPLES:
            reason_parts.append(f"{count} corrections disponibles")

        # Condition 2 : drift détecté (même avec moins de corrections)
        if drift and count >= max(5, AUTO_RETRAIN_MIN_SAMPLES // 4):
            reason_parts.append("drift détecté")

        if reason_parts:
            tasks.append((task, " + ".join(reason_parts)))

    return tasks


# ══════════════════════════════════════════════════════════════════════
# LANCEMENT DU FINE-TUNING
# ══════════════════════════════════════════════════════════════════════

def _run_finetuning_subprocess(task: str) -> dict:
    """Lance continuous_learning.py en sous-processus. Bloquant."""
    if not SCRIPT_PATH.exists():
        return {"status": "error", "reason": f"Script introuvable : {SCRIPT_PATH}"}

    logger.info("[AutoRetrain] Lancement fine-tuning task=%s", task)
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--task", task,
             "--min-samples", str(max(1, AUTO_RETRAIN_MIN_SAMPLES // 2)),
             "--epochs", "3"],
            capture_output=True,
            text=True,
            timeout=7200,   # max 2 heures
            cwd=str(ML_DIR),
            env={**os.environ, "DATABASE_URL": os.getenv("DATABASE_URL", "")},
        )
        if result.returncode == 0:
            logger.info("[AutoRetrain] Fine-tuning %s terminé avec succès", task)
            return {"status": "success", "task": task, "stdout_tail": result.stdout[-500:]}
        else:
            logger.error("[AutoRetrain] Fine-tuning %s échoué (code=%d)", task, result.returncode)
            return {"status": "failed", "task": task, "stderr": result.stderr[-300:]}
    except subprocess.TimeoutExpired:
        logger.error("[AutoRetrain] Fine-tuning %s timeout après 2h", task)
        return {"status": "timeout", "task": task}
    except Exception as e:
        logger.error("[AutoRetrain] Erreur subprocess %s : %s", task, e)
        return {"status": "error", "task": task, "reason": str(e)}


# ══════════════════════════════════════════════════════════════════════
# JOB PRINCIPAL (appelé par APScheduler chaque nuit)
# ══════════════════════════════════════════════════════════════════════

async def auto_retrain_job():
    """
    Job planifié : délègue la décision de retraining à l'agent autonome.
    L'agent analyse les patterns de corrections, raisonne via LLM, et choisit
    la meilleure stratégie (targeted vs full, quelle tâche, quelle urgence).
    Fallback sur la logique rule-based si l'agent est indisponible.
    """
    import asyncio

    global _last_run
    now = datetime.utcnow()

    logger.info("[AutoRetrain] ── Vérification nightly (%s) ──", now.strftime("%Y-%m-%d %H:%M"))

    if not AUTO_RETRAIN_ENABLED:
        logger.info("[AutoRetrain] Désactivé (AUTO_RETRAIN_ENABLED=false)")
        return

    # ── Essayer l'agent autonome ──
    try:
        sys.path.insert(0, str(ML_DIR))
        from autonomous_agent import AutonomousLearningAgent

        logger.info("[AutoRetrain] Lancement de l'agent autonome...")

        def _run_agent():
            agent = AutonomousLearningAgent()
            return agent.run(min_samples=max(1, AUTO_RETRAIN_MIN_SAMPLES // 2), epochs=3)

        log = await asyncio.to_thread(_run_agent)

        strategy  = log["decision"].get("strategy", "wait")
        executed  = log["execution"].get("executed", False)
        exec_status = log["execution"].get("status", "not_executed")

        logger.info("[AutoRetrain] Agent décision: strategy=%s, executed=%s, status=%s",
                    strategy, executed, exec_status)

        _last_run.update({
            "triggered_at":    now.isoformat(),
            "trigger_reason":  f"agent: {log['decision'].get('root_cause', strategy)}",
            "status":          "completed" if executed else "no_action_needed",
            "tasks_launched":  [log["execution"].get("task")] if executed else [],
            "result":          log,
            "agent_decision":  log["decision"],
        })
        return

    except Exception as e:
        logger.warning("[AutoRetrain] Agent indisponible (%s) — fallback rule-based", e)

    # ── Fallback : logique rule-based originale ──
    corrections = _count_pending_corrections()
    logger.info("[AutoRetrain] Fallback — corrections: sentiment=%d, emotion=%d",
                corrections["sentiment"], corrections["emotion"])

    tasks_to_train = _decide_tasks_to_train(corrections)

    if not tasks_to_train:
        logger.info("[AutoRetrain] Fallback — aucun entraînement nécessaire")
        _last_run.update({
            "triggered_at":   now.isoformat(),
            "trigger_reason": "fallback_check_only",
            "status":         "no_action_needed",
            "tasks_launched": [],
            "result":         {"corrections": corrections},
        })
        return

    results = []
    for task, reason in tasks_to_train:
        logger.info("[AutoRetrain] Fallback fine-tuning %s (%s)", task, reason)
        result = await asyncio.to_thread(_run_finetuning_subprocess, task)
        result["reason"] = reason
        results.append(result)

    successes = sum(1 for r in results if r["status"] == "success")
    logger.info("[AutoRetrain] Fallback terminé — %d/%d tâches réussies", successes, len(results))

    _last_run.update({
        "triggered_at":   now.isoformat(),
        "trigger_reason": "fallback: " + ", ".join(f"{t}: {r}" for t, r in tasks_to_train),
        "status":         "completed",
        "tasks_launched": [t for t, _ in tasks_to_train],
        "result":         results,
    })


# ══════════════════════════════════════════════════════════════════════
# DÉMARRAGE / ARRÊT DU SCHEDULER (appelé depuis main.py lifespan)
# ══════════════════════════════════════════════════════════════════════

async def nlp_enrichment_job():
    """
    Job périodique : applique le pipeline NLP sur les items insérés sans enrichissement.
    Tourne toutes les 10 minutes pour traiter les items issus des syncs Gmail/ClickUp/Jira.
    """
    import asyncio
    from core.database import SessionLocal
    from data.etl.loader import reprocess_unenriched

    db = SessionLocal()
    try:
        # Check if there are unenriched items before spinning up the pipeline
        from core.models import MessageRaw
        count = db.query(MessageRaw).filter(MessageRaw.sentiment_label.is_(None)).count()
        if count == 0:
            return
        logger.info("[NLP-Enrichment] %d items sans NLP détectés — lancement pipeline...", count)
        n = await asyncio.to_thread(reprocess_unenriched, db, 100)
        if n:
            logger.info("[NLP-Enrichment] %d items enrichis avec NLP.", n)
    except Exception as e:
        logger.error("[NLP-Enrichment] Erreur : %s", e)
    finally:
        db.close()


def gmail_periodic_sync_job():
    """
    Job périodique SYNCHRONE : sync Gmail pour toutes les orgs configurées.
    Tourne toutes les 15 minutes — exécuté dans le thread pool (pas l'event loop).
    """
    from core.database import SessionLocal
    from core.models import SourceConfig

    db = SessionLocal()
    try:
        rows = db.query(SourceConfig).filter(SourceConfig.source == "gmail").all()
        org_ids = [r.org_id for r in rows]
    except Exception as e:
        logger.warning("[Gmail-Sync] Impossible de lire source_configs : %s", e)
        return
    finally:
        db.close()

    if not org_ids:
        return

    logger.info("[Gmail-Sync] Sync périodique pour %d org(s)…", len(org_ids))

    from application.routes.auth import _do_gmail_sync_blocking
    for org_id in org_ids:
        try:
            n = _do_gmail_sync_blocking(org_id)
            if n:
                logger.info("[Gmail-Sync] org=%s → %d nouveaux items", org_id, n)
        except Exception as e:
            logger.warning("[Gmail-Sync] org=%s erreur : %s", org_id, e)


async def anomaly_detection_job():
    """
    Job planifié : détecte les anomalies comportementales sur toutes les sources.
    Tourne chaque jour à ANOMALY_CRON_HOUR:ANOMALY_CRON_MINUTE UTC.
    Sauvegarde les nouveaux événements en base et écrase ceux du jour.
    """
    from datetime import date
    from core.database import SessionLocal
    from intelligence.anomaly.detector import run_detection
    from core.models import AnomalyEvent

    now = datetime.utcnow()
    logger.info("[Anomaly] ── Détection automatique (%s) ──", now.strftime("%Y-%m-%d %H:%M"))

    db = SessionLocal()
    try:
        anomalies = run_detection(db, user_id="default", window_days=14)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for a in anomalies:
            db.query(AnomalyEvent).filter(
                AnomalyEvent.source == a["source"],
                AnomalyEvent.detected_at >= today_start,
            ).delete()

        for a in anomalies:
            db.add(AnomalyEvent(**a))
        db.commit()

        if anomalies:
            logger.info(
                "[Anomaly] %d anomalie(s) détectée(s) : %s",
                len(anomalies),
                [f"{a['source']}({a['severity']})" for a in anomalies],
            )
        else:
            logger.info("[Anomaly] Aucune anomalie détectée — tout normal.")

    except Exception as e:
        logger.error("[Anomaly] Erreur lors de la détection automatique : %s", e)
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    """Démarre le scheduler APScheduler. Appelé au démarrage de FastAPI."""
    global _scheduler

    from apscheduler.executors.pool import ThreadPoolExecutor as _TPE
    _scheduler = AsyncIOScheduler(
        timezone="UTC",
        executors={"default": {"type": "asyncio"}, "threadpool": _TPE(max_workers=3)},
    )

    _scheduler.add_job(
        auto_retrain_job,
        trigger=CronTrigger(
            hour=AUTO_RETRAIN_CRON_HOUR,
            minute=AUTO_RETRAIN_CRON_MINUTE,
            timezone="UTC",
        ),
        id="auto_retrain_nightly",
        name="Auto-Retraining Nightly Check",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_job(
        nlp_enrichment_job,
        trigger="interval",
        minutes=30,
        id="nlp_enrichment_periodic",
        name="NLP Enrichment — items non enrichis",
        replace_existing=True,
        misfire_grace_time=300,
    )

    _scheduler.add_job(
        gmail_periodic_sync_job,
        trigger="interval",
        minutes=15,
        id="gmail_periodic_sync",
        name="Gmail — sync périodique toutes les 15 min",
        replace_existing=True,
        misfire_grace_time=120,
        executor="threadpool",
    )

    _scheduler.add_job(
        anomaly_detection_job,
        trigger=CronTrigger(
            hour=ANOMALY_CRON_HOUR,
            minute=ANOMALY_CRON_MINUTE,
            timezone="UTC",
        ),
        id="anomaly_daily",
        name="Anomaly Detection Daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    next_retrain = _scheduler.get_job("auto_retrain_nightly").next_run_time
    next_anomaly = _scheduler.get_job("anomaly_daily").next_run_time
    next_nlp     = _scheduler.get_job("nlp_enrichment_periodic").next_run_time
    next_gmail   = _scheduler.get_job("gmail_periodic_sync").next_run_time
    logger.info(
        "[AutoRetrain] Scheduler démarré — prochain run : %s (min_samples=%d, enabled=%s)",
        next_retrain.strftime("%Y-%m-%d %H:%M UTC") if next_retrain else "N/A",
        AUTO_RETRAIN_MIN_SAMPLES,
        AUTO_RETRAIN_ENABLED,
    )
    logger.info(
        "[Anomaly] Job quotidien configuré — prochain run : %s",
        next_anomaly.strftime("%Y-%m-%d %H:%M UTC") if next_anomaly else "N/A",
    )
    logger.info(
        "[NLP-Enrichment] Job périodique configuré (toutes les 30 min) — prochain run : %s",
        next_nlp.strftime("%Y-%m-%d %H:%M UTC") if next_nlp else "N/A",
    )
    logger.info(
        "[Gmail-Sync] Job périodique configuré (toutes les 15 min) — prochain run : %s",
        next_gmail.strftime("%Y-%m-%d %H:%M UTC") if next_gmail else "N/A",
    )


def stop_scheduler():
    """Arrête proprement le scheduler. Appelé à l'arrêt de FastAPI."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[AutoRetrain] Scheduler arrêté.")


def get_scheduler_status() -> dict:
    """Retourne l'état du scheduler (pour le endpoint /api/ml/scheduler)."""
    if not _scheduler:
        return {
            "running":         False,
            "enabled":         AUTO_RETRAIN_ENABLED,
            "min_samples":     AUTO_RETRAIN_MIN_SAMPLES,
            "retrain_schedule": f"Tous les jours à {AUTO_RETRAIN_CRON_HOUR:02d}:{AUTO_RETRAIN_CRON_MINUTE:02d} UTC",
            "anomaly_schedule": f"Tous les jours à {ANOMALY_CRON_HOUR:02d}:{ANOMALY_CRON_MINUTE:02d} UTC",
            "next_run":        None,
            "last_run":        _last_run,
        }

    job_retrain = _scheduler.get_job("auto_retrain_nightly")
    job_anomaly = _scheduler.get_job("anomaly_daily")
    return {
        "running":                _scheduler.running,
        "enabled":                AUTO_RETRAIN_ENABLED,
        "min_samples":            AUTO_RETRAIN_MIN_SAMPLES,
        "retrain_schedule":       f"Tous les jours à {AUTO_RETRAIN_CRON_HOUR:02d}:{AUTO_RETRAIN_CRON_MINUTE:02d} UTC",
        "anomaly_schedule":       f"Tous les jours à {ANOMALY_CRON_HOUR:02d}:{ANOMALY_CRON_MINUTE:02d} UTC",
        "next_retrain_run":       job_retrain.next_run_time.isoformat() if job_retrain and job_retrain.next_run_time else None,
        "next_anomaly_run":       job_anomaly.next_run_time.isoformat() if job_anomaly and job_anomaly.next_run_time else None,
        "last_run":               _last_run,
    }
