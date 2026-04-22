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
from core.models import SourceConfig, MessageRaw

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
        "available": False, "coming_soon": True, "category": "Communication"
    },
    "teams": {
        "name": "Teams", "icon": "💬", "color": "#6264A7",
        "auth_type": "oauth2", "description": "Messages Microsoft Teams",
        "available": False, "coming_soon": True, "category": "Communication"
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


def _load_jira_db_config() -> dict | None:
    """Load Jira credentials from source_configs table."""
    try:
        db = SessionLocal()
        try:
            row = db.query(SourceConfig).filter(SourceConfig.source == "jira").first()
            if row:
                cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
                return cfg
        finally:
            db.close()
    except Exception:
        pass
    return None


def _is_jira_connected() -> bool:
    if _load_jira_db_config():
        return True
    from core.config import settings
    return bool(settings.jira_base_url and settings.jira_api_token)


@router.get("/jira/status")
async def jira_status():
    """Retourne si Jira est connecté (DB ou .env)."""
    cfg = _load_jira_db_config()
    if cfg:
        return {"connected": True, "source": "db",
                "base_url": cfg.get("base_url"), "email": cfg.get("email")}
    from core.config import settings
    if settings.jira_base_url and settings.jira_api_token:
        return {"connected": True, "source": "env",
                "base_url": settings.jira_base_url, "email": settings.jira_email}
    return {"connected": False}


@router.post("/jira/connect")
async def connect_jira(body: JiraConnectRequest, background_tasks: BackgroundTasks):
    """
    Connecte Jira avec les credentials fournis par le CEO.
    1. Teste l'authentification
    2. Sauvegarde en DB
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
            user = resp.json()
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
        row = db.query(SourceConfig).filter(SourceConfig.source == "jira").first()
        if row:
            row.config = config
            row.connected_at = datetime.utcnow()
        else:
            db.add(SourceConfig(source="jira", config=config))
        db.commit()
    finally:
        db.close()

    # 3. Reset auth + sync en arrière-plan
    background_tasks.add_task(_background_jira_sync)

    return {"connected": True, "user": user.get("displayName"),
            "message": "Jira connecté — sync en cours en arrière-plan"}


async def _background_jira_sync():
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
                # Supprimer anciens items Jira et réinsérer
                db.query(MessageRaw).filter(MessageRaw.source == "jira").delete(synchronize_session=False)
                db.commit()
                load_items(fetched, db, run_nlp=False)
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
    except Exception as e:
        logging.getLogger(__name__).warning("[Jira] Background sync failed: %s", e)


@router.get("/status")
async def sources_status(store: Annotated[ItemStore, Depends(get_store)]):
    """Returns each source with connection status and item count."""
    SOURCE_TYPES = {
        "gmail":   SourceType.GMAIL,
        "slack":   SourceType.SLACK,
        "jira":    SourceType.JIRA,
        "clickup": SourceType.CLICKUP,
    }
    result = []
    for key, data in REGISTRY.items():
        source_type = SOURCE_TYPES.get(key)
        count = len(store.all(source=source_type, limit=10_000)) if source_type else 0
        last_sync = store.last_sync(source_type).isoformat() if (source_type and store.last_sync(source_type)) else None
        result.append({
            "key":        key,
            "name":       data["name"],
            "icon":       data["icon"],
            "color":      data["color"],
            "category":   data["category"],
            "available":  data["available"],
            "coming_soon": data.get("coming_soon", False),
            "connected":  count > 0,
            "items_count": count,
            "last_sync":  last_sync,
        })
    return result


# ── ClickUp Connection ────────────────────────────────────────────────────────

class ClickUpConnectRequest(BaseModel):
    api_token: str
    team_id:   str = ""    # optional: workspace/team ID


def _load_clickup_db_config() -> dict | None:
    try:
        db = SessionLocal()
        try:
            row = db.query(SourceConfig).filter(SourceConfig.source == "clickup").first()
            if row:
                return row.config if isinstance(row.config, dict) else json.loads(row.config)
        finally:
            db.close()
    except Exception:
        pass
    return None


@router.get("/clickup/status")
async def clickup_status():
    cfg = _load_clickup_db_config()
    if cfg and cfg.get("api_token"):
        return {"connected": True, "team_id": cfg.get("team_id", "")}
    return {"connected": False}


@router.post("/clickup/connect")
async def connect_clickup(body: ClickUpConnectRequest, background_tasks: BackgroundTasks):
    """Save ClickUp API token, verify it, then sync in background."""
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
            user = resp.json().get("user", {})
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
        row = db.query(SourceConfig).filter(SourceConfig.source == "clickup").first()
        if row:
            row.config = config
            row.connected_at = datetime.utcnow()
        else:
            db.add(SourceConfig(source="clickup", config=config))
        db.commit()
    finally:
        db.close()

    # 3. Background sync
    background_tasks.add_task(_background_clickup_sync)

    return {
        "connected": True,
        "user": user.get("username"),
        "message": "ClickUp connecté — sync en cours en arrière-plan",
    }


@router.delete("/clickup/disconnect", status_code=204)
async def disconnect_clickup():
    db = SessionLocal()
    try:
        db.query(SourceConfig).filter(SourceConfig.source == "clickup").delete()
        db.commit()
    finally:
        db.close()


async def _background_clickup_sync():
    import logging as _logging
    logger = _logging.getLogger(__name__)
    try:
        from application.deps import connector_manager, item_store
        from integrations.connectors import ConnectorManager
        from integrations.connectors.schemas import SourceType as ST
        from data.etl.loader import load_items, load_from_db
        from main import _build_data_item

        clickup = connector_manager._connectors.get(ST.CLICKUP)
        if clickup:
            clickup._authenticated = False

        since = datetime.utcnow() - timedelta(days=365)
        results = await connector_manager.sync_all(since=since, sources=[ST.CLICKUP])
        fetched = ConnectorManager.collect_items(results)
        item_store.upsert(fetched)

        if fetched:
            db = SessionLocal()
            try:
                db.query(MessageRaw).filter(MessageRaw.source == "clickup").delete(synchronize_session=False)
                db.commit()
                load_items(fetched, db, run_nlp=False)
                rows = load_from_db(db, since_days=365)
                refreshed = []
                for r in rows:
                    if r.get("source") == "clickup":
                        try:
                            refreshed.append(_build_data_item(r))
                        except Exception:
                            pass
                if refreshed:
                    item_store.upsert(refreshed)
                logger.info("[ClickUp] Sync post-connexion : %d items chargés", len(refreshed))
            finally:
                db.close()
    except Exception as e:
        logging.getLogger(__name__).warning("[ClickUp] Background sync failed: %s", e)
