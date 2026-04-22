from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from integrations.connectors import ConnectorManager, SourceType, SyncResult
from core.store import ItemStore
from application.deps import get_manager, get_store
from core.database import SessionLocal

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncRequest(BaseModel):
    sources: list[SourceType] | None = None
    since_days: int = 7  # how far back to fetch


class SyncResponse(BaseModel):
    triggered_at: datetime
    total_items_stored: int
    results: list[dict]


def _run_nlp_background(item_ids: list[str], since_days: int, store: ItemStore) -> None:
    """Background task: run NLP on newly inserted items and refresh store."""
    import logging
    log = logging.getLogger(__name__)
    if not item_ids:
        return
    try:
        from data.etl.loader import reprocess_unenriched, load_from_db
        from main import _build_data_item
        db = SessionLocal()
        try:
            updated = reprocess_unenriched(db, limit=len(item_ids) + 50)
            rows = load_from_db(db, since_days=since_days + 7)
            refreshed = []
            for r in rows:
                try:
                    refreshed.append(_build_data_item(r))
                except Exception:
                    pass
            store.upsert(refreshed)
            log.info("[sync/bg] NLP enrichment done: %d items, store refreshed (%d)", updated, len(refreshed))
        finally:
            db.close()
    except Exception as e:
        log.warning("[sync/bg] Background NLP failed: %s", e)


@router.post("", response_model=SyncResponse)
async def trigger_sync(
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    manager: Annotated[ConnectorManager, Depends(get_manager)],
    store: Annotated[ItemStore, Depends(get_store)],
):
    """
    Trigger a data sync from all (or specific) connectors.

    - **sources**: optional list to restrict which connectors run
    - **since_days**: how many days back to pull data (default 7)
    """
    since = datetime.utcnow() - timedelta(days=body.since_days)
    results: list[SyncResult] = await manager.sync_all(
        since=since, sources=body.sources
    )

    fetched_items = ConnectorManager.collect_items(results)
    store.upsert(fetched_items)

    now = datetime.utcnow()
    for r in results:
        if r.success:
            store.set_last_sync(r.source, now)

    # ── ETL : upsert en DB SANS NLP (rapide) ───────────────
    # NLP tourne en arrière-plan pour ne pas bloquer la réponse
    etl_inserted = 0
    new_ids: list[str] = []
    if fetched_items:
        try:
            from data.etl.loader import load_items, load_from_db
            from main import _build_data_item
            db = SessionLocal()
            try:
                etl_inserted = load_items(fetched_items, db, run_nlp=False)
                new_ids = [i.id for i in fetched_items]
                # Recharger le store immédiatement (sans labels NLP pour l'instant)
                rows = load_from_db(db, since_days=body.since_days + 7)
                refreshed = []
                for r_db in rows:
                    try:
                        refreshed.append(_build_data_item(r_db))
                    except Exception:
                        pass
                store.upsert(refreshed)
            finally:
                db.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("[sync] ETL failed: %s", e)

    # ── NLP en arrière-plan (non bloquant) ──────────────────
    if new_ids:
        background_tasks.add_task(_run_nlp_background, new_ids, body.since_days, store)

    summary = manager.summary(results)

    return SyncResponse(
        triggered_at=now,
        total_items_stored=store.count(),
        results=[
            {
                "source": source,
                "items_fetched": info["items"],
                "success": info["success"],
                "error": info.get("error"),
                "nlp_processed": etl_inserted,
            }
            for source, info in summary["by_source"].items()
        ],
    )


@router.get("/status", tags=["sync"])
async def sync_status(
    store: Annotated[ItemStore, Depends(get_store)],
):
    """Returns last sync timestamps and total item count per source."""
    return {
        "total_items": store.count(),
        "last_sync": {
            source.value: store.last_sync(source)
            for source in SourceType
        },
    }


def _reload_store_from_db(db, store, since_days: int = 90) -> int:
    """Reload item store from DB with fresh NLP + source metadata. Returns count."""
    from data.etl.loader import load_from_db
    from main import _build_data_item
    rows = load_from_db(db, since_days=since_days)
    refreshed = []
    for r in rows:
        try:
            refreshed.append(_build_data_item(r))
        except Exception:
            pass
    store.upsert(refreshed)
    return len(refreshed)


@router.post("/reprocess", tags=["sync"])
async def reprocess_all_nlp(
    store: Annotated[ItemStore, Depends(get_store)],
):
    """
    Re-run NLP on ALL existing messages (overwrites current labels).
    Use after updating the NLP pipeline logic.
    """
    from data.etl.loader import reprocess_all
    db = SessionLocal()
    try:
        updated = reprocess_all(db, limit=500)
        n = _reload_store_from_db(db, store)
    finally:
        db.close()
    return {"reprocessed": updated, "store_refreshed": n}


@router.post("/force-reprocess", tags=["sync"])
async def force_reprocess_nlp(
    store: Annotated[ItemStore, Depends(get_store)],
):
    """
    Reset ALL NLP labels to NULL, then re-run the full pipeline on every row.
    Use when existing labels are wrong (bad model, logic bug, calendar misclassified, etc.).
    Unlike /reprocess, this guarantees every row is re-classified from scratch.
    """
    from data.etl.loader import force_reprocess_all
    db = SessionLocal()
    try:
        updated = force_reprocess_all(db, limit=500)
        n = _reload_store_from_db(db, store)
    finally:
        db.close()
    return {"reprocessed": updated, "store_refreshed": n}


@router.get("/jira/diagnose", tags=["sync"])
async def diagnose_jira():
    """
    Teste chaque étape de la connexion Jira et retourne les résultats détaillés.
    Utilise directement les credentials du .env.
    """
    import httpx
    from core.config import settings

    base_url   = settings.jira_base_url.rstrip("/")
    email      = settings.jira_email
    api_token  = settings.jira_api_token
    project_key = settings.jira_project_keys.split(",")[0].strip()

    results: dict = {
        "credentials": {
            "base_url": base_url,
            "email": email,
            "api_token_set": bool(api_token),
            "project_key": project_key,
        }
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        auth = (email, api_token)
        headers = {"Accept": "application/json"}

        # 1. Test auth
        try:
            r = await client.get(f"{base_url}/rest/api/3/myself", auth=auth, headers=headers)
            results["auth"] = {"status": r.status_code, "ok": r.status_code == 200,
                               "user": r.json().get("displayName") if r.status_code == 200 else r.text[:200]}
        except Exception as e:
            results["auth"] = {"ok": False, "error": str(e)}

        # 2. Lister les projets accessibles
        try:
            r = await client.get(f"{base_url}/rest/api/3/project", auth=auth, headers=headers)
            projects = r.json() if r.status_code == 200 else []
            results["projects"] = {
                "status": r.status_code,
                "count": len(projects),
                "keys": [p.get("key") for p in projects[:10]] if isinstance(projects, list) else str(projects)[:200],
            }
        except Exception as e:
            results["projects"] = {"ok": False, "error": str(e)}

        # 3. JQL search
        try:
            r = await client.get(
                f"{base_url}/rest/api/3/search/jql",
                params={"jql": f"project={project_key} ORDER BY updated DESC", "maxResults": 5,
                        "fields": "summary,status,priority,issuetype"},
                auth=auth, headers=headers,
            )
            if r.status_code == 200:
                data = r.json()
                issues = data.get("issues", [])
                results["jql_search"] = {
                    "status": 200, "total": data.get("total", 0),
                    "sample": [
                        {
                            "key": i.get("key"),
                            "status": (i.get("fields", {}).get("status") or {}).get("name"),
                            "priority": (i.get("fields", {}).get("priority") or {}).get("name"),
                            "issuetype": (i.get("fields", {}).get("issuetype") or {}).get("name"),
                        }
                        for i in issues
                    ],
                }
            else:
                results["jql_search"] = {"status": r.status_code, "error": r.text[:300]}
        except Exception as e:
            results["jql_search"] = {"ok": False, "error": str(e)}

    return results


@router.post("/jira/force-refresh", tags=["sync"])
async def force_refresh_jira(
    manager: Annotated[ConnectorManager, Depends(get_manager)],
    store: Annotated[ItemStore, Depends(get_store)],
):
    """
    Force un re-fetch complet des issues Jira :
    1. Supprime tous les items Jira de la DB
    2. Fetch frais depuis l'API Jira (JQL)
    3. Insère en DB + recharge le store
    """
    from data.etl.loader import load_items, load_from_db
    from main import _build_data_item
    from datetime import timedelta
    from core.models import MessageRaw

    db = SessionLocal()
    try:
        # 1. Supprimer les vieux items Jira
        deleted = db.query(MessageRaw).filter(MessageRaw.source == "jira").delete(synchronize_session=False)
        db.commit()

        # 2. Vider le store Jira en mémoire
        jira_ids = [i.id for i in store.all(source=SourceType.JIRA, limit=10_000)]
        for jid in jira_ids:
            store._items.pop(jid, None)

        # 3. Fetch frais depuis Jira (90 jours)
        since = datetime.utcnow() - timedelta(days=365)
        results = await manager.sync_all(since=since, sources=[SourceType.JIRA])
        fetched = ConnectorManager.collect_items(results)

        inserted = 0
        if fetched:
            inserted = load_items(fetched, db, run_nlp=False)
            store.upsert(fetched)

        # 4. Recharger depuis DB
        rows = load_from_db(db, since_days=365)
        refreshed = []
        for r in rows:
            if r.get("source") == "jira":
                try:
                    refreshed.append(_build_data_item(r))
                except Exception:
                    pass
        if refreshed:
            store.upsert(refreshed)

        # 5. Sample pour debug
        sample = [
            {
                "id": i.id,
                "status": (i.metadata or {}).get("status"),
                "priority": (i.metadata or {}).get("priority"),
                "issue_type": (i.metadata or {}).get("issue_type"),
            }
            for i in refreshed[:5]
        ]

        return {
            "deleted_from_db": deleted,
            "fetched_from_jira": len(fetched),
            "inserted_in_db": inserted,
            "reloaded_in_store": len(refreshed),
            "sample": sample,
        }
    finally:
        db.close()
