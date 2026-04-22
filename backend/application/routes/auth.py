import json
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# In-memory state store for CSRF protection (use Redis in production)
_oauth_states: set[str] = set()


def _build_flow() -> Flow:
    return Flow.from_client_secrets_file(
        settings.gmail_credentials_path,
        scopes=SCOPES,
        redirect_uri=settings.gmail_redirect_uri,
    )


def get_gmail_credentials() -> Credentials | None:
    """Load credentials from token.json, refresh if expired."""
    token_path = settings.gmail_token_path
    if not os.path.exists(token_path):
        return None

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        _save_token(creds)

    return creds if creds.valid else None


def _save_token(creds: Credentials) -> None:
    with open(settings.gmail_token_path, "w") as f:
        f.write(creds.to_json())


def _build_auth_url() -> tuple[str, str]:
    """Generate the Google OAuth URL and state. Reusable by both endpoints."""
    if not os.path.exists(settings.gmail_credentials_path):
        raise HTTPException(
            status_code=500,
            detail=f"credentials.json introuvable à l'emplacement '{settings.gmail_credentials_path}'. "
                   "Téléchargez-le depuis la console Google Cloud.",
        )
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _oauth_states.add(state)
    return auth_url, state


@router.get("/gmail")
async def gmail_login():
    """Browser flow — redirects directly to Google consent screen."""
    auth_url, _ = _build_auth_url()
    return RedirectResponse(auth_url)


@router.get("/google")
async def google_auth_url():
    """
    Frontend flow — returns the OAuth URL as JSON so the frontend
    can redirect programmatically: { url: "https://accounts.google.com/..." }
    """
    auth_url, _ = _build_auth_url()
    return {"url": auth_url}


async def _background_gmail_sync():
    """Sync Gmail + ETL NLP en arrière-plan après connexion OAuth."""
    import logging
    from datetime import datetime, timedelta
    logger = logging.getLogger(__name__)
    try:
        from application.deps import connector_manager, item_store
        from integrations.connectors.schemas import SourceType, DataItem
        from core.database import SessionLocal
        from data.etl.loader import load_items, reprocess_unenriched, load_from_db

        since = datetime.utcnow() - timedelta(days=90)
        results = await connector_manager.sync_all(since=since, sources=[SourceType.GMAIL])
        from integrations.connectors import ConnectorManager
        fetched = ConnectorManager.collect_items(results)
        item_store.upsert(fetched)

        if fetched:
            db = SessionLocal()
            try:
                n = load_items(fetched, db, run_nlp=True)
                logger.info("[auth] Gmail sync + ETL : %d nouveaux items NLP enrichis", n)
                # Reprocess items sans NLP
                reprocess_unenriched(db, limit=200)
                # Rafraîchir le store
                rows = load_from_db(db, since_days=90)
                refreshed = []
                for r in rows:
                    try:
                        refreshed.append(DataItem(
                            id=r["id"], source=r["source"], type=r["item_type"],
                            title=r["title"] or "", content=r["content"] or "",
                            author=r["author"], timestamp=r["timestamp"],
                            url=r.get("url"),
                            tags=list(r["tags"]) if r.get("tags") else [],
                            metadata={
                                "from_email": r.get("author_email", ""),
                                "thread_id": r.get("thread_id"),
                                "sentiment_label": r.get("sentiment_label"),
                                "sentiment_score": r.get("sentiment_score"),
                                "emotion_label": r.get("emotion_label"),
                                "emotion_score": r.get("emotion_score"),
                                "topic": r.get("topic"),
                                "business_label": r.get("business_label"),
                                "business_confidence": r.get("business_confidence"),
                                "business_reason": r.get("business_reason"),
                                "burnout_score": r.get("burnout_score"),
                                "hour_sent": r.get("hour_sent"),
                                "is_weekend": r.get("is_weekend"),
                                "is_after_hours": r.get("is_after_hours"),
                            },
                        ))
                    except Exception:
                        pass
                item_store.upsert(refreshed)
                logger.info("[auth] Store rafraîchi : %d items avec NLP", len(refreshed))
            finally:
                db.close()
    except Exception as e:
        logging.getLogger(__name__).warning("[auth] Background sync failed: %s", e)


@router.get("/gmail/callback")
async def gmail_callback(request: Request, code: str, state: str, background_tasks: BackgroundTasks):
    """
    Step 2 — Google redirects here with an authorization code.
    Exchanges le code contre des tokens, sauvegarde, puis sync Gmail en arrière-plan.
    """
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF.")
    _oauth_states.discard(state)

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    flow = _build_flow()
    flow.fetch_token(code=code)
    _save_token(flow.credentials)

    # Sync Gmail + NLP en arrière-plan (non bloquant)
    background_tasks.add_task(_background_gmail_sync)

    return RedirectResponse("http://localhost:3001/dashboard", status_code=302)


@router.get("/gmail/status")
async def gmail_status():
    """Check whether Gmail is authenticated."""
    creds = get_gmail_credentials()
    if creds and creds.valid:
        return {"connected": True, "scopes": creds.scopes}
    return {"connected": False, "next_step": "GET /auth/gmail"}
