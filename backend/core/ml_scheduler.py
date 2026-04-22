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
    Job planifié : vérifie les conditions et lance le fine-tuning si nécessaire.
    Tourne de façon asynchrone pour ne pas bloquer FastAPI.
    """
    import asyncio

    global _last_run
    now = datetime.utcnow()

    logger.info("[AutoRetrain] ── Vérification nightly (%s) ──", now.strftime("%Y-%m-%d %H:%M"))

    if not AUTO_RETRAIN_ENABLED:
        logger.info("[AutoRetrain] Désactivé (AUTO_RETRAIN_ENABLED=false)")
        return

    # ── 1. Lire les corrections disponibles ──
    corrections = _count_pending_corrections()
    logger.info("[AutoRetrain] Corrections disponibles : sentiment=%d, emotion=%d",
                corrections["sentiment"], corrections["emotion"])

    # ── 2. Décider quoi entraîner ──
    tasks_to_train = _decide_tasks_to_train(corrections)

    if not tasks_to_train:
        logger.info(
            "[AutoRetrain] Aucun entraînement nécessaire "
            "(sentiment=%d/%d, emotion=%d/%d corrections, aucun drift)",
            corrections["sentiment"], AUTO_RETRAIN_MIN_SAMPLES,
            corrections["emotion"],   AUTO_RETRAIN_MIN_SAMPLES,
        )
        _last_run.update({
            "triggered_at":   now.isoformat(),
            "trigger_reason": "check_only",
            "status":         "no_action_needed",
            "tasks_launched": [],
            "result":         {"corrections": corrections},
        })
        return

    # ── 3. Lancer les fine-tunings ──
    results = []
    for task, reason in tasks_to_train:
        logger.info("[AutoRetrain] Démarrage fine-tuning %s (%s)", task, reason)
        # On lance dans un thread pour ne pas bloquer la boucle async
        result = await asyncio.get_event_loop().run_in_executor(
            None, _run_finetuning_subprocess, task
        )
        result["reason"] = reason
        results.append(result)
        logger.info("[AutoRetrain] Résultat %s : %s", task, result["status"])

    _last_run.update({
        "triggered_at":   now.isoformat(),
        "trigger_reason": ", ".join(f"{t}: {r}" for t, r in tasks_to_train),
        "status":         "completed",
        "tasks_launched": [t for t, _ in tasks_to_train],
        "result":         results,
    })

    successes = sum(1 for r in results if r["status"] == "success")
    logger.info("[AutoRetrain] Pipeline terminé — %d/%d tâches réussies",
                successes, len(results))


# ══════════════════════════════════════════════════════════════════════
# DÉMARRAGE / ARRÊT DU SCHEDULER (appelé depuis main.py lifespan)
# ══════════════════════════════════════════════════════════════════════

def start_scheduler():
    """Démarre le scheduler APScheduler. Appelé au démarrage de FastAPI."""
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")

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
        misfire_grace_time=3600,  # si le serveur était éteint, tolère 1h de retard
    )

    _scheduler.start()
    next_run = _scheduler.get_job("auto_retrain_nightly").next_run_time
    logger.info(
        "[AutoRetrain] Scheduler démarré — prochain run : %s (min_samples=%d, enabled=%s)",
        next_run.strftime("%Y-%m-%d %H:%M UTC") if next_run else "N/A",
        AUTO_RETRAIN_MIN_SAMPLES,
        AUTO_RETRAIN_ENABLED,
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
            "running":     False,
            "enabled":     AUTO_RETRAIN_ENABLED,
            "min_samples": AUTO_RETRAIN_MIN_SAMPLES,
            "schedule":    f"Tous les jours à {AUTO_RETRAIN_CRON_HOUR:02d}:{AUTO_RETRAIN_CRON_MINUTE:02d} UTC",
            "next_run":    None,
            "last_run":    _last_run,
        }

    job = _scheduler.get_job("auto_retrain_nightly")
    return {
        "running":          _scheduler.running,
        "enabled":          AUTO_RETRAIN_ENABLED,
        "min_samples":      AUTO_RETRAIN_MIN_SAMPLES,
        "schedule":         f"Tous les jours à {AUTO_RETRAIN_CRON_HOUR:02d}:{AUTO_RETRAIN_CRON_MINUTE:02d} UTC",
        "next_run":         job.next_run_time.isoformat() if job and job.next_run_time else None,
        "last_run":         _last_run,
    }
