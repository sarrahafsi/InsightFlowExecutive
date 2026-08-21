"""
Microsoft Outlook OAuth — InsightFlow Executive
================================================
Reuses the same Azure App Registration as Teams.
Add these to .env:
  OUTLOOK_CLIENT_ID=...       (can be same as TEAMS_CLIENT_ID)
  OUTLOOK_CLIENT_SECRET=...   (can be same as TEAMS_CLIENT_SECRET)
  OUTLOOK_TENANT=common
  OUTLOOK_REDIRECT_URI=http://localhost:8000/auth/outlook/callback

Add Mail.Read permission to the Azure App and add the new Redirect URI.
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

router = APIRouter(prefix="/auth/outlook", tags=["outlook"])

OUTLOOK_SCOPES = "Mail.Read Calendars.Read offline_access"
AUTH_BASE      = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
TOKEN_URL      = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# state → org_id
_oauth_states: dict[str, str | None] = {}


def _tenant() -> str:
    return settings.outlook_tenant or "common"


@router.get("/connect")
async def outlook_connect(current_user: User = Depends(get_current_user)):
    """Redirect browser to Microsoft consent screen."""
    if not settings.outlook_client_id:
        raise HTTPException(status_code=400, detail="OUTLOOK_CLIENT_ID not configured in .env")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = current_user.org_id
    params = {
        "client_id":     settings.outlook_client_id,
        "response_type": "code",
        "redirect_uri":  settings.outlook_redirect_uri,
        "scope":         OUTLOOK_SCOPES,
        "response_mode": "query",
        "state":         state,
        "prompt":        "select_account",
    }
    url = AUTH_BASE.format(tenant=_tenant()) + "?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/auth-url")
async def outlook_auth_url(current_user: User = Depends(get_current_user)):
    """Frontend flow — returns the OAuth URL as JSON."""
    if not settings.outlook_client_id:
        raise HTTPException(status_code=400, detail="OUTLOOK_CLIENT_ID not configured in .env")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = current_user.org_id
    params = {
        "client_id":     settings.outlook_client_id,
        "response_type": "code",
        "redirect_uri":  settings.outlook_redirect_uri,
        "scope":         OUTLOOK_SCOPES,
        "response_mode": "query",
        "state":         state,
        "prompt":        "select_account",
    }
    url = AUTH_BASE.format(tenant=_tenant()) + "?" + urlencode(params)
    return {"url": url}


@router.get("/callback")
async def outlook_callback(
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
        raise HTTPException(status_code=400, detail="Aucun code reçu.")

    org_id = _oauth_states.pop(state, None) if state else None

    token_url = TOKEN_URL.format(tenant=_tenant())
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data={
            "client_id":     settings.outlook_client_id,
            "client_secret": settings.outlook_client_secret,
            "code":          code,
            "redirect_uri":  settings.outlook_redirect_uri,
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

    if background_tasks:
        background_tasks.add_task(_background_outlook_sync)

    return RedirectResponse(f"{settings.frontend_url}/onboarding?connected=outlook", status_code=302)


@router.get("/status")
async def outlook_status(current_user: User = Depends(get_current_user)):
    cfg = _load_token(current_user.org_id)
    if not cfg or not cfg.get("access_token"):
        return {"connected": False, "next_step": "GET /auth/outlook/connect"}
    return {"connected": True, "refreshed_at": cfg.get("refreshed_at")}


@router.delete("/disconnect", status_code=204)
async def outlook_disconnect(current_user: User = Depends(get_current_user)):
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
        from integrations.connectors.schemas import SourceType
        connector = connector_manager._connectors.get(SourceType.OUTLOOK)
        if connector:
            connector._authenticated = False
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_token(org_id: str | None = None) -> dict | None:
    try:
        db = SessionLocal()
        try:
            q = db.query(SourceConfig).filter(SourceConfig.source == "outlook")
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
        q = db.query(SourceConfig).filter(SourceConfig.source == "outlook")
        if org_id is not None:
            q = q.filter(SourceConfig.org_id == org_id)
        row = q.first()
        if row:
            row.config = token_data
        else:
            db.add(SourceConfig(org_id=org_id, source="outlook", config=token_data))
        db.commit()
    finally:
        db.close()


async def _background_outlook_sync() -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        from application.deps import connector_manager, item_store
        from integrations.connectors import ConnectorManager
        from integrations.connectors.schemas import SourceType
        from data.etl.loader import load_items, load_from_db
        from main import _build_data_item
        from datetime import timedelta
        from core.database import SessionLocal
        from core.models import MessageRaw

        connector = connector_manager._connectors.get(SourceType.OUTLOOK)
        if connector:
            connector._authenticated = False

        since   = datetime.utcnow() - timedelta(days=30)
        results = await connector_manager.sync_all(since=since, sources=[SourceType.OUTLOOK])
        fetched = ConnectorManager.collect_items(results)
        item_store.upsert(fetched)

        if fetched:
            db = SessionLocal()
            try:
                db.query(MessageRaw).filter(MessageRaw.source == "outlook").delete(synchronize_session=False)
                db.commit()
                load_items(fetched, db, run_nlp=False)
                rows      = load_from_db(db, since_days=30)
                refreshed = []
                for r in rows:
                    if r.get("source") == "outlook":
                        try:
                            refreshed.append(_build_data_item(r))
                        except Exception:
                            pass
                if refreshed:
                    item_store.upsert(refreshed)
                logger.info("[Outlook] Background sync: %d items loaded", len(refreshed))
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
                logger.info("[Outlook] NLP enrichissement : %d items", n_nlp)
            except Exception as nlp_err:
                logger.warning("[Outlook] NLP ignoré : %s", nlp_err)
            finally:
                db2.close()

    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).warning("[Outlook] Background sync failed: %s", e)
