"""
Orchestration Tasks — exécute l'orchestrateur AI après chaque sync.
"""
import logging
from core.celery_app import celery_app

logger = logging.getLogger(__name__)

# Dernier résultat d'orchestration (cache mémoire, partagé au sein du worker)
_latest_result: dict = {}


def get_latest() -> dict:
    return _latest_result


@celery_app.task(name="tasks.orchestrate_tasks.run_orchestration")
def run_orchestration(source: str = "gmail", new_items: int = 0):
    """
    Tâche Celery principale d'orchestration.
    Appelée automatiquement à la fin de chaque sync source.
    """
    import asyncio
    from datetime import datetime, timedelta
    from core.database import SessionLocal
    from core.models import MessageRaw, HumanCorrection
    from intelligence.orchestrator import AIOrchestrator, OrchestrationContext

    global _latest_result
    logger.info("[Orchestrator] source=%s  new_items=%d", source, new_items)

    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=90)
        recent = db.query(MessageRaw).filter(MessageRaw.timestamp >= since).all()
        total  = len(recent)

        if total == 0:
            logger.info("[Orchestrator] Aucun message — skip")
            return {"status": "skipped", "reason": "no_messages"}

        # ── Métriques contextuelles ─────────────────────────────────
        negative = sum(1 for m in recent if m.sentiment_label == "NEGATIVE")
        urgent   = sum(1 for m in recent if m.business_label in ("Urgent", "Risk", "Blocked", "Conflict"))
        risk     = sum(1 for m in recent if m.business_label in ("Blocked", "Risk", "Conflict", "Urgent"))
        burnout  = sum(1 for m in recent if (m.burnout_score or 0) >= 0.7)

        corrections = db.query(HumanCorrection).filter(
            HumanCorrection.used_for_training == False  # noqa: E712
        ).count()

        drift    = (negative / total) > 0.45
        now      = datetime.utcnow()
        is_monday = (now.weekday() == 0 and 6 <= now.hour <= 10)

        ctx = OrchestrationContext(
            source=source,
            new_items=new_items,
            total_recent=total,
            negative_pct=negative / total,
            high_burnout_count=burnout,
            urgent_count=urgent,
            risk_count=risk,
            is_monday_morning=is_monday,
            corrections_pending=corrections,
            drift_detected=drift,
        )

        # ── Analyse (règles + LLM) ─────────────────────────────────
        orchestrator = AIOrchestrator()
        decision = asyncio.run(orchestrator.analyze_with_llm(ctx))

        logger.info(
            "[Orchestrator] alert=%s(%s)  brief=%s  retrain=%s  rag=%s",
            decision.should_alert, decision.alert_level,
            decision.should_generate_brief, decision.should_retrain, decision.should_index_rag,
        )

        # ── Déclencher les tâches décidées ─────────────────────────
        from tasks.report_tasks import generate_monday_brief, index_rag, ml_retrain

        if decision.should_generate_brief:
            generate_monday_brief.delay()
            logger.info("[Orchestrator] → Monday Brief lancé")

        if decision.should_index_rag:
            index_rag.delay()
            logger.info("[Orchestrator] → Indexation RAG lancée")

        if decision.should_retrain:
            ml_retrain.delay(task=decision.retrain_task)
            logger.info("[Orchestrator] → Retraining %s lancé", decision.retrain_task)

        # ── Sauvegarder le résultat (cache mémoire) ────────────────
        result = {
            "status":    "ok",
            "source":    source,
            "new_items": new_items,
            "timestamp": now.isoformat(),
            "context": {
                "total_recent":    total,
                "negative_pct":    round(ctx.negative_pct * 100, 1),
                "urgent":          urgent,
                "burnout":         burnout,
                "risk":            risk,
                "corrections":     corrections,
                "drift_detected":  drift,
                "is_monday":       is_monday,
            },
            "decision": {
                "alert":            decision.should_alert,
                "alert_level":      decision.alert_level,
                "alert_reason":     decision.alert_reason,
                "brief":            decision.should_generate_brief,
                "retrain":          decision.should_retrain,
                "retrain_task":     decision.retrain_task,
                "rag":              decision.should_index_rag,
                "commentary":       decision.ai_commentary,
                "priority_actions": decision.priority_actions,
            },
        }

        _latest_result = result
        return result

    except Exception as exc:
        logger.error("[Orchestrator] Erreur : %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
