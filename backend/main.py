from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import sync, items, auth, sources, analytics
from api.deps import connector_manager, item_store
from database import init_db, SessionLocal
from connectors.schemas import DataItem, SourceType, ItemType


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 1. Initialiser le schéma PostgreSQL ──────────────────
    db_ok = init_db()

    if db_ok:
        # ── 2. Charger les données existantes depuis PostgreSQL ──
        # (persistance entre restarts)
        from etl.loader import load_from_db
        db = SessionLocal()
        try:
            rows = load_from_db(db, since_days=30)
            if rows:
                pg_items = []
                for r in rows:
                    try:
                        pg_items.append(DataItem(
                            id=r["id"],
                            source=r["source"],
                            type=r["item_type"],
                            title=r["title"] or "",
                            content=r["content"] or "",
                            author=r["author"],
                            timestamp=r["timestamp"],
                            url=r.get("url"),
                            tags=list(r["tags"]) if r.get("tags") else [],
                            metadata={
                                "from_email": r.get("email", ""),
                                "thread_id": r.get("thread_id"),
                                "sentiment_label": r.get("sentiment_label"),
                                "sentiment_score": r.get("sentiment_score"),
                            },
                        ))
                    except Exception:
                        pass
                item_store.upsert(pg_items)
                print(f"[startup] {len(pg_items)} items chargés depuis PostgreSQL")
        finally:
            db.close()

    # ── 3. Sync connecteurs (nouveaux items) ─────────────────
    print("[startup] Sync connecteurs...")
    since = datetime.utcnow() - timedelta(days=30)
    results = await connector_manager.sync_all(since=since)
    new_items = connector_manager.collect_items(results)
    item_store.upsert(new_items)
    summary = connector_manager.summary(results)
    print(f"[startup] Sync : {summary['total_items']} items récupérés")

    # ── 4. ETL → écrire les nouveaux items dans PostgreSQL ───
    if db_ok and new_items:
        from etl.loader import load_items
        db = SessionLocal()
        try:
            n = load_items(new_items, db)
            print(f"[startup] ETL : {n} nouveaux items insérés en base")
        except Exception as e:
            print(f"[startup] ETL warning : {e}")
        finally:
            db.close()

    yield


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
app.include_router(sync.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(sources.router)
app.include_router(analytics.router)


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
