"""
Webhook receivers — Gmail (Pub/Sub), Slack (Events API), Jira.
Each handler:
  1. Validates the incoming request
  2. Triggers a targeted sync in background
  3. Broadcasts the result via WebSocket
"""
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from core.config import settings
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

async def _sync_source_and_broadcast(source_value: str):
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

        # ── NLP — synchrone, 2-5s ───────────────────────────────────────────
        db = SessionLocal()
        try:
            load_items(new_items, db, run_nlp=True)
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

    except Exception as e:
        logger.error("[webhook/%s] sync error: %s", source_value, e)


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

    background_tasks.add_task(_sync_source_and_broadcast, "gmail")
    return {"status": "ok"}


@router.post("/gmail/watch")
async def start_gmail_watch():
    """
    Register Gmail push notifications via Google Pub/Sub.
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
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import os

        token_path = settings.gmail_token_path
        if not os.path.exists(token_path):
            raise HTTPException(status_code=400, detail="Gmail token.json not found — authenticate first")

        import json as _json
        with open(token_path) as f:
            token_data = _json.load(f)

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
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
        background_tasks.add_task(_sync_source_and_broadcast, "slack")

    return {"status": "ok"}


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
