import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

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


@router.get("/gmail/callback")
async def gmail_callback(request: Request, code: str, state: str):
    """
    Step 2 — Google redirects here with an authorization code.
    Exchanges the code for access + refresh tokens and saves them.
    """
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF.")
    _oauth_states.discard(state)

    # Allow HTTP for localhost (not needed in production with HTTPS)
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    # Accept broader scopes returned by Google (openid, userinfo, etc.)
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    flow = _build_flow()
    flow.fetch_token(code=code)

    _save_token(flow.credentials)

    return {
        "status": "authenticated",
        "message": "Gmail connected successfully. You can now sync emails.",
        "next": "POST /api/sync  with  {\"sources\": [\"gmail\"]}",
    }


@router.get("/gmail/status")
async def gmail_status():
    """Check whether Gmail is authenticated."""
    creds = get_gmail_credentials()
    if creds and creds.valid:
        return {"connected": True, "scopes": creds.scopes}
    return {"connected": False, "next_step": "GET /auth/gmail"}
