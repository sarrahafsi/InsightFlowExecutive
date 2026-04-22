"""
Sync Tasks — synchronisation asynchrone des sources de données
"""
import logging
from datetime import datetime, timedelta
from core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.sync_tasks.sync_gmail", max_retries=3)
def sync_gmail(self, since_days: int = 1):
    """Synchroniser Gmail et enrichir les nouveaux emails avec NLP."""
    try:
        from application.deps import connector_manager
        from core.database import SessionLocal
        from core.store import item_store
        from data.etl.loader import load_items, load_from_db
        from integrations.connectors.schemas import SourceType
        import asyncio

        since = datetime.utcnow() - timedelta(days=since_days)
        results = asyncio.run(connector_manager.sync_source(SourceType.GMAIL, since=since))
        new_items = connector_manager.collect_items({SourceType.GMAIL: results})
        item_store.upsert(new_items)

        db = SessionLocal()
        try:
            n = load_items(new_items, db)
            rows = load_from_db(db, since_days=since_days)
            logger.info("[Sync/Gmail] %d nouveaux items insérés", n)
        finally:
            db.close()

        # ── Orchestrateur AI post-sync ──────────────────────────
        from tasks.orchestrate_tasks import run_orchestration
        run_orchestration.delay(source="gmail", new_items=len(new_items))

        return {"status": "ok", "source": "gmail", "inserted": n}

    except Exception as exc:
        logger.error("[Sync/Gmail] Erreur : %s", exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="tasks.sync_tasks.sync_jira", max_retries=3)
def sync_jira(self, since_days: int = 1):
    """Synchroniser Jira et enrichir les tickets avec NLP."""
    try:
        from application.deps import connector_manager
        from core.database import SessionLocal
        from core.store import item_store
        from data.etl.loader import load_items
        from integrations.connectors.schemas import SourceType
        import asyncio

        since = datetime.utcnow() - timedelta(days=since_days)
        results = asyncio.run(connector_manager.sync_source(SourceType.JIRA, since=since))
        new_items = connector_manager.collect_items({SourceType.JIRA: results})
        item_store.upsert(new_items)

        db = SessionLocal()
        try:
            n = load_items(new_items, db)
            logger.info("[Sync/Jira] %d tickets insérés", n)
        finally:
            db.close()

        from tasks.orchestrate_tasks import run_orchestration
        run_orchestration.delay(source="jira", new_items=len(new_items))

        return {"status": "ok", "source": "jira", "inserted": n}

    except Exception as exc:
        logger.error("[Sync/Jira] Erreur : %s", exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="tasks.sync_tasks.sync_slack", max_retries=3)
def sync_slack(self, since_days: int = 1):
    """Synchroniser Slack et enrichir les messages avec NLP."""
    try:
        from application.deps import connector_manager
        from core.database import SessionLocal
        from core.store import item_store
        from data.etl.loader import load_items
        from integrations.connectors.schemas import SourceType
        import asyncio

        since = datetime.utcnow() - timedelta(days=since_days)
        results = asyncio.run(connector_manager.sync_source(SourceType.SLACK, since=since))
        new_items = connector_manager.collect_items({SourceType.SLACK: results})
        item_store.upsert(new_items)

        db = SessionLocal()
        try:
            n = load_items(new_items, db)
            logger.info("[Sync/Slack] %d messages insérés", n)
        finally:
            db.close()

        from tasks.orchestrate_tasks import run_orchestration
        run_orchestration.delay(source="slack", new_items=len(new_items))

        return {"status": "ok", "source": "slack", "inserted": n}

    except Exception as exc:
        logger.error("[Sync/Slack] Erreur : %s", exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.sync_tasks.sync_all_sources")
def sync_all_sources(since_days: int = 1):
    """Lancer la synchronisation de toutes les sources en parallèle."""
    from celery import group

    job = group(
        sync_gmail.s(since_days=since_days),
        sync_jira.s(since_days=since_days),
        sync_slack.s(since_days=since_days),
    )
    result = job.apply_async()
    logger.info("[Sync/All] Synchronisation de toutes les sources lancée")
    return {"status": "launched", "group_id": str(result.id)}
