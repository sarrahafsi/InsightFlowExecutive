"""
OneDrive OAuth + folder picker — InsightFlow Executive
Requires Azure app registration with Files.Read + offline_access scopes.
"""
import json
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from core.models import ProjectSource, SourceConfig

router = APIRouter(prefix="/auth/onedrive", tags=["onedrive"])

GRAPH_SCOPE   = "Files.Read Files.Read.All offline_access"
AUTH_BASE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
TOKEN_URL     = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_API     = "https://graph.microsoft.com/v1.0"


# ── OAuth flow ────────────────────────────────────────────────────────────────

@router.get("/connect")
async def onedrive_connect(project_id: str = Query(...)):
    """Redirect to Microsoft OAuth. project_id stored in state param."""
    if not settings.onedrive_client_id:
        raise HTTPException(status_code=400, detail="OneDrive client_id not configured. Add ONEDRIVE_CLIENT_ID to .env")

    params = {
        "client_id":     settings.onedrive_client_id,
        "response_type": "code",
        "redirect_uri":  settings.onedrive_redirect_uri,
        "scope":         GRAPH_SCOPE,
        "state":         project_id,
        "response_mode": "query",
    }
    url = AUTH_BASE_URL.format(tenant=settings.onedrive_tenant) + "?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/callback")
async def onedrive_callback(code: str = Query(...), state: str = Query(...)):
    """Handle Microsoft OAuth callback. state = project_id."""
    project_id = state

    # Exchange code for tokens
    token_url = TOKEN_URL.format(tenant=settings.onedrive_tenant)
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "client_id":     settings.onedrive_client_id,
            "client_secret": settings.onedrive_client_secret,
            "code":          code,
            "redirect_uri":  settings.onedrive_redirect_uri,
            "grant_type":    "authorization_code",
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")
        tokens = resp.json()

    # Save token in source_configs (keyed by project)
    db: Session = SessionLocal()
    try:
        key = f"onedrive_{project_id}"
        row = db.query(SourceConfig).filter(SourceConfig.source == key).first()
        token_data = {
            "access_token":  tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
        }
        if row:
            row.config = token_data
        else:
            db.add(SourceConfig(source=key, config=token_data))
        db.commit()
    finally:
        db.close()

    # Redirect to project page (folder picker tab)
    return RedirectResponse(f"http://localhost:3000/dashboard/projects/{project_id}?tab=preferences&onedrive=connected")


# ── Graph API helpers ─────────────────────────────────────────────────────────

def _get_token(project_id: str) -> str:
    db: Session = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(SourceConfig.source == f"onedrive_{project_id}").first()
        if not row:
            raise HTTPException(status_code=401, detail="OneDrive not connected for this project")
        cfg = row.config if isinstance(row.config, dict) else json.loads(row.config)
        return cfg["access_token"]
    finally:
        db.close()


@router.get("/folders")
async def list_folders(project_id: str = Query(...), folder_id: str = Query(default="root")):
    """List OneDrive folders for the folder picker."""
    token = _get_token(project_id)

    url = f"{GRAPH_API}/me/drive/items/{folder_id}/children"
    if folder_id == "root":
        url = f"{GRAPH_API}/me/drive/root/children"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"},
                                params={"$select": "id,name,folder,size", "$filter": "folder ne null"})
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="OneDrive token expired. Reconnect.")
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=resp.text)
        data = resp.json()

    return [{"id": item["id"], "name": item["name"]} for item in data.get("value", [])]


@router.get("/status")
async def onedrive_status(project_id: str = Query(...)):
    """Check if OneDrive is connected for this project."""
    db: Session = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(SourceConfig.source == f"onedrive_{project_id}").first()
        return {"connected": row is not None}
    finally:
        db.close()


# ── Link folder to project ────────────────────────────────────────────────────

class LinkFolderBody(BaseModel):
    folder_id:   str
    folder_name: str


@router.post("/link")
async def link_folder(project_id: str = Query(...), body: LinkFolderBody = None):
    """Save selected OneDrive folder to project_sources."""
    db: Session = SessionLocal()
    try:
        from core.models import Project, ProjectSource, ProjectActivity
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Project not found")

        # Remove existing onedrive source if any
        db.query(ProjectSource).filter(
            ProjectSource.project_id == project_id,
            ProjectSource.source_type == "onedrive"
        ).delete()

        src = ProjectSource(
            project_id=project_id,
            source_type="onedrive",
            config={"folder_id": body.folder_id, "folder_name": body.folder_name},
        )
        db.add(src)
        db.add(ProjectActivity(
            project_id=project_id, actor="CEO",
            action="linked_source", detail=f"OneDrive — {body.folder_name}",
        ))
        db.commit()
        return {"connected": True, "folder_name": body.folder_name}
    finally:
        db.close()
