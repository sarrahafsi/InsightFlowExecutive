"""
ML Route — Continuous Learning Dashboard
GET  /api/ml/status              → état des corrections + dernier fine-tuning
GET  /api/ml/history             → liste des runs de fine-tuning
POST /api/ml/retrain             → lance le script continuous_learning.py en sous-processus
GET  /api/ml/drift               → rapport de drift (calcul complet)
GET  /api/ml/drift/last          → dernier rapport de drift sauvegardé
GET  /api/ml/scheduler           → état du scheduler auto-retraining
POST /api/ml/auto-retrain/trigger → déclenche le check maintenant (sans attendre 2h)
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func

from core.database import SessionLocal
from core.models import HumanCorrection

router = APIRouter(prefix="/ml", tags=["ml"])

ML_DIR      = Path(__file__).parent.parent.parent.parent / "ml"
REPORTS_DIR = ML_DIR / "training_reports"
SCRIPT_PATH = ML_DIR / "continuous_learning.py"
REPORTS_DIR.mkdir(exist_ok=True)

# État du training en cours (simple flag en mémoire)
_training_state: dict = {"running": False, "started_at": None, "task": None}


class RetrainRequest(BaseModel):
    task: str = "sentiment"        # sentiment | emotion | all
    min_samples: int = 5
    epochs: int = 3


# ── Helpers ────────────────────────────────────────────────────────────

def _count_corrections() -> dict:
    """Compte les corrections en attente dans PostgreSQL."""
    db = SessionLocal()
    try:
        q = db.query(
            func.count(HumanCorrection.id).filter(
                HumanCorrection.corrected_sentiment.isnot(None),
                HumanCorrection.used_in_training.is_(False),
            ).label("sentiment"),
            func.count(HumanCorrection.id).filter(
                HumanCorrection.corrected_emotion.isnot(None),
                HumanCorrection.used_in_training.is_(False),
            ).label("emotion"),
            func.count(HumanCorrection.id).filter(
                HumanCorrection.corrected_business.isnot(None),
                HumanCorrection.used_in_training.is_(False),
            ).label("business"),
            func.count(HumanCorrection.id).filter(
                HumanCorrection.used_in_training.is_(False),
            ).label("total_pending"),
            func.count(HumanCorrection.id).label("total_all"),
            func.max(HumanCorrection.corrected_at).label("last_correction_at"),
        ).one()
        return {
            "sentiment":          q.sentiment,
            "emotion":            q.emotion,
            "business":           q.business,
            "total_pending":      q.total_pending,
            "total_all":          q.total_all,
            "last_correction_at": q.last_correction_at,
        }
    except Exception:
        return {}
    finally:
        db.close()


def _get_last_report() -> dict | None:
    """Charge le dernier rapport JSON de fine-tuning."""
    reports = sorted(REPORTS_DIR.glob("cl-*.json"), reverse=True)
    if not reports:
        return None
    try:
        with open(reports[0]) as f:
            return json.load(f)
    except Exception:
        return None


def _get_all_reports() -> list[dict]:
    """Charge tous les rapports de fine-tuning (les 20 derniers)."""
    reports = sorted(REPORTS_DIR.glob("cl-*.json"), reverse=True)[:20]
    results = []
    for r in reports:
        try:
            with open(r) as f:
                results.append(json.load(f))
        except Exception:
            pass
    return results


def _run_training_subprocess(task: str, min_samples: int, epochs: int):
    """Lance le script en sous-processus (appelé en background task)."""
    global _training_state
    _training_state = {"running": True, "started_at": datetime.utcnow().isoformat(), "task": task}
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--task", task,
             "--min-samples", str(min_samples),
             "--epochs", str(epochs)],
            capture_output=True,
            text=True,
            timeout=3600,   # max 1 heure
        )
        print(f"[ML-Route] Subprocess stdout:\n{result.stdout}")
        if result.returncode != 0:
            print(f"[ML-Route] Subprocess stderr:\n{result.stderr}")
    except subprocess.TimeoutExpired:
        print("[ML-Route] Fine-tuning timeout après 1 heure")
    except Exception as e:
        print(f"[ML-Route] Erreur subprocess : {e}")
    finally:
        _training_state = {"running": False, "started_at": None, "task": None}


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/status")
async def ml_status():
    """
    Retourne l'état complet du système de continuous learning :
    - Corrections disponibles par tâche
    - Dernier run de fine-tuning (métriques)
    - État du training en cours
    - Versions des modèles
    """
    counts = _count_corrections()
    last_report = _get_last_report()

    # Vérifier quels modèles locaux existent
    models_dir = ML_DIR / "models"
    models_info = {}
    for task in ["sentiment", "emotion"]:
        base_path = models_dir / f"insightflow-{task}-xlm-v1" if task == "sentiment" \
                    else models_dir / f"insightflow-{task}-v1"
        latest_path = models_dir / f"insightflow-{task}-latest"

        # Trouver les versions fine-tunées
        versioned = sorted(
            [d for d in models_dir.glob(f"insightflow-{task}-cl-*") if d.is_dir()],
            reverse=True,
        )

        models_info[task] = {
            "base_model_exists": base_path.exists(),
            "latest_finetuned":  str(versioned[0].name) if versioned else None,
            "versions_count":    len(versioned),
        }

    return {
        "corrections": {
            "pending_sentiment": counts.get("sentiment", 0),
            "pending_emotion":   counts.get("emotion", 0),
            "pending_business":  counts.get("business", 0),
            "total_pending":     counts.get("total_pending", 0),
            "total_all_time":    counts.get("total_all", 0),
            "last_correction_at": str(counts.get("last_correction_at", "")) or None,
        },
        "last_training": last_report,
        "training_in_progress": _training_state["running"],
        "training_started_at":  _training_state.get("started_at"),
        "training_task":        _training_state.get("task"),
        "models": models_info,
        "script_available": SCRIPT_PATH.exists(),
    }


@router.get("/history")
async def ml_history():
    """Liste tous les runs de fine-tuning avec leurs métriques."""
    return {
        "runs": _get_all_reports(),
        "total_runs": len(list(REPORTS_DIR.glob("cl-*.json"))),
    }


@router.post("/retrain")
async def trigger_retrain(body: RetrainRequest, background_tasks: BackgroundTasks):
    """
    Lance le fine-tuning incrémental en arrière-plan.
    Le script continuous_learning.py est exécuté en sous-processus pour isoler
    les dépendances PyTorch/HuggingFace du processus FastAPI principal.
    """
    if _training_state["running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Un fine-tuning est déjà en cours (task={_training_state['task']}, démarré à {_training_state['started_at']})"
        )

    if not SCRIPT_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Script continuous_learning.py introuvable : {SCRIPT_PATH}"
        )

    # Vérifier qu'il y a assez de corrections
    counts = _count_corrections()
    task_count = counts.get(body.task, counts.get("total_pending", 0)) if body.task != "all" \
                 else counts.get("total_pending", 0)

    if task_count < body.min_samples:
        raise HTTPException(
            status_code=422,
            detail=f"Pas assez de corrections ({task_count}/{body.min_samples} minimum requis pour '{body.task}')"
        )

    # Lancer en background
    background_tasks.add_task(
        _run_training_subprocess,
        task=body.task,
        min_samples=body.min_samples,
        epochs=body.epochs,
    )

    return {
        "status":   "started",
        "task":     body.task,
        "message":  f"Fine-tuning '{body.task}' lancé en arrière-plan avec {task_count} corrections.",
        "started_at": datetime.utcnow().isoformat(),
    }


@router.get("/drift")
async def drift_report(
    task: str = "all",
    window_days: int = 30,
    background_tasks: BackgroundTasks = None,
):
    """
    Lance le monitoring de dérive du modèle en production.
    Vérifie : performance drift, distribution drift, confidence drift.
    """
    import sys
    ml_dir = SCRIPT_PATH.parent
    if str(ml_dir) not in sys.path:
        sys.path.insert(0, str(ml_dir))

    try:
        from monitoring import run_monitoring_report, run_all_monitoring, get_last_monitoring_report
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Module monitoring introuvable : {e}")

    try:
        if task == "all":
            return run_all_monitoring(window_days=window_days)
        else:
            return run_monitoring_report(task=task, window_days=window_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur monitoring : {e}")


@router.get("/drift/last")
async def last_drift_report(task: str = "sentiment"):
    """Retourne le dernier rapport de monitoring sauvegardé (sans recalculer)."""
    import sys
    ml_dir = SCRIPT_PATH.parent
    if str(ml_dir) not in sys.path:
        sys.path.insert(0, str(ml_dir))

    try:
        from monitoring import get_last_monitoring_report
        report = get_last_monitoring_report(task)
        if not report:
            return {"task": task, "overall_status": "no_report", "message": "Aucun rapport de monitoring disponible."}
        return report
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Module monitoring introuvable : {e}")


@router.get("/scheduler")
async def scheduler_status():
    """
    Retourne l'état du scheduler auto-retraining :
    activé/désactivé, prochain run, dernier run, résultat.
    """
    try:
        from ml_scheduler import get_scheduler_status
        return get_scheduler_status()
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Scheduler introuvable : {e}")


@router.post("/auto-retrain/trigger")
async def trigger_auto_retrain(background_tasks: BackgroundTasks):
    """
    Déclenche immédiatement le check auto-retraining
    (sans attendre l'heure planifiée).
    Utile pour tester ou forcer une vérification manuelle.
    """
    try:
        from ml_scheduler import auto_retrain_job
        background_tasks.add_task(auto_retrain_job)
        return {
            "status":  "triggered",
            "message": "Vérification auto-retraining lancée en arrière-plan.",
            "note":    "Vérifiez GET /api/ml/scheduler dans quelques secondes pour le résultat.",
        }
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Scheduler introuvable : {e}")


@router.post("/reload-models")
async def reload_models():
    """
    Vide le cache LRU des modèles HuggingFace pour forcer le rechargement
    depuis le disque (après un fine-tuning).
    """
    reloaded = []
    try:
        from intelligence.nlp.sentiment import _load_pipeline as sent_pipe
        sent_pipe.cache_clear()
        reloaded.append("sentiment")
    except Exception as e:
        print(f"[ML] Sentiment cache clear failed: {e}")

    try:
        from intelligence.nlp.emotion import _load_pipeline as emo_pipe
        emo_pipe.cache_clear()
        reloaded.append("emotion")
    except Exception as e:
        print(f"[ML] Emotion cache clear failed: {e}")

    return {
        "status":   "ok",
        "reloaded": reloaded,
        "message":  "Les modèles seront rechargés depuis le disque au prochain message traité.",
    }
