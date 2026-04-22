"""
Report Tasks — génération asynchrone des rapports et briefs
"""
import logging
from core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.report_tasks.generate_monday_brief")
def generate_monday_brief():
    """Générer le brief hebdomadaire du CEO via LLM."""
    try:
        from core.database import SessionLocal
        from core.store import item_store
        from data.analytics.engine import compute_overview
        from intelligence.llm.client import complete
        import asyncio

        overview = compute_overview(item_store)
        total    = overview.get("total_items", 0)
        urgent   = overview.get("urgent_count", 0)
        risks    = overview.get("risk_count", 0)

        prompt = f"""Tu es l'assistant IA du CEO. Génère le brief du lundi matin.

Données de la semaine :
- Total messages analysés : {total}
- Messages urgents : {urgent}
- Risques détectés : {risks}

Rédige un brief exécutif concis (3 paragraphes max) : état général, points d'attention, priorités de la semaine."""

        brief = asyncio.run(complete(
            system="Tu es l'assistant IA personnel d'un CEO.",
            user=prompt,
            use_tools=False,
        ))

        logger.info("[Brief] Monday Brief généré (%d chars)", len(brief))
        return {"status": "ok", "brief": brief, "length": len(brief)}

    except Exception as exc:
        logger.error("[Brief] Erreur génération : %s", exc)
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="tasks.report_tasks.index_rag")
def index_rag(limit: int = 2000):
    """Indexer les messages dans ChromaDB pour le RAG."""
    try:
        from core.database import SessionLocal
        from intelligence.rag.embedder import index_from_db

        db = SessionLocal()
        try:
            n = index_from_db(db, limit=limit)
            logger.info("[RAG] %d messages indexés dans ChromaDB", n)
            return {"status": "ok", "indexed": n}
        finally:
            db.close()

    except Exception as exc:
        logger.error("[RAG] Erreur indexation : %s", exc)
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="tasks.report_tasks.ml_retrain")
def ml_retrain(task: str = "sentiment"):
    """Lancer le fine-tuning incrémental du modèle NLP."""
    try:
        import subprocess, sys
        from pathlib import Path

        ml_dir    = Path(__file__).resolve().parent.parent.parent / "ml"
        ml_script = ml_dir / "continuous_learning.py"

        result = subprocess.run(
            [sys.executable, str(ml_script), "--task", task, "--min-samples", "20"],
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if result.returncode == 0:
            logger.info("[ML] Fine-tuning %s terminé", task)
            return {"status": "ok", "task": task, "output": result.stdout[-500:]}
        else:
            logger.error("[ML] Fine-tuning %s échoué : %s", task, result.stderr[-300:])
            return {"status": "error", "task": task, "error": result.stderr[-300:]}

    except Exception as exc:
        logger.error("[ML] Erreur retrain : %s", exc)
        return {"status": "error", "error": str(exc)}
