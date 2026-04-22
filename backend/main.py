import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.routes import sync, items, auth, sources, analytics, actions, brief, search, ml, ask, emails, projects, onedrive, decisions
from application.deps import connector_manager, item_store
from core.database import init_db, SessionLocal
from integrations.connectors.schemas import DataItem, SourceType, ItemType
from core.ml_scheduler import start_scheduler, stop_scheduler


def _build_data_item(r: dict) -> DataItem:
    import json as _json
    meta = {
        "from_email":          r.get("author_email", ""),
        "thread_id":           r.get("thread_id"),
        "sentiment_label":     r.get("sentiment_label"),
        "sentiment_score":     r.get("sentiment_score"),
        "emotion_label":       r.get("emotion_label"),
        "emotion_score":       r.get("emotion_score"),
        "topic":               r.get("topic"),
        "business_label":      r.get("business_label"),
        "business_confidence": r.get("business_confidence"),
        "business_reason":     r.get("business_reason"),
        "burnout_score":       r.get("burnout_score"),
        "hour_sent":           r.get("hour_sent"),
        "is_weekend":          r.get("is_weekend"),
        "is_after_hours":      r.get("is_after_hours"),
    }
    # Merge source-specific metadata (Jira KPIs, etc.)
    raw_meta = r.get("metadata_json")
    if raw_meta:
        if isinstance(raw_meta, str):
            try:
                raw_meta = _json.loads(raw_meta)
            except Exception:
                raw_meta = {}
        if isinstance(raw_meta, dict):
            meta.update(raw_meta)
    return DataItem(
        id=r["id"],
        source=r["source"],
        type=r["item_type"],
        title=r["title"] or "",
        content=r["content"] or "",
        author=r["author"],
        timestamp=r["timestamp"],
        url=r.get("url"),
        tags=list(r["tags"]) if r.get("tags") else [],
        metadata=meta,
    )


async def _background_sync():
    """Sync Gmail + ETL + NLP en arrière-plan après démarrage du serveur."""
    print("[bg-sync] Démarrage du sync Gmail en arrière-plan...")
    try:
        since = datetime.utcnow() - timedelta(days=90)
        results = await connector_manager.sync_all(since=since)
        new_items = connector_manager.collect_items(results)
        item_store.upsert(new_items)
        summary = connector_manager.summary(results)
        print(f"[bg-sync] Sync : {summary['total_items']} items récupérés")

        if new_items:
            from data.etl.loader import load_items
            db = SessionLocal()
            try:
                n = load_items(new_items, db)
                print(f"[bg-sync] ETL : {n} nouveaux items insérés en base")
            finally:
                db.close()

        from data.etl.loader import reprocess_unenriched, load_from_db
        db = SessionLocal()
        try:
            n = reprocess_unenriched(db, limit=200)
            if n > 0:
                print(f"[bg-sync] NLP reprocess : {n} items enrichis")

            rows = load_from_db(db, since_days=90)
            if rows:
                refreshed = []
                for r in rows:
                    try:
                        refreshed.append(_build_data_item(r))
                    except Exception:
                        pass
                item_store.upsert(refreshed)
                print(f"[bg-sync] Store rafraîchi : {len(refreshed)} items avec NLP")

            # ── ChromaDB : indexer les messages pour le RAG ──
            try:
                from intelligence.rag.embedder import index_from_db as rag_index
                n_indexed = rag_index(db, limit=2000)
                print(f"[bg-sync] ChromaDB : {n_indexed} messages indexés pour le RAG")
            except Exception as e:
                print(f"[bg-sync] ChromaDB indexation ignorée : {e}")
        finally:
            db.close()

    except Exception as e:
        print(f"[bg-sync] Erreur : {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 1. Initialiser le schéma PostgreSQL ──────────────────
    db_ok = init_db()

    # ── 2. Charger les données depuis PostgreSQL (rapide) ────
    if db_ok:
        from data.etl.loader import load_from_db
        db = SessionLocal()
        try:
            rows = load_from_db(db, since_days=90)
            if rows:
                pg_items = []
                for r in rows:
                    try:
                        pg_items.append(_build_data_item(r))
                    except Exception:
                        pass
                item_store.upsert(pg_items)
                print(f"[startup] {len(pg_items)} items chargés depuis PostgreSQL")
        finally:
            db.close()

    # ── 3. Déléguer le sync à Celery (worker séparé) ─────────
    try:
        from tasks.sync_tasks import sync_all_sources
        sync_all_sources.delay(since_days=90)
        print("[startup] Sync délégué au Celery Worker — dashboard disponible immédiatement")
    except Exception as e:
        print(f"[startup] Celery indisponible ({e}), sync local en arrière-plan")
        asyncio.create_task(_background_sync())

    # ── 4. Démarrer le scheduler MLOps (auto-retraining nightly) ──
    start_scheduler()

    yield

    # ── Arrêt propre ──────────────────────────────────────────
    stop_scheduler()


app = FastAPI(
    title="InsightFlow Executive API",
    description="AI-powered CEO dashboard — data ingestion layer",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sync.router,    prefix="/api")
app.include_router(items.router,   prefix="/api")
app.include_router(sources.router)
app.include_router(analytics.router)
app.include_router(actions.router, prefix="/api")
app.include_router(brief.router,   prefix="/api")
app.include_router(search.router,  prefix="/api")
app.include_router(ml.router,      prefix="/api")
app.include_router(ask.router,     prefix="/api")
app.include_router(emails.router,   prefix="/api")
app.include_router(projects.router)
app.include_router(onedrive.router)
app.include_router(decisions.router, prefix="/api")


@app.get("/", tags=["health"])
async def root():
    return {
        "service": "InsightFlow Executive API",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "items_in_store": item_store.count()}
