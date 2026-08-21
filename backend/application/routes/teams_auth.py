"""
Microsoft Teams OAuth — InsightFlow Executive
=============================================
Azure app registration required with scopes:
  ChannelMessage.Read.All  Team.ReadBasic.All  Channel.ReadBasic.All  Chat.Read  offline_access

Set in .env:
  TEAMS_CLIENT_ID=...
  TEAMS_CLIENT_SECRET=...
  TEAMS_TENANT=common          # or your tenant ID / domain
  TEAMS_REDIRECT_URI=http://localhost:8000/auth/teams/callback
"""
import json
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import RedirectResponse

from core.config import settings
from core.database import SessionLocal
from core.models import SourceConfig, User
from core.security import get_current_user
from fastapi import Depends
import secrets

router = APIRouter(prefix="/auth/teams", tags=["teams"])

TEAMS_SCOPES = "ChannelMessage.Read.All Team.ReadBasic.All Channel.ReadBasic.All Chat.Read offline_access"
AUTH_BASE    = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
TOKEN_URL    = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# state → org_id
_oauth_states: dict[str, str | None] = {}


def _tenant() -> str:
    return settings.teams_tenant or "common"


# ── OAuth flow ────────────────────────────────────────────────────────────────

@router.get("/connect")
async def teams_connect(current_user: User = Depends(get_current_user)):
    """Redirect browser to Microsoft consent screen."""
    if not settings.teams_client_id:
        raise HTTPException(status_code=400, detail="Teams client_id not configured.")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = current_user.org_id
    params = {
        "client_id":     settings.teams_client_id,
        "response_type": "code",
        "redirect_uri":  settings.teams_redirect_uri,
        "scope":         TEAMS_SCOPES,
        "response_mode": "query",
        "state":         state,
        "prompt":        "select_account",
    }
    url = AUTH_BASE.format(tenant=_tenant()) + "?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/auth-url")
async def teams_auth_url(current_user: User = Depends(get_current_user)):
    """Frontend flow — returns the OAuth URL as JSON."""
    if not settings.teams_client_id:
        raise HTTPException(status_code=400, detail="Teams client_id not configured.")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = current_user.org_id
    params = {
        "client_id":     settings.teams_client_id,
        "response_type": "code",
        "redirect_uri":  settings.teams_redirect_uri,
        "scope":         TEAMS_SCOPES,
        "response_mode": "query",
        "state":         state,
        "prompt":        "select_account",
    }
    url = AUTH_BASE.format(tenant=_tenant()) + "?" + urlencode(params)
    return {"url": url}


@router.get("/callback")
async def teams_callback(
    background_tasks: BackgroundTasks = None,
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    error_description: str = Query(default=None),
):
    """Microsoft redirects here after consent."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error} — {error_description}")
    if not code:
        raise HTTPException(status_code=400, detail="Aucun code d'autorisation reçu.")

    org_id = _oauth_states.pop(state, None) if state else None

    token_url = TOKEN_URL.format(tenant=_tenant())
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data={
            "client_id":     settings.teams_client_id,
            "client_secret": settings.teams_client_secret,
            "code":          code,
            "redirect_uri":  settings.teams_redirect_uri,
            "grant_type":    "authorization_code",
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text[:300]}")
        tokens = resp.json()

    token_data = {
        "access_token":  tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_in":    tokens.get("expires_in", 3600),
        "refreshed_at":  datetime.utcnow().isoformat(),
    }
    _save_token(token_data, org_id)
    _enable_real_mode()

    if background_tasks:
        background_tasks.add_task(_background_teams_sync)

    return RedirectResponse(f"{settings.frontend_url}/onboarding?connected=teams", status_code=302)


@router.get("/status")
async def teams_status(current_user: User = Depends(get_current_user)):
    """Check whether Teams is authenticated for this org."""
    cfg = _load_token(current_user.org_id)
    if not cfg or not cfg.get("access_token"):
        return {"connected": False, "next_step": "GET /auth/teams/connect"}
    return {"connected": True, "refreshed_at": cfg.get("refreshed_at"), "mock_mode": False}


@router.delete("/disconnect", status_code=204)
async def teams_disconnect(current_user: User = Depends(get_current_user)):
    """Remove Teams token and switch back to mock mode."""
    db = SessionLocal()
    try:
        db.query(SourceConfig).filter(
            SourceConfig.source == "teams",
            SourceConfig.org_id == current_user.org_id,
        ).delete()
        db.commit()
    finally:
        db.close()
    _disable_real_mode()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_token(org_id: str | None = None) -> dict | None:
    try:
        db = SessionLocal()
        try:
            q = db.query(SourceConfig).filter(SourceConfig.source == "teams")
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


def _save_token(token_data: dict, org_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        q = db.query(SourceConfig).filter(SourceConfig.source == "teams")
        if org_id is not None:
            q = q.filter(SourceConfig.org_id == org_id)
        row = q.first()
        if row:
            row.config = token_data
        else:
            db.add(SourceConfig(org_id=org_id, source="teams", config=token_data))
        db.commit()
    finally:
        db.close()


def _enable_real_mode() -> None:
    try:
        from application.deps import connector_manager
        from integrations.connectors.schemas import SourceType
        connector = connector_manager._connectors.get(SourceType.TEAMS)
        if connector:
            connector.config["use_mock"] = False
            connector._authenticated = False
    except Exception:
        pass


def _disable_real_mode() -> None:
    try:
        from application.deps import connector_manager
        from integrations.connectors.schemas import SourceType
        connector = connector_manager._connectors.get(SourceType.TEAMS)
        if connector:
            connector.config["use_mock"] = True
            connector._authenticated = False
    except Exception:
        pass


async def _background_teams_sync() -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        from application.deps import connector_manager, item_store
        from integrations.connectors import ConnectorManager
        from integrations.connectors.schemas import SourceType
        from data.etl.loader import load_items, load_from_db
        from main import _build_data_item
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(days=30)
        results = await connector_manager.sync_all(since=since, sources=[SourceType.TEAMS])
        fetched = ConnectorManager.collect_items(results)
        item_store.upsert(fetched)

        if fetched:
            from core.database import SessionLocal
            from core.models import MessageRaw
            db = SessionLocal()
            try:
                db.query(MessageRaw).filter(MessageRaw.source == "teams").delete(synchronize_session=False)
                db.commit()
                load_items(fetched, db, run_nlp=False)
                rows = load_from_db(db, since_days=30)
                refreshed = []
                for r in rows:
                    if r.get("source") == "teams":
                        try:
                            refreshed.append(_build_data_item(r))
                        except Exception:
                            pass
                if refreshed:
                    item_store.upsert(refreshed)
                logger.info("[Teams] Background sync: %d items loaded", len(refreshed))
            finally:
                db.close()

        if fetched:
            import asyncio
            from data.etl.loader import reprocess_unenriched
            from core.database import SessionLocal as _SL
            db2 = _SL()
            try:
                n_nlp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: reprocess_unenriched(db2, limit=len(fetched) + 20)
                )
                logger.info("[Teams] NLP enrichissement : %d items", n_nlp)
            except Exception as nlp_err:
                logger.warning("[Teams] NLP ignoré : %s", nlp_err)
            finally:
                db2.close()

    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).warning("[Teams] Background sync failed: %s", e)
