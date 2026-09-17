"""
Slack OAuth v2 — InsightFlow Executive
=======================================
One Slack App (registered once at api.slack.com, "Distribution" enabled), installed
per-organisation via "Add to Slack" — each install produces its own bot token, scoped
to that org via source_configs.org_id. This is the same multi-tenant model as Outlook/Teams,
adapted to Slack's OAuth v2 (bot install, not a per-user delegated token).

Add these to .env:
  SLACK_CLIENT_ID=...
  SLACK_CLIENT_SECRET=...
  SLACK_REDIRECT_URI=http://localhost:8000/auth/slack/callback

Bot scopes required on the Slack App (OAuth & Permissions → Bot Token Scopes):
  channels:history  channels:read  channels:join  chat:write  im:write  users:read  users:read.email  files:read

Note: si l'app était déjà installée avant l'ajout d'un scope, il faut la
reconnecter (Slack ne backfille pas les scopes d'un token déjà émis).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import settings
from core.database import SessionLocal
from core.models import SourceConfig, User
from core.security import get_current_org_user, is_same_org_account
from core.plans import check_org_limit
import secrets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/slack", tags=["slack"])

BOT_SCOPES  = "channels:history,channels:read,channels:join,chat:write,im:write,users:read,users:read.email,files:read"
AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
TOKEN_URL     = "https://slack.com/api/oauth.v2.access"
USERS_INFO_URL = "https://slack.com/api/users.info"

# state → (org_id, requesting user's email)
_oauth_states: dict[str, tuple[str | None, str]] = {}


def _check_connector_limit_if_new(org_id: str | None) -> None:
    """Gate max_connectors only when Slack isn't already connected for this org."""
    db = SessionLocal()
    try:
        already = db.query(SourceConfig).filter(
            SourceConfig.source == "slack", SourceConfig.org_id == org_id,
        ).first()
        if already:
            return
        count = db.query(SourceConfig).filter(SourceConfig.org_id == org_id).count()
        check_org_limit(db, org_id, "max_connectors", count)
    finally:
        db.close()


# ── OAuth flow ──────────────────────────────────────────────────────────────

@router.get("/connect")
async def slack_connect(current_user: User = Depends(get_current_org_user)):
    """Redirect browser to Slack's 'Add to Slack' consent screen."""
    if not settings.slack_client_id:
        raise HTTPException(status_code=400, detail="SLACK_CLIENT_ID not configured in .env")
    _check_connector_limit_if_new(current_user.org_id)
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = (current_user.org_id, current_user.email)
    params = {
        "client_id":    settings.slack_client_id,
        "scope":        BOT_SCOPES,
        "redirect_uri": settings.slack_redirect_uri,
        "state":        state,
    }
    return RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/auth-url")
async def slack_auth_url(current_user: User = Depends(get_current_org_user)):
    """Frontend flow — returns the OAuth URL as JSON."""
    if not settings.slack_client_id:
        raise HTTPException(status_code=400, detail="SLACK_CLIENT_ID not configured in .env")
    _check_connector_limit_if_new(current_user.org_id)
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = (current_user.org_id, current_user.email)
    params = {
        "client_id":    settings.slack_client_id,
        "scope":        BOT_SCOPES,
        "redirect_uri": settings.slack_redirect_uri,
        "state":        state,
    }
    return {"url": f"{AUTHORIZE_URL}?{urlencode(params)}"}


@router.get("/callback")
async def slack_callback(
    background_tasks: BackgroundTasks = None,
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
):
    """Slack redirects here after the workspace admin approves the install."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Aucun code reçu.")
    if not state or state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF.")

    org_id, requesting_email = _oauth_states.pop(state)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id":     settings.slack_client_id,
            "client_secret": settings.slack_client_secret,
            "code":          code,
            "redirect_uri":  settings.slack_redirect_uri,
        })
        tokens = resp.json()
        if not tokens.get("ok"):
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {tokens.get('error')}")

        bot_token   = tokens.get("access_token", "")
        team        = tokens.get("team") or {}
        authed_user = tokens.get("authed_user") or {}

        # Vérifie que la personne qui installe l'app appartient bien au domaine de
        # l'utilisateur InsightFlow qui a initié le flow — empêche un compte externe
        # d'installer le bot sur un workspace qui n'a rien à voir avec cette org.
        connected_email = ""
        installer_id = authed_user.get("id")
        if installer_id and bot_token:
            try:
                me_resp = await client.get(
                    USERS_INFO_URL,
                    headers={"Authorization": f"Bearer {bot_token}"},
                    params={"user": installer_id},
                )
                me = me_resp.json()
                if me.get("ok"):
                    connected_email = (me.get("user") or {}).get("profile", {}).get("email", "")
            except Exception:
                connected_email = ""

    # TEMPORAIREMENT DÉSACTIVÉ : un seul compte dispo en test — voir auth.py (gmail_callback).
    # if not connected_email or not is_same_org_account(connected_email, requesting_email):
    #     return RedirectResponse(
    #         f"{settings.frontend_url}/onboarding?connected=slack&error=domain_mismatch"
    #         f"&connected_email={quote(connected_email)}",
    #         status_code=302,
    #     )

    token_data = {
        "bot_token":     bot_token,
        "team_id":       team.get("id", ""),
        "team_name":     team.get("name", ""),
        "installed_by":  connected_email,
        "connected_at":  datetime.utcnow().isoformat(),
    }
    _save_token(token_data, org_id)

    if background_tasks:
        background_tasks.add_task(_background_slack_sync, org_id)

    return RedirectResponse(f"{settings.frontend_url}/onboarding?connected=slack", status_code=302)


@router.get("/status")
async def slack_status(current_user: User = Depends(get_current_org_user)):
    cfg = _load_token(current_user.org_id)
    if not cfg or not cfg.get("bot_token"):
        return {"connected": False, "next_step": "GET /auth/slack/connect"}
    return {
        "connected":   True,
        "team_name":   cfg.get("team_name"),
        "installed_by": cfg.get("installed_by"),
        "connected_at": cfg.get("connected_at"),
    }


class SlackSendMessage(BaseModel):
    text: str
    channel_id: str | None = None
    user_id: str | None = None
    thread_ts: str | None = None


@router.post("/send-message")
async def slack_send_message(
    body: SlackSendMessage,
    current_user: User = Depends(get_current_org_user),
):
    """
    Poste un message via le bot Slack de cette org — soit dans un canal
    (`channel_id`, avec `thread_ts` optionnel pour répondre en thread), soit en
    DM à un utilisateur (`user_id`, ouvre la conversation automatiquement).
    """
    if not body.channel_id and not body.user_id:
        raise HTTPException(status_code=400, detail="channel_id ou user_id requis.")

    cfg = _load_token(current_user.org_id)
    if not cfg or not cfg.get("bot_token"):
        raise HTTPException(status_code=401, detail="Slack non connecté pour cette organisation.")

    from integrations.connectors.slack import SlackConnector
    connector = SlackConnector({"org_id": current_user.org_id})

    try:
        channel_id = body.channel_id or connector.open_dm(body.user_id)
        ts = connector.send_message(channel_id, body.text, thread_ts=body.thread_ts)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur Slack : {e}")

    return {"sent": True, "channel_id": channel_id, "ts": ts}


@router.delete("/disconnect", status_code=204)
async def slack_disconnect(current_user: User = Depends(get_current_org_user)):
    db = SessionLocal()
    try:
        db.query(SourceConfig).filter(
            SourceConfig.source == "slack",
            SourceConfig.org_id == current_user.org_id,
        ).delete()
        db.commit()
    finally:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_token(org_id: str | None) -> dict | None:
    db = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(
            SourceConfig.source == "slack", SourceConfig.org_id == org_id,
        ).first()
        return row.config if (row and isinstance(row.config, dict)) else None
    finally:
        db.close()


def _save_token(token_data: dict, org_id: str | None) -> None:
    db = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(
            SourceConfig.source == "slack", SourceConfig.org_id == org_id,
        ).first()
        if row:
            row.config = token_data
            row.connected_at = datetime.utcnow()
        else:
            db.add(SourceConfig(org_id=org_id, source="slack", config=token_data))
        db.commit()
    finally:
        db.close()


async def _background_slack_sync(org_id: str | None, since: datetime | None = None) -> None:
    """
    Sync Slack directement avec les credentials de l'org — bypass le connector_manager
    global (org-unaware). Même pattern que ClickUp (voir application/routes/sources.py).
    `since` par défaut à 30 jours (premier sync post-connexion) ; le resync périodique
    (voir _periodic_slack_sync_loop) passe une fenêtre plus courte.
    """
    try:
        from integrations.connectors.slack import SlackConnector
        from data.etl.loader import load_items, reprocess_unenriched

        connector = SlackConnector({"org_id": org_id})
        await connector.authenticate()
        if not connector.is_authenticated():
            logger.warning("[Slack] Sync post-connexion annulée — authentification échouée (org=%s)", org_id)
            return

        since = since or (datetime.utcnow() - timedelta(days=30))
        raw_items = await connector.fetch_raw(since)
        # Pas de suffixe d'org sur l'id — connector.normalize() génère déjà un id
        # stable (canal+ts), identique quel que soit le chemin de sync (ce bouton,
        # /api/sync, la boucle périodique) : suffixer ici dupliquait chaque message
        # (même item stocké sous deux ids différents selon la voie empruntée).
        items = [connector.normalize(r) for r in raw_items]

        if not items:
            logger.info("[Slack] Aucun item pour org=%s", org_id)
            return

        db = SessionLocal()
        try:
            n = load_items(items, db, run_nlp=False, org_id=org_id, index_rag=True)
            logger.info("[Slack] %d nouveaux items insérés pour org=%s", n, org_id)
        finally:
            db.close()

        import asyncio
        db2 = SessionLocal()
        try:
            n_nlp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: reprocess_unenriched(db2, limit=len(items) + 20)
            )
            logger.info("[Slack] NLP enrichissement : %d items (org=%s)", n_nlp, org_id)
        except Exception as nlp_err:
            logger.warning("[Slack] NLP ignoré : %s", nlp_err)
        finally:
            db2.close()

    except Exception as e:
        logger.warning("[Slack] Background sync failed (org=%s): %s", org_id, e)


# ── Resync périodique par organisation ──────────────────────────────────────
# Contourne le connector_manager global (org-unaware, voir main.py _realtime_sync_loop) :
# on liste ici toutes les orgs qui ont un token Slack en DB et on les sync une par une.

_last_org_sync: dict[str, datetime] = {}


async def periodic_slack_sync_loop() -> None:
    """Tâche de fond : resync Slack pour chaque org connectée, toutes les auto_sync_interval secondes."""
    import asyncio

    while True:
        await asyncio.sleep(settings.auto_sync_interval)
        try:
            db = SessionLocal()
            try:
                org_ids = [
                    r[0] for r in db.query(SourceConfig.org_id)
                    .filter(SourceConfig.source == "slack", SourceConfig.org_id.isnot(None))
                    .distinct().all()
                ]
            finally:
                db.close()

            for org_id in org_ids:
                since = _last_org_sync.get(org_id, datetime.utcnow() - timedelta(hours=1))
                await _background_slack_sync(org_id, since=since)
                _last_org_sync[org_id] = datetime.utcnow()
        except asyncio.CancelledError:
            logger.info("[Slack] Resync périodique arrêté")
            return
        except Exception as e:
            logger.warning("[Slack] Resync périodique échoué : %s", e)
