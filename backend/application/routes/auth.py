import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from core.config import settings
from core.database import SessionLocal
from core.models import SourceConfig, User
from core.security import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# state → org_id  (CSRF protection + org context through OAuth redirect)
_oauth_states: dict[str, str | None] = {}


def _build_flow() -> Flow:
    return Flow.from_client_secrets_file(
        settings.gmail_credentials_path,
        scopes=SCOPES,
        redirect_uri=settings.gmail_redirect_uri,
    )


def get_gmail_credentials(org_id: str | None = None) -> Credentials | None:
    """Load Gmail credentials from source_configs DB, refresh if expired."""
    try:
        db = SessionLocal()
        try:
            q = db.query(SourceConfig).filter(SourceConfig.source == "gmail")
            if org_id is not None:
                q = q.filter(SourceConfig.org_id == org_id)
            row = q.first()
            if not row:
                return None
            cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
            creds = Credentials(
                token=cfg.get("token"),
                refresh_token=cfg.get("refresh_token"),
                token_uri=cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=cfg.get("client_id"),
                client_secret=cfg.get("client_secret"),
                scopes=cfg.get("scopes", SCOPES),
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
                _save_token_db(creds, org_id)
            return creds if creds.valid else None
        finally:
            db.close()
    except Exception:
        if org_id is not None:
            return None
        # Fallback legacy token.json — uniquement quand org_id est inconnu (dev/tests)
        token_path = settings.gmail_token_path
        if not os.path.exists(token_path):
            return None
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        return creds if creds.valid else None


def _save_token_db(creds: Credentials, org_id: str | None) -> None:
    """Save Gmail credentials in source_configs DB, scoped to org."""
    from sqlalchemy.orm.attributes import flag_modified
    cfg = json.loads(creds.to_json())
    db = SessionLocal()
    try:
        q = db.query(SourceConfig).filter(SourceConfig.source == "gmail")
        if org_id is not None:
            q = q.filter(SourceConfig.org_id == org_id)
        row = q.first()
        if row:
            row.config = cfg
            flag_modified(row, "config")  # force JSONB dirty detection
        else:
            db.add(SourceConfig(org_id=org_id, source="gmail", config=cfg))
        db.commit()
    finally:
        db.close()


def _delete_gmail_credentials(org_id: str | None) -> None:
    """Remove Gmail credentials from source_configs (called after invalid_grant)."""
    db = SessionLocal()
    try:
        q = db.query(SourceConfig).filter(SourceConfig.source == "gmail")
        if org_id is not None:
            q = q.filter(SourceConfig.org_id == org_id)
        q.delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        print(f"[gmail-sync] Échec suppression credentials: {e}")
    finally:
        db.close()


def _build_auth_url(org_id: str | None) -> tuple[str, str]:
    """Generate the Google OAuth URL and state, storing org_id in state map."""
    if not os.path.exists(settings.gmail_credentials_path):
        raise HTTPException(
            status_code=500,
            detail=f"credentials.json introuvable à '{settings.gmail_credentials_path}'.",
        )
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _oauth_states[state] = org_id
    return auth_url, state


@router.get("/gmail")
async def gmail_login(current_user: User = Depends(get_current_user)):
    """Browser flow — redirects to Google consent screen."""
    auth_url, _ = _build_auth_url(current_user.org_id)
    return RedirectResponse(auth_url)


@router.get("/google")
async def google_auth_url(current_user: User = Depends(get_current_user)):
    """Frontend flow — returns OAuth URL as JSON."""
    if not current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail="Votre compte n'est associé à aucune organisation. Contactez votre administrateur ou re-créez votre compte.",
        )
    auth_url, _ = _build_auth_url(current_user.org_id)
    return {"url": auth_url}


def _do_gmail_sync_blocking(org_id: str | None) -> int:
    """Sync Gmail synchrone — appelé dans un thread séparé via asyncio.to_thread."""
    from datetime import datetime, timedelta

    print(f"[gmail-sync] Démarrage pour org={org_id}")

    creds = get_gmail_credentials(org_id)
    if not creds or not creds.valid:
        print(f"[gmail-sync] ERREUR: pas de credentials valides pour org={org_id}")
        return 0

    from googleapiclient.discovery import build
    from integrations.connectors.gmail import GmailConnector
    from data.etl.loader import load_items

    service = build("gmail", "v1", credentials=creds)

    from core.store import item_store
    from integrations.connectors.schemas import SourceType
    last_sync = item_store.last_sync(SourceType.GMAIL)
    since = last_sync if last_sync else datetime.utcnow() - timedelta(days=90)
    since_date = since.strftime("%Y/%m/%d")
    query = f"(in:inbox OR in:sent) -category:promotions -label:spam -label:junk after:{since_date}"

    print(f"[gmail-sync] Requête Gmail depuis {since_date} ({'delta' if last_sync else 'premier sync 90j'})…")
    msg_refs = []
    try:
        page_token = None
        while True:
            kwargs = {"userId": "me", "q": query, "maxResults": 200}
            if page_token:
                kwargs["pageToken"] = page_token
            response = service.users().messages().list(**kwargs).execute()
            msg_refs.extend(response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        print(f"[gmail-sync] ERREUR appel Gmail API: {e}")
        if "invalid_grant" in str(e):
            print(f"[gmail-sync] Token révoqué — suppression credentials pour org={org_id}, re-auth requise")
            _delete_gmail_credentials(org_id)
        return 0
    print(f"[gmail-sync] {len(msg_refs)} messages trouvés")

    NO_REPLY = ("no-reply", "noreply", "do-not-reply", "donotreply",
                "notifications@", "mailer-daemon", "bounce@")

    connector = GmailConnector({"org_id": org_id})
    items = []
    for ref in msg_refs:
        try:
            raw = service.users().messages().get(
                userId="me", id=ref["id"], format="full"
            ).execute()
            headers = {h["name"]: h["value"]
                       for h in raw.get("payload", {}).get("headers", [])}
            if any(p in headers.get("From", "").lower() for p in NO_REPLY):
                continue
            if headers.get("List-Unsubscribe") or headers.get("List-ID"):
                continue
            item = connector.normalize(raw)
            items.append(item)
        except Exception as e:
            print(f"[gmail-sync] msg {ref['id']} ignoré: {e}")

    print(f"[gmail-sync] {len(items)} items après filtrage")

    if not items:
        item_store.set_last_sync(SourceType.GMAIL, datetime.utcnow())
        return 0

    db = SessionLocal()
    try:
        n = load_items(items, db, run_nlp=False, org_id=org_id, index_rag=False)
        print(f"[gmail-sync] {n} nouveaux items insérés en DB pour org={org_id}")
        item_store.set_last_sync(SourceType.GMAIL, datetime.utcnow())
    except Exception as e:
        print(f"[gmail-sync] ERREUR insertion DB: {e}")
        return 0
    finally:
        db.close()

    # NLP enrichissement immédiat (synchrone — on est déjà dans un thread)
    if n > 0:
        db2 = SessionLocal()
        try:
            from data.etl.loader import reprocess_unenriched
            print(f"[gmail-sync] Lancement NLP enrichissement…")
            enriched = reprocess_unenriched(db2, limit=n + 20)
            print(f"[gmail-sync] NLP terminé : {enriched} items enrichis")
        except Exception as nlp_err:
            print(f"[gmail-sync] NLP ignoré : {nlp_err}")
        finally:
            db2.close()

    return n


async def _background_gmail_sync(org_id: str | None = None):
    """Lance le sync Gmail dans un thread pour ne pas bloquer l'event loop."""
    import asyncio
    print(f"[auth] Lancement background sync Gmail pour org={org_id}")
    try:
        n = await asyncio.to_thread(_do_gmail_sync_blocking, org_id)
        print(f"[auth] Gmail sync terminé: {n} items pour org={org_id}")
    except Exception as e:
        print(f"[auth] Gmail sync ERREUR (org={org_id}): {e}")


@router.get("/gmail/callback")
async def gmail_callback(request: Request, code: str, state: str, background_tasks: BackgroundTasks):
    """
    Step 2 — Google redirects here with an authorization code.
    Retrieves org_id from state map, saves token to DB, syncs Gmail.
    """
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF.")
    org_id = _oauth_states.pop(state)

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    flow = _build_flow()
    flow.fetch_token(code=code)
    _save_token_db(flow.credentials, org_id)

    background_tasks.add_task(_background_gmail_sync, org_id)

    return RedirectResponse(f"{settings.frontend_url}/onboarding?connected=gmail", status_code=302)


@router.get("/gmail/status")
async def gmail_status(current_user: User = Depends(get_current_user)):
    """Check whether Gmail is authenticated for this org."""
    creds = get_gmail_credentials(current_user.org_id)
    if creds and creds.valid:
        return {"connected": True, "scopes": list(creds.scopes or [])}
    return {"connected": False, "next_step": "GET /auth/gmail"}


@router.get("/gmail/diagnose")
async def gmail_diagnose(current_user: User = Depends(get_current_user)):
    """
    Diagnostic complet Gmail :
    - état des credentials
    - emails trouvés par l'API (5 derniers)
    - lesquels sont déjà en DB vs nouveaux
    """
    from datetime import datetime, timedelta
    from core.database import SessionLocal
    from core.models import MessageRaw as _MR
    from googleapiclient.discovery import build

    result: dict = {"org_id": current_user.org_id, "steps": {}}

    # 1. Credentials
    creds = get_gmail_credentials(current_user.org_id)
    result["steps"]["credentials"] = {
        "found": creds is not None,
        "valid": creds.valid if creds else False,
        "expired": creds.expired if creds else None,
    }
    if not creds or not creds.valid:
        result["conclusion"] = "STOP: credentials invalides — re-connecter Gmail"
        return result

    # 2. Appel API Gmail — 5 derniers emails
    try:
        service = build("gmail", "v1", credentials=creds)
        since_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y/%m/%d")
        query = f"(in:inbox OR in:sent) after:{since_date}"
        resp = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        msg_refs = resp.get("messages", [])
        result["steps"]["gmail_api"] = {
            "messages_found": len(msg_refs),
            "total_estimate": resp.get("resultSizeEstimate", "?"),
            "ids": [r["id"] for r in msg_refs],
        }
    except Exception as e:
        result["steps"]["gmail_api"] = {"error": str(e)}
        result["conclusion"] = f"STOP: erreur API Gmail — {e}"
        return result

    # 3. Ces IDs sont-ils déjà en DB ?
    db_ids_full  = [f"gmail_{r['id']}_{current_user.org_id[:8]}" for r in msg_refs] if current_user.org_id else []
    db_ids_plain = [f"gmail_{r['id']}" for r in msg_refs]
    db = SessionLocal()
    try:
        found_full  = {r.id for r in db.query(_MR.id).filter(_MR.id.in_(db_ids_full)).all()}
        found_plain = {r.id for r in db.query(_MR.id).filter(_MR.id.in_(db_ids_plain)).all()}
        total_in_db = db.query(_MR).filter(_MR.org_id == current_user.org_id).count()
    finally:
        db.close()

    result["steps"]["db_check"] = {
        "total_messages_for_org_in_db": total_in_db,
        "scoped_ids_in_db":  list(found_full),
        "plain_ids_in_db":   list(found_plain),
        "new_emails_not_in_db": [
            r["id"] for r in msg_refs
            if f"gmail_{r['id']}_{current_user.org_id[:8]}" not in found_full
            and f"gmail_{r['id']}" not in found_plain
        ],
    }

    new_count = len(result["steps"]["db_check"]["new_emails_not_in_db"])
    result["conclusion"] = (
        f"{new_count} email(s) nouveaux non encore en DB sur les 5 derniers" if new_count
        else "Les 5 derniers emails Gmail sont déjà en DB"
    )
    return result


@router.post("/migrate-all-credentials")
async def migrate_all_credentials(current_user: User = Depends(get_current_user)):
    """
    Migration one-shot : rattache toutes les source_configs orphelines (org_id=NULL)
    à l'organisation de l'utilisateur connecté.
    À appeler une seule fois après la migration multi-tenant.
    """
    if not current_user.org_id:
        raise HTTPException(status_code=400, detail="Votre compte n'a pas d'organisation.")

    db = SessionLocal()
    try:
        rows = db.query(SourceConfig).filter(SourceConfig.org_id == None).all()
        if not rows:
            return {"status": "nothing_to_migrate", "message": "Toutes les sources ont déjà un org_id."}

        migrated = []
        for row in rows:
            row.org_id = current_user.org_id
            migrated.append(row.source)

        db.commit()
        return {
            "status": "migrated",
            "org_id": current_user.org_id,
            "sources_migrated": migrated,
            "count": len(migrated),
        }
    finally:
        db.close()


@router.post("/gmail/migrate-credentials")
async def gmail_migrate_credentials(current_user: User = Depends(get_current_user)):
    """
    Migre les credentials Gmail stockés avec org_id=NULL vers le vrai org_id de l'utilisateur.
    À appeler une fois si Gmail était connecté avant la migration multi-tenant.
    """
    from sqlalchemy.orm.attributes import flag_modified
    if not current_user.org_id:
        raise HTTPException(status_code=400, detail="Votre compte n'a pas d'organisation.")

    db = SessionLocal()
    try:
        # Cherche un row gmail sans org_id (legacy)
        row = db.query(SourceConfig).filter(
            SourceConfig.source == "gmail",
            SourceConfig.org_id == None,
        ).first()

        if not row:
            # Vérifie si déjà migré
            existing = db.query(SourceConfig).filter(
                SourceConfig.source == "gmail",
                SourceConfig.org_id == current_user.org_id,
            ).first()
            if existing:
                return {"status": "already_migrated", "org_id": current_user.org_id}
            return {"status": "not_found", "message": "Aucun credentials Gmail trouvé — reconnectez Gmail via OAuth."}

        # Migre vers le bon org_id
        row.org_id = current_user.org_id
        flag_modified(row, "config")
        db.commit()
        return {"status": "migrated", "org_id": current_user.org_id, "message": "Credentials Gmail migrés — sync en cours."}
    finally:
        db.close()


@router.post("/gmail/sync")
async def gmail_sync_now(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Déclenche un sync Gmail immédiat pour l'org du CEO connecté."""
    creds = get_gmail_credentials(current_user.org_id)
    if not creds or not creds.valid:
        raise HTTPException(status_code=400, detail="Gmail non connecté pour cette organisation.")
    background_tasks.add_task(_background_gmail_sync, current_user.org_id)
    return {"status": "sync_started", "org_id": current_user.org_id,
            "message": "Sync Gmail lancé en arrière-plan — vérifiez les logs backend."}
