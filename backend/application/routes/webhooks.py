"""
Webhook receivers — Gmail (Pub/Sub), Slack (Events API), Jira.
Each handler:
  1. Validates the incoming request
  2. Triggers a targeted sync in background
  3. Broadcasts the result via WebSocket
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from core.config import settings
from core.models import User
from core.security import get_current_org_user
from core.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

URGENT_KEYWORDS = {
    "urgent", "urgence", "critique", "critical", "bloqu", "blocked",
    "down", "crash", "panne", "incident", "alerte", "alert",
    "asap", "immédiat", "immediate", "priorité", "priority",
    "escalade", "escalation", "crisis", "crise", "bloquant",
    "production", "p0", "p1", "sev1", "sev0", "outage",
}

def _is_urgent_text(text: str) -> bool:
    """Keyword-based urgency detection — instant, no NLP needed."""
    lower = text.lower()
    return any(kw in lower for kw in URGENT_KEYWORDS)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _sync_source_and_broadcast(source_value: str, org_id: str | None = None):
    """
    Two-phase broadcast:
      Phase 1 (immédiat)  — toast "nouveau message", pas de refresh inbox
      Phase 2 (après NLP) — nlp_complete → frontend rafraîchit Priority Inbox
                          — notification urgente si labels NLP le confirment
    """
    try:
        from integrations.connectors.schemas import SourceType
        from integrations.connectors import ConnectorManager
        from application.deps import connector_manager, item_store
        from data.etl.loader import load_items, load_from_db
        from core.database import SessionLocal
        from main import _build_data_item

        src   = SourceType(source_value)
        since = datetime.utcnow() - timedelta(minutes=5)

        if org_id and source_value == "gmail":
            # Meme piege que Slack (cf. commentaire ci-dessous) : le connector_manager
            # global est org-unaware, et fetch_raw()+normalize() sans passer par
            # BaseConnector.sync() saute aussi l'enrichissement image (meme bug que
            # le premier sync a l'inscription, cf. auth.py::_do_gmail_sync_blocking) —
            # on reproduit donc les deux etapes explicitement ici.
            from integrations.connectors.gmail import GmailConnector
            from intelligence.nlp.image_processor import enrich_data_items_with_images
            connector = GmailConnector({"org_id": org_id})
            await connector.authenticate()
            if not connector.is_authenticated():
                logger.warning("[webhook/gmail] org=%s non authentifié — skip", org_id)
                return
            raw_items = await connector.fetch_raw(since)
            new_items = [connector.normalize(r) for r in raw_items]
            await enrich_data_items_with_images(new_items)
        elif org_id and source_value == "slack":
            # Slack est en OAuth par org (token en DB) — le connector_manager global
            # est org-unaware (cf. mémoire feedback_connector_manager, même bug déjà
            # vu sur Gmail/ClickUp/Jira) : il ne trouve aucun credential et sync_all()
            # no-op silencieusement (pas d'exception, juste 0 items). On synchronise
            # donc directement avec les credentials de l'org, comme _background_slack_sync
            # (application/routes/slack_auth.py).
            from integrations.connectors.slack import SlackConnector
            connector = SlackConnector({"org_id": org_id})
            await connector.authenticate()
            if not connector.is_authenticated():
                logger.warning("[webhook/slack] org=%s non authentifié — skip", org_id)
                return
            raw_items = await connector.fetch_raw(since)
            new_items = [connector.normalize(r) for r in raw_items]
        else:
            results   = await connector_manager.sync_all(since=since, sources=[src])
            new_items = ConnectorManager.collect_items(results)

        if not new_items:
            return

        new_item_ids = {i.id for i in new_items}

        # ── Phase 1 : toast immédiat, PAS de refresh inbox ──────────────────
        await ws_manager.broadcast({
            "type":      "new_messages",
            "source":    source_value,
            "count":     len(new_items),
            "timestamp": datetime.utcnow().isoformat(),
            "preview":   [{"id": i.id, "title": i.title, "author": i.author}
                          for i in new_items[:3]],
        })

        # ── NLP — 2-5s de calcul CPU-bound, off-loadé dans un thread pour ne
        # pas bloquer la event loop (sinon les requêtes webhook concurrentes
        # timeout côté ngrok/Slack pendant ce temps — cf. status 0 observés) ──
        db = SessionLocal()
        try:
            await asyncio.to_thread(load_items, new_items, db, run_nlp=True, org_id=org_id)
            # Recharger depuis DB pour avoir les vrais labels NLP
            rows = load_from_db(db, since_days=1)
            enriched = []
            for r in rows:
                if r.get("id") in new_item_ids:
                    try:
                        enriched.append(_build_data_item(r))
                    except Exception:
                        pass
        finally:
            db.close()

        items_with_nlp = enriched if enriched else new_items
        item_store.upsert(items_with_nlp)

        # ── Phase 2 : nlp_complete → frontend rafraîchit Priority Inbox ─────
        urgent_notifs = []
        for item in items_with_nlp:
            meta      = item.metadata or {}
            sentiment = meta.get("sentiment_label", "")
            business  = meta.get("business_label", "")
            priority  = meta.get("priority", "")
            if (sentiment in ("negative", "very_negative")
                    or business in ("escalation", "urgent", "crisis")
                    or priority in ("Highest", "High", "Blocker", "Critical")):
                urgent_notifs.append({
                    "type":      "notification",
                    "level":     "critical",
                    "source":    source_value,
                    "message":   f"Message urgent de {item.author} : {item.title[:70]}",
                    "item_id":   item.id,
                    "sentiment": sentiment,
                    "business":  business,
                    "timestamp": datetime.utcnow().isoformat(),
                })

        # Signal de refresh Priority Inbox (après NLP)
        await ws_manager.broadcast({
            "type":         "nlp_complete",
            "source":       source_value,
            "count":        len(items_with_nlp),
            "urgent_count": len(urgent_notifs),
            "timestamp":    datetime.utcnow().isoformat(),
        })

        # Notifications urgentes (avec vrais labels NLP)
        for notif in urgent_notifs:
            await ws_manager.broadcast(notif)

    except Exception:
        logger.exception("[webhook/%s] sync error", source_value)


# ── Gmail — Google Pub/Sub push ───────────────────────────────────────────────

@router.post("/gmail")
async def gmail_push(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Gmail push notification from Google Pub/Sub.
    Google sends a POST with a base64-encoded JSON payload containing
    emailAddress and historyId.
    """
    body = await request.json()
    msg  = body.get("message", {})
    encoded = msg.get("data", "")
    try:
        decoded = json.loads(base64.b64decode(encoded + "==").decode())
    except Exception:
        return {"status": "ignored"}

    email_address = decoded.get("emailAddress", "")
    history_id    = decoded.get("historyId")
    logger.info("[webhook/gmail] push — email=%s historyId=%s", email_address, history_id)

    org_id = _resolve_gmail_org_id(email_address)
    if not org_id:
        logger.warning("[webhook/gmail] aucune org trouvée pour email=%s — sync ignoré", email_address)
        return {"status": "ignored"}

    background_tasks.add_task(_sync_source_and_broadcast, "gmail", org_id)
    return {"status": "ok"}


def _resolve_gmail_org_id(email_address: str | None) -> str | None:
    """Retrouve l'org InsightFlow dont la boîte Gmail connectée correspond à cet
    email — le payload Pub/Sub ne porte pas notre org_id directement. Sans ça,
    le sync passait par le connector_manager global (org-unaware) et insérait
    les messages avec org_id=NULL, invisibles pour l'org (cf. meme bug déjà vu
    et corrigé sur Slack via _resolve_slack_org_id)."""
    if not email_address:
        return None
    from core.database import SessionLocal
    from core.models import SourceConfig

    db = SessionLocal()
    try:
        rows = db.query(SourceConfig).filter(SourceConfig.source == "gmail").all()
        for r in rows:
            cfg = r.config if isinstance(r.config, dict) else {}
            if cfg.get("connected_email") == email_address:
                return r.org_id
        return None
    finally:
        db.close()


@router.post("/gmail/watch")
async def start_gmail_watch(current_user: User = Depends(get_current_org_user)):
    """
    Register Gmail push notifications via Google Pub/Sub, for the caller's org.
    Requires GMAIL_PUBSUB_TOPIC to be set in .env.
    Call once after setting up ngrok — watch expires after 7 days.
    """
    topic = settings.gmail_pubsub_topic
    if not topic:
        raise HTTPException(
            status_code=400,
            detail="GMAIL_PUBSUB_TOPIC not configured in .env",
        )
    try:
        from googleapiclient.discovery import build
        from application.routes.auth import get_gmail_credentials

        # Credentials live per-org in source_configs (DB) — same lookup used by
        # every other Gmail route. token.json is only auth.py's dev/test fallback,
        # so reading it directly here (as before) went stale the moment an org
        # connected/reconnected Gmail through the normal OAuth flow.
        creds = get_gmail_credentials(current_user.org_id)
        if creds is None:
            raise HTTPException(
                status_code=400,
                detail="Gmail non connecté (ou token invalide) pour cette organisation — reconnectez Gmail d'abord.",
            )
        service = build("gmail", "v1", credentials=creds)
        result  = service.users().watch(
            userId="me",
            body={"labelIds": ["INBOX"], "topicName": topic},
        ).execute()

        logger.info("[webhook/gmail] watch registered: %s", result)
        return {
            "status": "ok",
            "history_id": result.get("historyId"),
            "expiration": result.get("expiration"),
            "topic": topic,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail watch failed: {e}")


# ── Slack — Events API ────────────────────────────────────────────────────────

@router.post("/slack")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_signature: str = Header(default=""),
    x_slack_request_timestamp: str = Header(default=""),
):
    """
    Receive Slack Events API notifications.
    Handles URL verification challenge automatically.
    """
    raw_body = await request.body()

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # URL verification challenge (sent once when you configure the webhook)
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    # Verify Slack signature
    signing_secret = settings.slack_signing_secret
    if signing_secret and x_slack_signature:
        sig_base  = f"v0:{x_slack_request_timestamp}:{raw_body.decode()}"
        computed  = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_base.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(computed, x_slack_signature):
            raise HTTPException(status_code=403, detail="Invalid Slack signature")

    event = body.get("event", {})
    # Only handle user messages (ignore bot messages)
    if event.get("type") == "message" and not event.get("bot_id"):
        logger.info("[webhook/slack] message event — channel=%s user=%s",
                    event.get("channel"), event.get("user"))
        org_id = _resolve_slack_org_id(body.get("team_id"))
        background_tasks.add_task(_sync_source_and_broadcast, "slack", org_id)

    return {"status": "ok"}


def _resolve_slack_org_id(team_id: str | None) -> str | None:
    """Retrouve l'org InsightFlow connectée à ce workspace Slack (team_id) —
    le payload Slack ne porte pas notre org_id directement."""
    if not team_id:
        return None
    from core.database import SessionLocal
    from core.models import SourceConfig

    db = SessionLocal()
    try:
        rows = db.query(SourceConfig).filter(SourceConfig.source == "slack").all()
        for r in rows:
            cfg = r.config if isinstance(r.config, dict) else {}
            if cfg.get("team_id") == team_id:
                return r.org_id
        return None
    finally:
        db.close()


# ── Jira — Webhooks ───────────────────────────────────────────────────────────

@router.post("/jira")
async def jira_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Jira webhook notifications (issue created / updated).
    Immediate broadcast for high-priority issues, then background sync.
    """
    body        = await request.json()
    event_type  = body.get("webhookEvent", "")
    issue       = body.get("issue", {})
    issue_key   = issue.get("key", "")
    fields      = issue.get("fields", {})
    priority    = (fields.get("priority") or {}).get("name", "")
    status      = (fields.get("status")   or {}).get("name", "")
    summary     = fields.get("summary", "")
    assignee    = (fields.get("assignee") or {}).get("displayName", "Unknown")

    logger.info("[webhook/jira] %s — %s (%s)", event_type, issue_key, priority)

    is_critical = priority in ("Highest", "High", "Blocker", "Critical")

    # Immediate broadcast — no need to wait for full sync
    await ws_manager.broadcast({
        "type": "new_messages",
        "source": "jira",
        "count": 1,
        "timestamp": datetime.utcnow().isoformat(),
        "preview": [{
            "id": issue_key, "title": summary,
            "author": assignee, "status": status, "priority": priority,
        }],
    })

    if is_critical:
        await ws_manager.broadcast({
            "type": "notification",
            "level": "critical",
            "source": "jira",
            "message": f"Ticket {priority} Jira : [{issue_key}] {summary[:70]}",
            "item_id": issue_key,
            "timestamp": datetime.utcnow().isoformat(),
        })

    await ws_manager.broadcast({
        "type": "kpi_update",
        "source": "jira",
        "timestamp": datetime.utcnow().isoformat(),
    })

    background_tasks.add_task(_sync_source_and_broadcast, "jira")
    return {"status": "ok"}
