import json
import logging
from datetime import datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from integrations.connectors.schemas import SourceType
from core.database import SessionLocal, get_db
from core.store import ItemStore
from application.deps import get_store
from core.models import ConnectorCatalog, SourceConfig, MessageRaw, User
from core.security import get_current_user

router = APIRouter(prefix="/api/sources", tags=["sources"])


class Source(BaseModel):
    key: str
    name: str
    icon: str
    color: str
    auth_type: str
    description: str
    available: bool
    coming_soon: bool = False
    auto_connected: bool = False
    category: str


REGISTRY: dict[str, dict] = {
    "gmail": {
        "name": "Gmail", "icon": "📧", "color": "#EA4335",
        "auth_type": "oauth2", "description": "Emails Google",
        "available": True, "coming_soon": False, "category": "Communication"
    },
    "outlook": {
        "name": "Outlook", "icon": "📨", "color": "#0078D4",
        "auth_type": "oauth2", "description": "Emails Microsoft",
        "available": True, "coming_soon": False, "category": "Communication"
    },
    "teams": {
        "name": "Teams", "icon": "💬", "color": "#6264A7",
        "auth_type": "oauth2", "description": "Messages Microsoft Teams",
        "available": True, "coming_soon": False, "category": "Communication"
    },
    "slack": {
        "name": "Slack", "icon": "💼", "color": "#4A154B",
        "auth_type": "bot", "description": "Canaux du workspace connectés",
        "available": False, "coming_soon": False, "auto_connected": True, "category": "Communication"
    },
    "jira": {
        "name": "Jira", "icon": "🎫", "color": "#0052CC",
        "auth_type": "api_key", "description": "Tickets & Projets",
        "available": True, "coming_soon": False, "auto_connected": False, "category": "Projets"
    },
    "clickup": {
        "name": "ClickUp", "icon": "✅", "color": "#7B68EE",
        "auth_type": "api_key", "description": "Gestion de tâches",
        "available": True, "coming_soon": False, "auto_connected": False, "category": "Projets"
    },
    "notion": {
        "name": "Notion", "icon": "📓", "color": "#ffffff",
        "auth_type": "api_key", "description": "Documentation & Notes",
        "available": False, "coming_soon": True, "category": "Projets"
    },
    "google_calendar": {
        "name": "Google Calendar", "icon": "📅", "color": "#4285F4",
        "auth_type": "oauth2", "description": "Agenda & Réunions",
        "available": False, "coming_soon": True, "category": "Agenda"
    },
    "salesforce": {
        "name": "Salesforce", "icon": "☁️", "color": "#00A1E0",
        "auth_type": "oauth2", "description": "CRM & Ventes",
        "available": False, "coming_soon": True, "category": "CRM"
    },
    "trello": {
        "name": "Trello", "icon": "📋", "color": "#0052CC",
        "auth_type": "api_key", "description": "Boards visuels",
        "available": False, "coming_soon": True, "category": "Projets"
    },
    "hubspot": {
        "name": "HubSpot", "icon": "🟠", "color": "#FF7A59",
        "auth_type": "oauth2", "description": "Marketing & CRM",
        "available": False, "coming_soon": True, "category": "CRM"
    },
    "github": {
        "name": "GitHub", "icon": "🐙", "color": "#333333",
        "auth_type": "oauth2", "description": "Code & Pull Requests",
        "available": False, "coming_soon": True, "category": "Dev"
    },
}


def get_sources_by_category() -> dict[str, list[Source]]:
    categories: dict[str, list[Source]] = {}
    for key, data in REGISTRY.items():
        cat = data["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(Source(key=key, **data))
    return categories


@router.get("/categories")
async def sources_by_category() -> dict[str, list[Source]]:
    return get_sources_by_category()


# ── Jira Connection ───────────────────────────────────────────

class JiraConnectRequest(BaseModel):
    base_url:     str
    email:        str
    api_token:    str
    project_keys: str = "SCRUM"


def _load_jira_db_config(org_id: str | None = None) -> dict | None:
    """Load Jira credentials from source_configs table, scoped to org."""
    try:
        db = SessionLocal()
        try:
            q = db.query(SourceConfig).filter(SourceConfig.source == "jira")
            if org_id is not None:
                q = q.filter(SourceConfig.org_id == org_id)
            row = q.first()
            if row:
                return row.config if isinstance(row.config, dict) else json.loads(row.config)
        finally:
            db.close()
    except Exception:
        pass
    return None


def _is_jira_connected(org_id: str | None = None) -> bool:
    if _load_jira_db_config(org_id):
        return True
    if org_id is not None:
        return False
    from core.config import settings
    return bool(settings.jira_base_url and settings.jira_api_token)


@router.get("/jira/status")
async def jira_status(current_user: User = Depends(get_current_user)):
    """Retourne si Jira est connecté — scoped à l'org."""
    cfg = _load_jira_db_config(current_user.org_id)
    if cfg:
        return {"connected": True, "source": "db",
                "base_url": cfg.get("base_url"), "email": cfg.get("email")}
    return {"connected": False}


@router.post("/jira/connect")
async def connect_jira(
    body: JiraConnectRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Connecte Jira avec les credentials fournis par le CEO.
    1. Teste l'authentification
    2. Sauvegarde en DB (lié à l'org)
    3. Lance un sync en arrière-plan
    """
    base_url = body.base_url.rstrip("/")

    # 1. Tester les credentials
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url}/rest/api/3/myself",
                auth=(body.email, body.api_token),
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            jira_user = resp.json()
    except Exception as e:
        raise HTTPException(status_code=400,
                            detail=f"Impossible de se connecter à Jira : {e}")

    # 2. Sauvegarder en DB
    config = {
        "base_url":     base_url,
        "email":        body.email,
        "api_token":    body.api_token,
        "project_keys": [k.strip() for k in body.project_keys.split(",") if k.strip()],
    }
    db = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(
            SourceConfig.source == "jira",
            SourceConfig.org_id == current_user.org_id,
        ).first()
        if row:
            row.config = config
            row.connected_at = datetime.utcnow()
        else:
            db.add(SourceConfig(org_id=current_user.org_id, source="jira", config=config))
        db.commit()
    finally:
        db.close()

    background_tasks.add_task(_background_jira_sync, current_user.org_id)

    return {"connected": True, "user": jira_user.get("displayName"),
            "message": "Jira connecté — sync en cours en arrière-plan"}


async def _background_jira_sync(org_id: str | None = None):
    """Resync Jira après une nouvelle connexion."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from application.deps import connector_manager, item_store
        from integrations.connectors import ConnectorManager
        from data.etl.loader import load_items, load_from_db
        from main import _build_data_item

        # Reset auth pour forcer re-authentification avec les nouveaux credentials
        jira = connector_manager._connectors.get(SourceType.JIRA)
        if jira:
            jira._authenticated = False

        since = datetime.utcnow() - timedelta(days=365)
        results = await connector_manager.sync_all(since=since, sources=[SourceType.JIRA])
        fetched = ConnectorManager.collect_items(results)
        item_store.upsert(fetched)

        if fetched:
            db = SessionLocal()
            try:
                # Supprimer anciens items Jira de cette org et réinsérer
                q = db.query(MessageRaw).filter(MessageRaw.source == "jira")
                if org_id:
                    q = q.filter(MessageRaw.org_id == org_id)
                q.delete(synchronize_session=False)
                db.commit()
                load_items(fetched, db, run_nlp=False, org_id=org_id)
                rows = load_from_db(db, since_days=365)
                refreshed = []
                for r in rows:
                    if r.get("source") == "jira":
                        try:
                            refreshed.append(_build_data_item(r))
                        except Exception:
                            pass
                if refreshed:
                    item_store.upsert(refreshed)
                logger.info("[Jira] Sync post-connexion : %d items chargés", len(refreshed))
            finally:
                db.close()

        # NLP enrichissement après insertion
        if fetched:
            import asyncio
            from data.etl.loader import reprocess_unenriched
            db2 = SessionLocal()
            try:
                print(f"[jira-sync] Lancement NLP enrichissement…")
                n_nlp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: reprocess_unenriched(db2, limit=len(fetched) + 20)
                )
                print(f"[jira-sync] NLP terminé : {n_nlp} items enrichis")
            except Exception as nlp_err:
                print(f"[jira-sync] NLP ignoré : {nlp_err}")
            finally:
                db2.close()

    except Exception as e:
        logging.getLogger(__name__).warning("[Jira] Background sync failed: %s", e)


@router.get("/status")
async def sources_status(
    current_user: User = Depends(get_current_user),
    store=Depends(get_store),
):
    """Returns each source with connection status and item count.
    Availability and coming_soon flags come from the ConnectorCatalog (managed by superadmin).
    connected = True if credentials exist in source_configs OR items are already synced.
    """
    SOURCE_TYPES = {
        "gmail":   SourceType.GMAIL,
        "slack":   SourceType.SLACK,
        "jira":    SourceType.JIRA,
        "clickup": SourceType.CLICKUP,
        "teams":   SourceType.TEAMS,
        "outlook": SourceType.OUTLOOK,
    }

    # Load catalog flags from DB
    catalog: dict[str, ConnectorCatalog] = {}
    try:
        db = SessionLocal()
        try:
            catalog = {c.key: c for c in db.query(ConnectorCatalog).all()}
        finally:
            db.close()
    except Exception:
        pass

    # Load configured sources — isolated so ConnectorCatalog failure can't break this
    configured_sources: set[str] = set()
    try:
        db = SessionLocal()
        try:
            rows = db.query(SourceConfig.source).filter(
                SourceConfig.org_id == current_user.org_id
            ).all()
            configured_sources = {r.source for r in rows}
        finally:
            db.close()
    except Exception:
        pass

    result = []
    for key, data in REGISTRY.items():
        cat_entry = catalog.get(key)
        available   = (cat_entry.enabled and not cat_entry.coming_soon) if cat_entry else data["available"]
        coming_soon = cat_entry.coming_soon if cat_entry else data.get("coming_soon", False)

        source_type = SOURCE_TYPES.get(key)
        count     = store.count_source(source_type) if (source_type and hasattr(store, "count_source")) else (
                    len(store.all(source=source_type, limit=10_000)) if source_type else 0
                )
        last_sync = store.last_sync(source_type).isoformat() if (source_type and store.last_sync(source_type)) else None

        # For Gmail: check actual OAuth token validity, not just DB items
        if key == "gmail":
            from application.routes.auth import get_gmail_credentials
            creds = get_gmail_credentials(current_user.org_id)
            connected    = creds is not None and creds.valid
            sync_pending = False
        else:
            connected    = (key in configured_sources) or (count > 0)
            sync_pending = (key in configured_sources) and (count == 0)

        result.append({
            "key":          key,
            "name":         cat_entry.name if cat_entry else data["name"],
            "icon":         data["icon"],
            "color":        data["color"],
            "category":     cat_entry.category if cat_entry else data["category"],
            "available":    available,
            "coming_soon":  coming_soon,
            "connected":    connected,
            "sync_pending": sync_pending,
            "items_count":  count,
            "last_sync":    last_sync,
        })
    return result


# ── Gmail sync status ─────────────────────────────────────────────────────────

@router.get("/gmail/status")
async def gmail_sync_status(
    current_user: User = Depends(get_current_user),
    store=Depends(get_store),
):
    """Returns Gmail connection + sync status for this org."""
    from application.routes.auth import get_gmail_credentials
    creds = get_gmail_credentials(current_user.org_id)
    connected = creds is not None and creds.valid
    count = store.count_source(SourceType.GMAIL) if hasattr(store, "count_source") else 0
    return {
        "connected":    connected,
        "sync_pending": connected and count == 0,
        "items_count":  count,
    }


# ── ClickUp Connection ────────────────────────────────────────────────────────

class ClickUpConnectRequest(BaseModel):
    api_token: str
    team_id:   str = ""    # optional: workspace/team ID


def _load_clickup_db_config(org_id: str | None = None) -> dict | None:
    try:
        db = SessionLocal()
        try:
            q = db.query(SourceConfig).filter(SourceConfig.source == "clickup")
            if org_id is not None:
                q = q.filter(SourceConfig.org_id == org_id)
            row = q.first()
            if row:
                return row.config if isinstance(row.config, dict) else json.loads(row.config)
        finally:
            db.close()
    except Exception:
        pass
    return None


@router.get("/clickup/status")
async def clickup_status(current_user: User = Depends(get_current_user)):
    cfg = _load_clickup_db_config(current_user.org_id)
    if cfg and cfg.get("api_token"):
        return {"connected": True, "team_id": cfg.get("team_id", "")}
    return {"connected": False}


@router.post("/clickup/connect")
async def connect_clickup(
    body: ClickUpConnectRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Save ClickUp API token (lié à l'org), verify it, then sync in background."""
    import httpx as _httpx

    # 1. Verify token
    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.clickup.com/api/v2/user",
                headers={"Authorization": body.api_token},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"ClickUp token invalide: {resp.text}")
            cu_user = resp.json().get("user", {})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de se connecter à ClickUp : {e}")

    # 2. Save config
    config: dict = {"api_token": body.api_token}
    if body.team_id:
        config["team_id"] = body.team_id

    db = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(
            SourceConfig.source == "clickup",
            SourceConfig.org_id == current_user.org_id,
        ).first()
        if row:
            row.config = config
            row.connected_at = datetime.utcnow()
        else:
            db.add(SourceConfig(org_id=current_user.org_id, source="clickup", config=config))
        db.commit()
    finally:
        db.close()

    background_tasks.add_task(_background_clickup_sync, current_user.org_id)

    return {
        "connected": True,
        "user": cu_user.get("username"),
        "message": "ClickUp connecté — sync en cours en arrière-plan",
    }


@router.delete("/clickup/disconnect", status_code=204)
async def disconnect_clickup(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        db.query(SourceConfig).filter(
            SourceConfig.source == "clickup",
            SourceConfig.org_id == current_user.org_id,
        ).delete()
        db.commit()
    finally:
        db.close()


async def _background_clickup_sync(org_id: str | None = None):
    """Sync ClickUp directement avec les credentials de l'org — bypass connector_manager."""
    try:
        from integrations.connectors.clickup import ClickUpConnector
        from data.etl.loader import load_items

        # Charger la config depuis source_configs pour cet org
        cfg: dict = {}
        db0 = SessionLocal()
        try:
            row = db0.query(SourceConfig).filter(
                SourceConfig.source == "clickup",
                SourceConfig.org_id == org_id,
            ).first()
            if row:
                cfg = row.config if isinstance(row.config, dict) else {}
        finally:
            db0.close()

        if not cfg.get("api_token"):
            print(f"[clickup-sync] Pas de credentials pour org={org_id}")
            return

        print(f"[clickup-sync] Démarrage pour org={org_id}")
        connector = ClickUpConnector({**cfg, "org_id": org_id})
        await connector.authenticate()

        since = datetime.utcnow() - timedelta(days=90)
        raw_items = await connector.fetch_raw(since)
        print(f"[clickup-sync] {len(raw_items)} tâches trouvées")

        items = [connector.normalize(r) for r in raw_items]

        # Scoper les IDs par org pour éviter les conflits multi-tenant
        if org_id:
            items = [i.model_copy(update={"id": f"{i.id}_{org_id[:8]}"}) for i in items]

        if not items:
            print(f"[clickup-sync] Aucun item pour org={org_id}")
            return

        db = SessionLocal()
        try:
            n = load_items(items, db, run_nlp=False, org_id=org_id, index_rag=False)
            print(f"[clickup-sync] {n} nouveaux items insérés pour org={org_id}")
        finally:
            db.close()

        # NLP enrichissement immédiat après insertion
        if items:
            import asyncio
            from data.etl.loader import reprocess_unenriched
            db2 = SessionLocal()
            try:
                print(f"[clickup-sync] Lancement NLP enrichissement pour org={org_id}…")
                enriched = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: reprocess_unenriched(db2, limit=len(items) + 20)
                )
                print(f"[clickup-sync] NLP terminé : {enriched} items enrichis")
            except Exception as nlp_err:
                print(f"[clickup-sync] NLP ignoré : {nlp_err}")
            finally:
                db2.close()

    except Exception as e:
        print(f"[clickup-sync] ERREUR (org={org_id}): {e}")


# ── Teams ─────────────────────────────────────────────────────────────────────

@router.get("/teams/status")
async def teams_status(current_user: User = Depends(get_current_user)):
    """Check whether Teams is authenticated (real or mock mode)."""
    try:
        db = SessionLocal()
        try:
            row = db.query(SourceConfig).filter(
                SourceConfig.source == "teams",
                SourceConfig.org_id == current_user.org_id,
            ).first()
            if row:
                cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
                return {
                    "connected": True,
                    "mode": "real",
                    "refreshed_at": cfg.get("refreshed_at"),
                    "connect_url": "/auth/teams/connect",
                }
        finally:
            db.close()
    except Exception:
        pass
    return {
        "connected": False,
        "mode": "mock",
        "message": "Mock data active. Configure TEAMS_CLIENT_ID in .env and visit /auth/teams/connect to use real data.",
        "connect_url": "/auth/teams/connect",
    }


@router.post("/teams/sync")
async def teams_sync(background_tasks: BackgroundTasks):
    """Trigger a Teams sync (uses mock or real depending on auth state)."""
    from application.routes.teams_auth import _background_teams_sync
    background_tasks.add_task(_background_teams_sync)
    return {"message": "Teams sync triggered in background"}


# ── Outlook ───────────────────────────────────────────────────────────────────

@router.get("/outlook/status")
async def outlook_status(current_user: User = Depends(get_current_user)):
    try:
        db = SessionLocal()
        try:
            row = db.query(SourceConfig).filter(
                SourceConfig.source == "outlook",
                SourceConfig.org_id == current_user.org_id,
            ).first()
            if row:
                cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
                return {"connected": True, "refreshed_at": cfg.get("refreshed_at"), "connect_url": "/auth/outlook/connect"}
        finally:
            db.close()
    except Exception:
        pass
    return {"connected": False, "connect_url": "/auth/outlook/connect"}


@router.post("/outlook/sync")
async def outlook_sync(background_tasks: BackgroundTasks):
    from application.routes.outlook_auth import _background_outlook_sync
    background_tasks.add_task(_background_outlook_sync)
    return {"message": "Outlook sync triggered in background"}


@router.delete("/outlook/disconnect", status_code=204)
async def outlook_disconnect_source(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        db.query(SourceConfig).filter(
            SourceConfig.source == "outlook",
            SourceConfig.org_id == current_user.org_id,
        ).delete()
        db.commit()
    finally:
        db.close()
    try:
        from application.deps import connector_manager
        connector = connector_manager._connectors.get(SourceType.OUTLOOK)
        if connector:
            connector._authenticated = False
    except Exception:
        pass


@router.delete("/teams/disconnect", status_code=204)
async def teams_disconnect_source(current_user: User = Depends(get_current_user)):
    """Remove Teams token from DB and switch to mock mode."""
    db = SessionLocal()
    try:
        db.query(SourceConfig).filter(
            SourceConfig.source == "teams",
            SourceConfig.org_id == current_user.org_id,
        ).delete()
        db.commit()
    finally:
        db.close()
    try:
        from application.deps import connector_manager
        from integrations.connectors.schemas import SourceType as ST
        connector = connector_manager._connectors.get(ST.TEAMS)
        if connector:
            connector.config["use_mock"] = True
            connector._authenticated = False
    except Exception:
        pass
