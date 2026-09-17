import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.routes import sync, items, auth, sources, analytics, actions, brief, search, ml, ask, emails, projects, onedrive, decisions, orchestration, mcp, anomaly, health, teams_auth, outlook_auth, slack_auth, calendar as calendar_route, recommendations
from application.routes import websocket as ws_route, webhooks as webhooks_route, users as users_route
from application.routes import admin as admin_route
from application.routes import demo_requests as demo_requests_route
from application.deps import connector_manager, item_store
from core.database import init_db, SessionLocal
from core.config import settings
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


async def _realtime_sync_loop():
    """
    Auto-sync every AUTO_SYNC_INTERVAL seconds and broadcast results via WebSocket.
    Runs as a background asyncio task for the lifetime of the server.

    Syncs per-organisation: builds one fresh, org-scoped ConnectorManager per org
    that has real configured sources (from source_configs), restricted to those
    sources with use_mock=False. NEVER uses the global `connector_manager` — that
    singleton has no org_id and Teams/Outlook default to mock data when
    unconfigured, so using it here used to attribute mock messages (and whichever
    org's Gmail happened to be found first) to the wrong organisation.

    Slack is excluded — it has its own dedicated loop (see
    application/routes/slack_auth.py:periodic_slack_sync_loop), so it isn't
    double-synced here.
    """
    from core.ws_manager import ws_manager
    from core.models import SourceConfig as _SC
    from integrations.connectors import ConnectorManager as CM

    interval = settings.auto_sync_interval
    await asyncio.sleep(45)  # let server fully start first
    print(f"[realtime] Auto-sync loop started — interval={interval}s")
    while True:
        try:
            await ws_manager.broadcast({
                "type": "sync_started",
                "timestamp": datetime.utcnow().isoformat(),
            })
            since = datetime.utcnow() - timedelta(minutes=15)

            db = SessionLocal()
            try:
                rows = db.query(_SC.org_id, _SC.source).filter(
                    _SC.org_id.isnot(None), _SC.source != "slack",
                ).distinct().all()
            finally:
                db.close()

            by_org: dict[str, set[str]] = {}
            for org_id, source in rows:
                by_org.setdefault(org_id, set()).add(source)

            new_count = 0
            sources_summary: dict[str, dict] = {}

            for org_id, sources in by_org.items():
                targets = [SourceType(s) for s in sources if s in SourceType._value2member_map_]
                if not targets:
                    continue

                org_manager = CM(configs={
                    s: {"org_id": org_id, "use_mock": False} for s in targets
                })
                results = await org_manager.sync_all(since=since, sources=targets)
                new_items = CM.collect_items(results)

                for r in results:
                    info = sources_summary.setdefault(r.source.value, {"items": 0, "success": True})
                    info["items"] += len(r.items)
                    info["success"] = info["success"] and r.success

                if not new_items:
                    continue

                item_store.upsert(new_items)
                try:
                    from data.etl.loader import load_items
                    db2 = SessionLocal()
                    try:
                        new_count += load_items(new_items, db2, run_nlp=False, org_id=org_id)
                    finally:
                        db2.close()
                except Exception as etl_err:
                    print(f"[realtime] ETL error (org={org_id}): {etl_err}")

                # Broadcast urgent notifications — scoped to this org only
                for item in new_items:
                    meta = item.metadata or {}
                    if (meta.get("sentiment_label") in ("negative", "very_negative")
                            or meta.get("business_label") in ("escalation", "urgent", "crisis")):
                        await ws_manager.broadcast({
                            "type": "notification",
                            "level": "critical",
                            "source": item.source.value,
                            "message": f"Message urgent de {item.author} : {item.title[:70]}",
                            "item_id": item.id,
                            "timestamp": datetime.utcnow().isoformat(),
                        }, org_id=org_id)

            # Ne notifier le frontend que s'il y a vraiment du nouveau —
            # sinon chaque cycle (même vide) déclenche un rechargement
            # complet du dashboard côté client pour rien.
            if new_count > 0:
                await ws_manager.broadcast({
                    "type": "sync_complete",
                    "new_items": new_count,
                    "timestamp": datetime.utcnow().isoformat(),
                    "sources": sources_summary,
                })

        except asyncio.CancelledError:
            print("[realtime] Auto-sync loop stopped")
            return
        except Exception as e:
            print(f"[realtime] Sync error: {e}")

        await asyncio.sleep(interval)


async def _background_sync():
    """
    Sync + ETL + NLP en arrière-plan après démarrage du serveur (fallback si Celery
    indisponible). Sync par organisation — jamais via le connector_manager global
    (org-unaware, Teams/Outlook retombent en mock sans org_id) — même correctif
    que _realtime_sync_loop. Slack exclu : sync déjà géré par son propre flux
    (connexion OAuth + periodic_slack_sync_loop).
    """
    print("[bg-sync] Démarrage du sync en arrière-plan...")
    try:
        from core.models import SourceConfig as _SC
        from integrations.connectors import ConnectorManager as _CM

        since = datetime.utcnow() - timedelta(days=90)

        db0 = SessionLocal()
        try:
            rows = db0.query(_SC.org_id, _SC.source).filter(
                _SC.org_id.isnot(None), _SC.source != "slack",
            ).distinct().all()
        finally:
            db0.close()

        by_org: dict[str, set[str]] = {}
        for org_id, source in rows:
            by_org.setdefault(org_id, set()).add(source)

        new_items: list = []
        total_inserted = 0
        for org_id, sources in by_org.items():
            targets = [SourceType(s) for s in sources if s in SourceType._value2member_map_]
            if not targets:
                continue
            org_manager = _CM(configs={s: {"org_id": org_id, "use_mock": False} for s in targets})
            results = await org_manager.sync_all(since=since, sources=targets)
            org_items = _CM.collect_items(results)
            new_items.extend(org_items)
            print(f"[bg-sync] org={org_id} : {sum(len(r.items) for r in results)} items récupérés")

            if org_items:
                from data.etl.loader import load_items
                db = SessionLocal()
                try:
                    total_inserted += load_items(org_items, db, org_id=org_id)
                finally:
                    db.close()

        item_store.upsert(new_items)
        print(f"[bg-sync] ETL : {total_inserted} nouveaux items insérés en base")

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

    # ── 1b. Migrer les lignes legacy (org_id NULL) vers l'org de sarahhafsi ──
    if db_ok:
        try:
            from core.models import User, MessageRaw, ActionItem, DecisionLog, AnomalyEvent
            db = SessionLocal()
            try:
                # Chercher d'abord par email du .env (données issues de ses credentials)
                owner = (
                    db.query(User)
                    .filter(User.email == settings.jira_email)  # email configuré dans .env
                    .first()
                ) if settings.jira_email else None
                # Sinon, prendre le CEO avec le plus de messages existants
                if not owner or not owner.org_id:
                    from sqlalchemy import func
                    result = (
                        db.query(MessageRaw.org_id, func.count(MessageRaw.id).label("n"))
                        .filter(MessageRaw.org_id.isnot(None))
                        .group_by(MessageRaw.org_id)
                        .order_by(func.count(MessageRaw.id).desc())
                        .first()
                    )
                    if result:
                        owner = db.query(User).filter(User.org_id == result.org_id).first()
                if owner and owner.org_id:
                    oid = owner.org_id
                    for Model in [MessageRaw, ActionItem, DecisionLog, AnomalyEvent]:
                        count = db.query(Model).filter(Model.org_id.is_(None)).count()
                        if count > 0:
                            db.query(Model).filter(Model.org_id.is_(None)).update(
                                {"org_id": oid}, synchronize_session=False
                            )
                            print(f"[startup] Migration: {count} lignes {Model.__tablename__} → org {oid} ({owner.email})")
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[startup] Migration org_id ignorée: {e}")

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

    # ── 2b. Teams mock sync (synchrone, rapide — toujours disponible) ───
    try:
        teams_results = await connector_manager.sync_all(
            since=datetime.utcnow() - timedelta(days=90),
            sources=[SourceType.TEAMS],
        )
        teams_items = connector_manager.collect_items(teams_results)
        if teams_items:
            item_store.upsert(teams_items)
            from data.etl.loader import load_items
            from core.models import User as _User
            db_t = SessionLocal()
            try:
                first_ceo = (
                    db_t.query(_User)
                    .filter(_User.role.in_(["ceo", "admin"]))
                    .order_by(_User.created_at)
                    .first()
                )
                _org = first_ceo.org_id if first_ceo else None
                load_items(teams_items, db_t, run_nlp=False, org_id=_org)
            finally:
                db_t.close()
            print(f"[startup] Teams mock: {len(teams_items)} messages chargés")
    except Exception as e:
        print(f"[startup] Teams mock ignoré: {e}")

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

    # ── 5. Démarrer la boucle de sync temps réel ──────────────
    sync_task = asyncio.create_task(_realtime_sync_loop())

    # ── 6. Resync périodique par organisation (Slack) ─────────
    from application.routes.slack_auth import periodic_slack_sync_loop
    slack_sync_task = asyncio.create_task(periodic_slack_sync_loop())

    # ── 7. Démarrer les serveurs MCP une fois pour toutes (Ask Anything) ──
    # Évite de relancer un sous-processus Python par tool call — c'était le
    # principal goulot d'étranglement des réponses du chatbot.
    if settings.llm_provider.lower() == "azure":
        from intelligence.llm.client import start_mcp_sessions
        try:
            await start_mcp_sessions()
        except Exception as e:
            print(f"[startup] Démarrage MCP échoué (fallback sans tools): {e}")

    yield

    # ── Arrêt propre ──────────────────────────────────────────
    sync_task.cancel()
    slack_sync_task.cancel()
    stop_scheduler()

    if settings.llm_provider.lower() == "azure":
        from intelligence.llm.client import close_mcp_sessions
        await close_mcp_sessions()


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
app.include_router(teams_auth.router)
app.include_router(outlook_auth.router)
app.include_router(slack_auth.router)
app.include_router(decisions.router, prefix="/api")
app.include_router(orchestration.router)
app.include_router(mcp.router)
app.include_router(anomaly.router, prefix="/api")
app.include_router(health.router)
app.include_router(calendar_route.router)
app.include_router(ws_route.router)
app.include_router(webhooks_route.router)
app.include_router(users_route.router)
app.include_router(admin_route.router, prefix="/api")
app.include_router(demo_requests_route.router)
app.include_router(recommendations.router)


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
