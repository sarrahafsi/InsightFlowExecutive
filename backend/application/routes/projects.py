"""
Projects CRUD API — InsightFlow Executive
"""
from datetime import datetime
from uuid import uuid4

import os
import shutil

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")

from core.database import get_db, SessionLocal
from core.models import Project, ProjectMember, ProjectSource, ProjectNote, ProjectFile, ProjectActivity, SourceConfig, MessageRaw, User
from core.security import get_current_user, require_ceo

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    color: str = "#3e5c76"
    created_by: str | None = "CEO"

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    status: str | None = None      # on_track | at_risk | off_track
    progress: int | None = None    # 0–100

class MemberAdd(BaseModel):
    name: str
    email: str
    role: str = "member"

class SourceLink(BaseModel):
    source_type: str   # onedrive | teams
    config: dict = {}

class NoteCreate(BaseModel):
    title: str | None = None
    content: str
    created_by: str | None = "CEO"

class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(db: Session, project_id: str, actor: str, action: str, detail: str = ""):
    db.add(ProjectActivity(
        project_id=project_id,
        actor=actor,
        action=action,
        detail=detail,
    ))


def _project_or_404(db: Session, project_id: str, org_id: str | None = None) -> Project:
    q = db.query(Project).filter(Project.id == project_id)
    if org_id is not None:
        q = q.filter(Project.org_id == org_id)
    p = q.first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


# ── Projects ─────────────────────────────────────────────────────────────────

@router.get("")
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Project).filter(Project.org_id == current_user.org_id)
    if current_user.role == "pm":
        # PM sees only projects where they appear as a member (matched by email)
        member_project_ids = (
            db.query(ProjectMember.project_id)
            .filter(ProjectMember.email == current_user.email)
            .subquery()
        )
        q = q.filter(Project.id.in_(member_project_ids))
    return [_serialize_project(p) for p in q.order_by(Project.created_at.desc()).all()]


@router.post("", status_code=201)
def create_project(
    body: ProjectCreate,
    current_user: User = Depends(require_ceo),
    db: Session = Depends(get_db),
):
    project = Project(
        id=str(uuid4()),
        org_id=current_user.org_id,
        name=body.name,
        description=body.description,
        color=body.color,
        created_by=current_user.full_name,
    )
    db.add(project)
    _log(db, project.id, current_user.full_name, "created_project", f"Project '{body.name}' created")
    db.commit()
    db.refresh(project)
    return _serialize_project(project)


@router.get("/{project_id}")
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _serialize_project(_project_or_404(db, project_id, current_user.org_id))


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _project_or_404(db, project_id, current_user.org_id)
    if body.name        is not None: p.name        = body.name
    if body.description is not None: p.description = body.description
    if body.color       is not None: p.color       = body.color
    if body.status      is not None: p.status      = body.status
    if body.progress    is not None: p.progress    = max(0, min(100, body.progress))
    p.updated_at = datetime.utcnow()
    _log(db, project_id, current_user.full_name, "updated_project", "Project updated")
    db.commit()
    db.refresh(p)
    return _serialize_project(p)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _project_or_404(db, project_id, current_user.org_id)
    db.delete(p)
    db.commit()


# ── Members ───────────────────────────────────────────────────────────────────

@router.post("/{project_id}/members", status_code=201)
def add_member(
    project_id: str,
    body: MemberAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _project_or_404(db, project_id, current_user.org_id)
    member = ProjectMember(project_id=project_id, name=body.name, email=body.email, role=body.role)
    db.add(member)
    _log(db, project_id, current_user.full_name, "added_member", f"{body.name} ({body.role})")
    db.commit()
    db.refresh(member)
    return {"id": member.id, "name": member.name, "email": member.email, "role": member.role}


@router.delete("/{project_id}/members/{member_id}", status_code=204)
def remove_member(
    project_id: str,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _project_or_404(db, project_id, current_user.org_id)
    m = db.query(ProjectMember).filter(
        ProjectMember.id == member_id,
        ProjectMember.project_id == project_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(m)
    db.commit()


# ── Sources ───────────────────────────────────────────────────────────────────

@router.post("/{project_id}/sources", status_code=201)
def link_source(
    project_id: str,
    body: SourceLink,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _project_or_404(db, project_id, current_user.org_id)
    src = ProjectSource(project_id=project_id, source_type=body.source_type, config=body.config)
    db.add(src)
    _log(db, project_id, current_user.full_name, "linked_source", f"{body.source_type} linked")
    db.commit()
    db.refresh(src)
    return {"id": src.id, "source_type": src.source_type, "config": src.config}


@router.delete("/{project_id}/sources/{source_id}", status_code=204)
def unlink_source(project_id: str, source_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    s = db.query(ProjectSource).filter(
        ProjectSource.id == source_id,
        ProjectSource.project_id == project_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(s)
    db.commit()


# ── Notes ─────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/notes")
def list_notes(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    notes = db.query(ProjectNote).filter(ProjectNote.project_id == project_id).order_by(ProjectNote.created_at.desc()).all()
    return [{"id": n.id, "title": n.title, "content": n.content, "created_by": n.created_by,
             "created_at": n.created_at, "updated_at": n.updated_at} for n in notes]


@router.post("/{project_id}/notes", status_code=201)
def create_note(project_id: str, body: NoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    note = ProjectNote(project_id=project_id, title=body.title, content=body.content, created_by=current_user.full_name)
    db.add(note)
    _log(db, project_id, current_user.full_name, "created_note", body.title or "Untitled note")
    db.commit()
    db.refresh(note)
    return {"id": note.id, "title": note.title, "content": note.content,
            "created_by": note.created_by, "created_at": note.created_at}


@router.patch("/{project_id}/notes/{note_id}")
def update_note(project_id: str, note_id: int, body: NoteUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(ProjectNote).filter(ProjectNote.id == note_id, ProjectNote.project_id == project_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    if body.title   is not None: n.title   = body.title
    if body.content is not None: n.content = body.content
    n.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(n)
    return {"id": n.id, "title": n.title, "content": n.content, "updated_at": n.updated_at}


@router.delete("/{project_id}/notes/{note_id}", status_code=204)
def delete_note(project_id: str, note_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    n = db.query(ProjectNote).filter(ProjectNote.id == note_id, ProjectNote.project_id == project_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    _log(db, project_id, current_user.full_name, "deleted_note", n.title or "Note sans titre")
    db.delete(n)
    db.commit()


# ── Files ─────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/files")
def list_files(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).order_by(ProjectFile.uploaded_at.desc()).all()
    return [{"id": f.id, "filename": f.filename, "source": f.source, "size_bytes": f.size_bytes,
             "mime_type": f.mime_type, "uploaded_by": f.uploaded_by, "uploaded_at": f.uploaded_at} for f in files]


@router.post("/{project_id}/files/upload", status_code=201)
async def upload_file(project_id: str, file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)

    project_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, file.filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = os.path.getsize(file_path)

    record = ProjectFile(
        project_id=project_id,
        filename=file.filename,
        file_path=file_path,
        source="upload",
        size_bytes=size,
        mime_type=file.content_type,
        uploaded_by=current_user.full_name,
    )
    db.add(record)
    _log(db, project_id, current_user.full_name, "uploaded_file", file.filename)
    db.commit()
    db.refresh(record)

    return {"id": record.id, "filename": record.filename, "size_bytes": record.size_bytes,
            "mime_type": record.mime_type, "uploaded_at": record.uploaded_at}


@router.delete("/{project_id}/files/{file_id}", status_code=204)
def delete_file(project_id: str, file_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    f = db.query(ProjectFile).filter(ProjectFile.id == file_id, ProjectFile.project_id == project_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    if f.file_path and os.path.exists(f.file_path):
        os.remove(f.file_path)
    _log(db, project_id, current_user.full_name, "deleted_file", f.filename)
    db.delete(f)
    db.commit()


# ── Activity ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/activity")
def get_activity(project_id: str, limit: int = 50, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _project_or_404(db, project_id, current_user.org_id)
    activities = (
        db.query(ProjectActivity)
        .filter(ProjectActivity.project_id == project_id)
        .order_by(ProjectActivity.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{"id": a.id, "actor": a.actor, "action": a.action,
             "detail": a.detail, "created_at": a.created_at} for a in activities]


# ── Serializer ────────────────────────────────────────────────────────────────

def _serialize_project(p: Project) -> dict:
    return {
        "id":           p.id,
        "name":         p.name,
        "description":  p.description,
        "color":        p.color,
        "created_by":   p.created_by,
        "status":       p.status    or "on_track",
        "progress":     p.progress  or 0,
        "blockers":     p.blockers  or 0,
        "risk_level":   p.risk_level or "Low",
        "sentiment":    p.sentiment  or "Neutral",
        "created_at":   p.created_at,
        "updated_at":   p.updated_at,
        "members":      [{"id": m.id, "name": m.name, "email": m.email, "role": m.role} for m in p.members],
        "sources":      [{"id": s.id, "source_type": s.source_type, "config": s.config} for s in p.sources],
        "notes_count":  len(p.notes),
        "files_count":  len(p.files),
    }


# ── ClickUp project integration ───────────────────────────────────────────────

CLICKUP_API = "https://api.clickup.com/api/v2"


def _clickup_token() -> str:
    db = SessionLocal()
    try:
        row = db.query(SourceConfig).filter(SourceConfig.source == "clickup").first()
        if row:
            cfg = row.config if isinstance(row.config, dict) else {}
            return cfg.get("api_token", "")
    finally:
        db.close()
    return ""


class LinkClickUpList(BaseModel):
    list_id:   str
    list_name: str
    space_name: str = ""


@router.get("/{project_id}/clickup/debug-statuses")
async def debug_statuses(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Debug: returns raw status objects for all tasks in linked list."""
    src = db.query(ProjectSource).filter(
        ProjectSource.project_id == project_id,
        ProjectSource.source_type == "clickup",
    ).first()
    if not src:
        return {"error": "No ClickUp list linked"}
    cfg     = src.config if isinstance(src.config, dict) else {}
    list_id = cfg.get("list_id", "")
    token   = _clickup_token()
    if not token or not list_id:
        return {"error": "No token or list_id"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{CLICKUP_API}/list/{list_id}/task",
            headers={"Authorization": token},
            params={"include_closed": "true", "page": 0},
        )
        tasks = r.json().get("tasks", [])
    return [{"title": t.get("name"), "status": t.get("status")} for t in tasks[:20]]


@router.get("/{project_id}/clickup/lists")
async def clickup_lists(project_id: str):
    """Return all ClickUp lists the CEO has access to (for the list picker)."""
    token = _clickup_token()
    if not token:
        raise HTTPException(status_code=400, detail="ClickUp not connected")

    headers = {"Authorization": token}
    result: list[dict] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Get teams
        r = await client.get(f"{CLICKUP_API}/team", headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="ClickUp API error")
        teams = r.json().get("teams", [])

        for team in teams:
            team_id = team["id"]
            # 2. Get spaces
            r2 = await client.get(f"{CLICKUP_API}/team/{team_id}/space",
                                   headers=headers, params={"archived": "false"})
            if r2.status_code != 200:
                continue
            for space in r2.json().get("spaces", []):
                space_id   = space["id"]
                space_name = space["name"]

                # Folderless lists
                r3 = await client.get(f"{CLICKUP_API}/space/{space_id}/list",
                                       headers=headers, params={"archived": "false"})
                if r3.status_code == 200:
                    for lst in r3.json().get("lists", []):
                        result.append({
                            "list_id":   str(lst["id"]),
                            "list_name": lst["name"],
                            "space_name": space_name,
                            "task_count": lst.get("task_count", 0),
                        })

                # Lists inside folders
                r4 = await client.get(f"{CLICKUP_API}/space/{space_id}/folder",
                                       headers=headers, params={"archived": "false"})
                if r4.status_code == 200:
                    for folder in r4.json().get("folders", []):
                        folder_name = folder["name"]
                        for lst in folder.get("lists", []):
                            result.append({
                                "list_id":   str(lst["id"]),
                                "list_name": lst["name"],
                                "space_name": f"{space_name} / {folder_name}",
                                "task_count": lst.get("task_count", 0),
                            })

    return result


@router.post("/{project_id}/clickup/link", status_code=201)
def link_clickup_list(project_id: str, body: LinkClickUpList, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Link a ClickUp list to this project."""
    _project_or_404(db, project_id, current_user.org_id)

    # Remove previous ClickUp source if any
    db.query(ProjectSource).filter(
        ProjectSource.project_id == project_id,
        ProjectSource.source_type == "clickup",
    ).delete()

    src = ProjectSource(
        project_id=project_id,
        source_type="clickup",
        config={"list_id": body.list_id, "list_name": body.list_name, "space_name": body.space_name},
    )
    db.add(src)
    _log(db, project_id, "CEO", "linked_source", f"ClickUp — {body.list_name}")
    db.commit()
    db.refresh(src)
    return {"id": src.id, "list_id": body.list_id, "list_name": body.list_name}


@router.get("/{project_id}/clickup/tasks")
async def get_clickup_tasks(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fetch tasks for the linked ClickUp list — DB first, live API fallback."""
    _project_or_404(db, project_id, current_user.org_id)

    # Get linked list
    src = db.query(ProjectSource).filter(
        ProjectSource.project_id == project_id,
        ProjectSource.source_type == "clickup",
    ).first()

    if not src:
        return []

    cfg       = src.config if isinstance(src.config, dict) else {}
    list_id   = cfg.get("list_id", "")
    list_name = cfg.get("list_name", "")

    # ── 1. Live ClickUp API (toujours frais) ───────────────────
    token = _clickup_token()
    if token and list_id:
        headers = {"Authorization": token}
        tasks: list[dict] = []
        page = 0

        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                r = await client.get(
                    f"{CLICKUP_API}/list/{list_id}/task",
                    headers=headers,
                    params={"page": page, "order_by": "updated", "reverse": "true",
                            "include_closed": "true"},
                )
                if r.status_code != 200:
                    break
                batch = r.json().get("tasks", [])
                tasks.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

        if tasks:
            return [_serialize_live_task(t, list_name) for t in tasks]

    # ── 2. Fallback DB si API inaccessible ─────────────────────
    rows = (
        db.query(MessageRaw)
        .filter(MessageRaw.source == "clickup", MessageRaw.item_type == "ticket")
        .order_by(MessageRaw.timestamp.desc())
        .limit(500)
        .all()
    )
    matching = [r for r in rows if (r.metadata_json or {}).get("list_name") == list_name]
    return [_serialize_task(r) for r in matching]


def _serialize_task(r: MessageRaw) -> dict:
    meta = r.metadata_json or {}
    return {
        "id":          r.id,
        "title":       r.title or "",
        "status":      meta.get("status", "unknown"),
        "is_done":     meta.get("is_done", False),
        "priority":    meta.get("priority", "Normal"),
        "assignee":    meta.get("assignee_name") or meta.get("assignee") or r.author or "",
        "due_date":    meta.get("due_date"),
        "list_name":   meta.get("list_name", ""),
        "folder_name": meta.get("folder_name", ""),
        "url":         r.url or "",
        "updated_at":  r.timestamp.isoformat() if r.timestamp else "",
        "tags":        r.tags or [],
    }


def _serialize_live_task(t: dict, list_name: str) -> dict:
    status_obj   = t.get("status") or {}
    priority_obj = t.get("priority") or {}
    assignees    = t.get("assignees") or []
    priority_map = {
        "urgent": "Urgent", "high": "High", "normal": "Normal", "low": "Low",
        "1": "Urgent", "2": "High", "3": "Normal", "4": "Low",
    }
    priority_raw = priority_obj.get("priority") or priority_obj.get("id")
    priority_num = priority_raw.lower() if isinstance(priority_raw, str) else priority_raw

    def _ms(val):
        if not val:
            return None
        try:
            from datetime import timezone
            import datetime as _dt
            return _dt.datetime.utcfromtimestamp(int(val) / 1000).isoformat()
        except Exception:
            return None

    return {
        "id":          f"clickup_{t.get('id', '')}",
        "title":       t.get("name", ""),
        "status":      status_obj.get("status", "unknown"),
        "is_done":     status_obj.get("type", "").lower() == "closed" or status_obj.get("status", "").lower() in {"complete", "done", "closed"},
        "priority":    priority_map.get(priority_num, "Normal") if priority_num else "Normal",
        "assignee":    assignees[0].get("username", "") if assignees else "",
        "due_date":    _ms(t.get("due_date")),
        "list_name":   list_name,
        "folder_name": (t.get("folder") or {}).get("name", ""),
        "url":         t.get("url", ""),
        "updated_at":  _ms(t.get("date_updated")) or "",
        "tags":        [tag.get("name", "") for tag in (t.get("tags") or [])],
    }


# ── Project AI Summary ────────────────────────────────────────────────────────

@router.get("/{project_id}/clickup/summary")
async def clickup_summary(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compute task stats + generate AI brief via Ollama."""
    from datetime import timezone
    import datetime as _dt

    p = _project_or_404(db, project_id, current_user.org_id)

    # ── 1. Get tasks (reuse existing endpoint logic) ───────────
    tasks_response = await get_clickup_tasks(project_id, db)
    tasks = tasks_response if isinstance(tasks_response, list) else []

    if not tasks:
        return {
            "stats": {"total": 0, "done": 0, "open": 0, "urgent": 0, "blocked": 0, "progress": 0},
            "summary": "Aucune tâche trouvée pour ce projet. Liez une liste ClickUp dans les Préférences.",
            "assignees": [],
        }

    # ── 2. Compute stats ───────────────────────────────────────
    now = _dt.datetime.utcnow()
    total   = len(tasks)
    done    = sum(1 for t in tasks if t["is_done"])
    urgent  = sum(1 for t in tasks if not t["is_done"] and t["priority"] == "Urgent")
    overdue = sum(1 for t in tasks if not t["is_done"] and t.get("due_date") and
                  _dt.datetime.fromisoformat(t["due_date"].replace("Z", "")) < now)

    # Blocked = open + not updated in 5+ days
    blocked = 0
    for t in tasks:
        if t["is_done"]:
            continue
        upd = t.get("updated_at") or ""
        if upd:
            try:
                upd_dt = _dt.datetime.fromisoformat(upd.replace("Z", ""))
                if (now - upd_dt).days >= 5:
                    blocked += 1
            except Exception:
                pass

    progress = round((done / total) * 100) if total > 0 else 0

    # Per-assignee breakdown
    assignee_map: dict[str, dict] = {}
    for t in tasks:
        name = t.get("assignee") or "Non assigné"
        if name not in assignee_map:
            assignee_map[name] = {"name": name, "total": 0, "done": 0, "urgent": 0}
        assignee_map[name]["total"] += 1
        if t["is_done"]:
            assignee_map[name]["done"] += 1
        if t["priority"] == "Urgent":
            assignee_map[name]["urgent"] += 1
    assignees = sorted(assignee_map.values(), key=lambda x: x["total"], reverse=True)[:5]

    # ── 3. Build Ollama prompt ─────────────────────────────────
    open_tasks = [t for t in tasks if not t["is_done"]]
    urgent_titles = [t["title"] for t in open_tasks if t["priority"] == "Urgent"][:5]
    blocked_titles = []
    for t in open_tasks:
        upd = t.get("updated_at") or ""
        if upd:
            try:
                upd_dt = _dt.datetime.fromisoformat(upd.replace("Z", ""))
                if (now - upd_dt).days >= 5:
                    blocked_titles.append(f"{t['title']} ({(now - upd_dt).days}j sans mise à jour)")
            except Exception:
                pass
    blocked_titles = blocked_titles[:5]

    overdue_titles = [t["title"] for t in open_tasks
                      if t.get("due_date") and
                      _dt.datetime.fromisoformat(t["due_date"].replace("Z", "")) < now][:5]

    prompt = f"""Tu es l'assistant IA d'un CEO. Génère un résumé exécutif COURT (4-6 phrases max) du projet "{p.name}".

DONNÉES DU PROJET :
- Total tâches : {total} | Terminées : {done} ({progress}%) | En cours : {total - done}
- Urgentes : {urgent} | Bloquées (≥5j sans update) : {blocked} | En retard : {overdue}
- Tâches urgentes : {', '.join(urgent_titles) if urgent_titles else 'aucune'}
- Tâches bloquées : {', '.join(blocked_titles) if blocked_titles else 'aucune'}
- Tâches en retard : {', '.join(overdue_titles) if overdue_titles else 'aucune'}
- Membres actifs : {', '.join(f"{a['name']} ({a['total']} tâches, {a['done']} terminées)" for a in assignees[:3])}

Résumé en français, ton direct CEO. Commence par l'état global, signale les risques, termine par une recommandation si nécessaire. Pas de markdown, pas de listes à puces."""

    # ── 4. Call LLM (Ollama ou Azure GPT-4o) ──────────────────
    from intelligence.llm.client import complete as llm_complete
    try:
        summary = await llm_complete(
            system="Tu es l'assistant IA d'un CEO. Réponds en français, ton direct, pas de markdown.",
            user=prompt,
            use_tools=False,
            temperature=0.2,
            max_tokens=250,
        )
    except Exception as e:
        summary = f"Résumé IA indisponible ({e}). Voici l'état : {done}/{total} tâches terminées, {urgent} urgentes, {blocked} bloquées."

    return {
        "stats": {
            "total":    total,
            "done":     done,
            "open":     total - done,
            "urgent":   urgent,
            "blocked":  blocked,
            "overdue":  overdue,
            "progress": progress,
        },
        "summary":   summary,
        "assignees": assignees,
    }


# ── Per-project OHS ──────────────────────────────────────────────────────────

@router.get("/{project_id}/ohs")
async def project_ohs(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compute a composite health score scoped to this project's signals."""
    import datetime as _dt

    p = _project_or_404(db, project_id, current_user.org_id)

    # ── 1. Flatten all signals from cross-signals ─────────────────
    signals_raw = await cross_signals(project_id, db)

    all_sigs: list[dict] = []
    for task_sig in signals_raw:
        all_sigs.extend(task_sig.get("signals", []))

    total_sigs = len(all_sigs)

    # ── 2. Sentiment — use label already present in each signal ───
    if total_sigs > 0:
        pos = sum(1 for s in all_sigs if (s.get("sentiment") or "").upper() == "POSITIVE")
        neu = sum(1 for s in all_sigs if (s.get("sentiment") or "").upper() in ("NEUTRAL", ""))
        sentiment_score = max(0.0, min(100.0, (pos * 100.0 + neu * 60.0) / total_sigs))
    else:
        sentiment_score = 60.0

    # ── 3. Burnout — query DB by the unique authors in signals ────
    authors = list({s.get("author", "") for s in all_sigs if s.get("author")})
    if authors:
        since_b = _dt.datetime.utcnow() - _dt.timedelta(days=30)
        burnout_vals = [
            r.burnout_score
            for r in db.query(MessageRaw.burnout_score)
                       .filter(
                           MessageRaw.author.in_(authors),
                           MessageRaw.burnout_score.isnot(None),
                           MessageRaw.timestamp >= since_b,
                       ).all()
            if r.burnout_score is not None
        ]
        if burnout_vals:
            avg_b = sum(burnout_vals) / len(burnout_vals)
            burnout_score = max(0.0, min(100.0, (1.0 - avg_b) * 100.0))
        else:
            burnout_score = 70.0
    else:
        burnout_score = 70.0

    # ── 4. Task dimension (ClickUp) ───────────────────────────────
    task_score = 75.0
    clickup_stats = None
    try:
        resp = await clickup_summary(project_id, db)
        clickup_stats = resp.get("stats")
        if clickup_stats and clickup_stats.get("total", 0) > 0:
            total_t  = clickup_stats["total"]
            progress = clickup_stats.get("progress", 0)
            blocked  = clickup_stats.get("blocked", 0)
            urgent   = clickup_stats.get("urgent", 0)
            task_score = max(0.0, min(100.0,
                float(progress)
                - (blocked / total_t) * 40.0
                - (urgent  / total_t) * 20.0
            ))
    except Exception:
        pass

    # ── 5. Communication — after-hours ratio scoped to project signals ─
    if all_sigs:
        after = 0
        counted = 0
        for s in all_sigs:
            raw_date = s.get("date", "")
            if not raw_date:
                continue
            try:
                ts = _dt.datetime.fromisoformat(raw_date)
                counted += 1
                if ts.hour < 8 or ts.hour > 20:
                    after += 1
            except ValueError:
                pass
        if counted > 0:
            comm_score = max(0.0, min(100.0, 100.0 - (after / counted) * 100.0))
        else:
            comm_score = 70.0
    else:
        comm_score = 70.0

    # ── 6. Weighted composite ─────────────────────────────────────
    WEIGHTS = {"sentiment": 0.30, "burnout": 0.25, "tasks": 0.30, "communication": 0.15}
    dims = {
        "sentiment":     round(sentiment_score, 1),
        "burnout":       round(burnout_score, 1),
        "tasks":         round(task_score, 1),
        "communication": round(comm_score, 1),
    }
    score = round(sum(dims[k] * WEIGHTS[k] for k in WEIGHTS))

    if score >= 70:
        label, color = "Sain", "#22c55e"
    elif score >= 40:
        label, color = "Tendu", "#f59e0b"
    else:
        label, color = "Critique", "#ef4444"

    LABELS = {
        "sentiment":     "Sentiment des messages liés",
        "burnout":       "Surcharge des membres",
        "tasks":         "Avancement des tâches",
        "communication": "Fluidité communication",
    }

    return {
        "project_id":    project_id,
        "project_name":  p.name,
        "score":         score,
        "label":         label,
        "color":         color,
        "linked_msgs":   total_sigs,
        "signals_tasks": len(signals_raw),
        "computed_at":   _dt.datetime.utcnow().isoformat(),
        "breakdown":     [
            {"key": k, "label": LABELS[k], "score": dims[k], "weight": int(WEIGHTS[k] * 100)}
            for k in WEIGHTS
        ],
    }


# ── Cross-source signals ──────────────────────────────────────────────────────

_STOP_WORDS = {
    "le","la","les","un","de","du","des","et","en","à","au","aux","est","par",
    "sur","pour","dans","avec","the","a","an","of","to","in","for","on","and",
    "is","are","was","be","this","that","fix","add","update","feat","bug","task",
}

def _keywords(text: str, min_len: int = 4) -> set[str]:
    """Extract meaningful keywords from a task title."""
    import re
    words = re.findall(r"[a-zA-ZÀ-ÿ]{%d,}" % min_len, text.lower())
    return {w for w in words if w not in _STOP_WORDS}


@router.get("/{project_id}/clickup/signals")
async def cross_signals(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    For each open ClickUp task, find related Gmail/Slack messages in the DB.
    Matching logic: email title or content shares ≥2 keywords with the task title,
    OR the email author email matches the task assignee.
    Returns only tasks that have at least one signal.
    """
    import datetime as _dt

    # ── 1. Get open tasks ──────────────────────────────────────
    tasks_raw = await get_clickup_tasks(project_id, db)
    open_tasks = [t for t in tasks_raw if not t["is_done"]]
    if not open_tasks:
        return []

    # ── 2. Load recent messages from DB (Gmail + Slack, last 60 days) ─
    since = _dt.datetime.utcnow() - _dt.timedelta(days=60)
    messages = (
        db.query(MessageRaw)
        .filter(
            MessageRaw.source.in_(["gmail", "slack"]),
            MessageRaw.timestamp >= since,
        )
        .order_by(MessageRaw.timestamp.desc())
        .limit(1000)
        .all()
    )

    if not messages:
        return []

    # ── 3. Match tasks ↔ messages (RAG semantic search + keyword fallback) ────
    SOURCE_ICON = {"gmail": "📧", "slack": "💬"}
    signals: list[dict] = []

    # Pre-build a dict of messages by ID for O(1) lookup after RAG
    messages_by_id: dict[str, object] = {str(msg.id): msg for msg in messages}

    # Try RAG-based matching — falls back to keywords if ChromaDB is empty
    try:
        from intelligence.rag.retriever import retrieve as _rag_retrieve
        from intelligence.rag.embedder import get_collection as _get_col
        _rag_available = _get_col().count() > 0
    except Exception:
        _rag_available = False

    for task in open_tasks:
        assignee_name = (task.get("assignee") or "").lower()
        matched: list[dict] = []

        if _rag_available:
            # ── RAG path: embed task title → semantic similarity ──────────
            # score = cosine distance (0 = identical, 2 = opposite)
            rag_docs = _rag_retrieve(task["title"], top_k=15)

            for doc in rag_docs:
                # Keep only relevant matches from gmail/slack, distance ≤ 0.72
                if doc.score > 0.72 or doc.source not in ("gmail", "slack"):
                    continue
                msg = messages_by_id.get(doc.id)
                if msg is None:
                    continue  # message not in recent window

                # Relevance score 0–10 (inverted distance)
                relevance = round((1.0 - doc.score / 2.0) * 10, 1)

                # Author match bonus
                author_match = (
                    assignee_name and len(assignee_name) > 3
                    and (assignee_name in (msg.author or "").lower()
                         or assignee_name in (msg.author_email or "").lower())
                )
                final_score = relevance + (2.0 if author_match else 0.0)

                title = msg.title or ""
                content_preview = (msg.content or "")[:200]
                if msg.source == "slack" and (not title or title.startswith("#")):
                    display_title = content_preview[:80] or "(message Slack)"
                else:
                    display_title = (title or content_preview[:80] or "(sans titre)")[:80]

                matched.append({
                    "id":        msg.id,
                    "source":    msg.source,
                    "icon":      SOURCE_ICON.get(msg.source, "📌"),
                    "title":     display_title,
                    "excerpt":   content_preview,
                    "author":    msg.author or "",
                    "date":      msg.timestamp.isoformat() if msg.timestamp else "",
                    "sentiment": msg.sentiment_label or "",
                    "emotion":   msg.emotion_label or "",
                    "url":       msg.url or "",
                    "score":     final_score,
                    "match_type": "semantic",
                    "rag_distance": round(doc.score, 3),
                })

        else:
            # ── Keyword fallback (ChromaDB empty / not indexed yet) ────────
            task_keywords = _keywords(task["title"])
            if len(task_keywords) < 1:
                continue

            for msg in messages:
                msg_text = f"{msg.title or ''} {msg.content or ''}".lower()
                msg_keywords = _keywords(msg_text, min_len=4)
                common = task_keywords & msg_keywords

                author_match = (
                    assignee_name and len(assignee_name) > 3
                    and (assignee_name in (msg.author or "").lower()
                         or assignee_name in (msg.author_email or "").lower())
                )

                score = len(common) * 2 + (3 if author_match else 0)
                if score < 2:
                    continue

                title = msg.title or ""
                content_preview = (msg.content or "")[:200]
                if msg.source == "slack" and (not title or title.startswith("#")):
                    display_title = content_preview[:80] or "(message Slack)"
                else:
                    display_title = (title or content_preview[:80] or "(sans titre)")[:80]

                matched.append({
                    "id":        msg.id,
                    "source":    msg.source,
                    "icon":      SOURCE_ICON.get(msg.source, "📌"),
                    "title":     display_title,
                    "excerpt":   content_preview,
                    "author":    msg.author or "",
                    "date":      msg.timestamp.isoformat() if msg.timestamp else "",
                    "sentiment": msg.sentiment_label or "",
                    "emotion":   msg.emotion_label or "",
                    "url":       msg.url or "",
                    "score":     score,
                    "match_type": "keyword",
                    "keywords":  list(common)[:5],
                })

        if matched:
            # Sort by score desc, keep top 3
            matched.sort(key=lambda x: x["score"], reverse=True)
            signals.append({
                "task_id":    task["id"],
                "task_title": task["title"],
                "priority":   task["priority"],
                "assignee":   task["assignee"],
                "is_done":    task["is_done"],
                "signals":    matched[:3],
            })

    # Sort: urgent first, then by number of signals
    signals.sort(key=lambda x: (
        0 if x["priority"] == "Urgent" else 1 if x["priority"] == "High" else 2,
        -len(x["signals"])
    ))

    return signals[:15]  # Max 15 tasks with signals


# ── Slack channel linking ─────────────────────────────────────────────────────

class LinkSlackChannel(BaseModel):
    channel_id:   str
    channel_name: str


@router.get("/{project_id}/slack/channels")
async def list_slack_channels(project_id: str):
    """List available Slack channels for linking."""
    from core.config import settings
    token = settings.slack_bot_token
    if not token:
        raise HTTPException(status_code=400, detail="Slack not connected")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 100, "types": "public_channel,private_channel"},
        )
        data = resp.json()
        if not data.get("ok"):
            err = data.get("error", "unknown")
            raise HTTPException(status_code=400, detail=f"Slack API error: {err}. Scopes needed: channels:read, groups:read")
        channels = data.get("channels", [])

    return [
        {"channel_id": c["id"], "channel_name": c["name"], "is_private": c.get("is_private", False), "num_members": c.get("num_members", 0)}
        for c in channels
    ]


@router.post("/{project_id}/slack/link", status_code=201)
def link_slack_channel(project_id: str, body: LinkSlackChannel, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Link a Slack channel to this project."""
    _project_or_404(db, project_id, current_user.org_id)

    db.query(ProjectSource).filter(
        ProjectSource.project_id == project_id,
        ProjectSource.source_type == "slack",
    ).delete()

    src = ProjectSource(
        project_id=project_id,
        source_type="slack",
        config={"channel_id": body.channel_id, "channel_name": body.channel_name},
    )
    db.add(src)
    _log(db, project_id, "CEO", "linked_source", f"Slack — #{body.channel_name}")
    db.commit()
    db.refresh(src)
    return {"id": src.id, "channel_id": body.channel_id, "channel_name": body.channel_name}


@router.get("/{project_id}/slack/messages")
async def slack_project_messages(project_id: str, limit: int = 30, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return recent messages from the linked Slack channel."""
    import datetime as _dt

    _project_or_404(db, project_id, current_user.org_id)
    src = db.query(ProjectSource).filter(
        ProjectSource.project_id == project_id,
        ProjectSource.source_type == "slack",
    ).first()

    if not src:
        return []

    cfg          = src.config if isinstance(src.config, dict) else {}
    channel_name = cfg.get("channel_name", "")

    since = _dt.datetime.utcnow() - _dt.timedelta(days=30)
    rows = (
        db.query(MessageRaw)
        .filter(
            MessageRaw.source == "slack",
            MessageRaw.timestamp >= since,
        )
        .order_by(MessageRaw.timestamp.desc())
        .limit(limit * 3)
        .all()
    )

    # Filter by channel name from metadata or tags
    matching = []
    for r in rows:
        meta = r.metadata_json or {}
        tags = r.tags or []
        if (meta.get("channel") == channel_name
                or channel_name in tags
                or (not channel_name)):  # fallback: all slack if no channel linked
            matching.append(r)

    matching = matching[:limit]
    return [
        {
            "id":        r.id,
            "author":    r.author or "",
            "content":   (r.content or "")[:300],
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            "sentiment": r.sentiment_label or "",
            "url":       r.url or "",
        }
        for r in matching
    ]


# ── Project Overview ──────────────────────────────────────────────────────────

@router.get("/{project_id}/overview")
async def project_overview(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Aggregated CEO-level overview of a project:
    - Connected sources status
    - ClickUp task stats (if linked)
    - Slack NLP sentiment (if linked)
    - Cross-source signal count
    - Overall project health / climate
    """
    import datetime as _dt
    from collections import Counter

    _project_or_404(db, project_id, current_user.org_id)

    # ── 1. Connected sources ───────────────────────────────────
    sources = db.query(ProjectSource).filter(
        ProjectSource.project_id == project_id
    ).all()
    source_map = {s.source_type: s.config if isinstance(s.config, dict) else {} for s in sources}

    # ── 2. ClickUp stats ───────────────────────────────────────
    clickup_stats = None
    clickup_summary_text = ""
    if "clickup" in source_map:
        try:
            resp = await clickup_summary(project_id, db)
            clickup_stats        = resp.get("stats")
            clickup_summary_text = resp.get("summary", "")
        except Exception:
            pass

    # ── 3. Slack NLP stats ─────────────────────────────────────
    slack_stats = None
    if "slack" in source_map:
        since = _dt.datetime.utcnow() - _dt.timedelta(days=30)
        cfg          = source_map["slack"]
        channel_name = cfg.get("channel_name", "")
        rows = (
            db.query(MessageRaw)
            .filter(MessageRaw.source == "slack", MessageRaw.timestamp >= since)
            .order_by(MessageRaw.timestamp.desc())
            .limit(200)
            .all()
        )
        if channel_name:
            rows = [r for r in rows if
                    (r.metadata_json or {}).get("channel") == channel_name
                    or channel_name in (r.tags or [])]

        if rows:
            sent_counts = Counter(r.sentiment_label or "NEUTRAL" for r in rows)
            emo_counts  = Counter(r.emotion_label for r in rows if r.emotion_label)
            total_s     = max(len(rows), 1)
            top_emotion = emo_counts.most_common(1)[0][0] if emo_counts else "neutral"
            slack_stats = {
                "total":      len(rows),
                "positive":   round(sent_counts["POSITIVE"] / total_s * 100),
                "negative":   round(sent_counts["NEGATIVE"] / total_s * 100),
                "neutral":    round(sent_counts["NEUTRAL"]  / total_s * 100),
                "top_emotion": top_emotion,
                "channel":    channel_name,
            }

    # ── 4. Gmail stats (global, last 30 days) ─────────────────
    gmail_stats = None
    gmail_src = db.query(SourceConfig).filter(SourceConfig.source == "gmail").first()
    if gmail_src:
        since = _dt.datetime.utcnow() - _dt.timedelta(days=7)
        rows = (
            db.query(MessageRaw)
            .filter(MessageRaw.source == "gmail", MessageRaw.timestamp >= since)
            .limit(200)
            .all()
        )
        if rows:
            sent_counts = Counter(r.sentiment_label or "NEUTRAL" for r in rows)
            total_g     = max(len(rows), 1)
            risk_count  = sum(1 for r in rows if r.business_label in ("Blocked", "Urgent", "Risk", "Conflict"))
            gmail_stats = {
                "total":      len(rows),
                "negative":   round(sent_counts["NEGATIVE"] / total_g * 100),
                "risk_count": risk_count,
            }

    # ── 5. Cross-source signals count ─────────────────────────
    signals_count = 0
    try:
        sigs = await cross_signals(project_id, db)
        signals_count = sum(len(ts["signals"]) for ts in sigs)
    except Exception:
        pass

    # ── 6. Project health / climate ───────────────────────────
    risk_score = 0
    if clickup_stats:
        if clickup_stats.get("blocked", 0) > 0:
            risk_score += 30
        if clickup_stats.get("urgent", 0) > 0:
            risk_score += 20
        progress = clickup_stats.get("progress", 100)
        if progress < 30:
            risk_score += 20
        elif progress < 60:
            risk_score += 10
    if slack_stats:
        risk_score += min(30, slack_stats.get("negative", 0))
    if gmail_stats:
        risk_score += min(20, gmail_stats.get("risk_count", 0) * 5)

    risk_score = min(100, risk_score)
    if risk_score >= 60:
        climate = {"label": "Critical", "color": "#ef4444", "icon": "🔴", "fr": "Critique"}
    elif risk_score >= 35:
        climate = {"label": "Tense",    "color": "#f59e0b", "icon": "🟡", "fr": "Tendu"}
    elif risk_score >= 15:
        climate = {"label": "Moderate", "color": "#eab308", "icon": "🟠", "fr": "Modéré"}
    else:
        climate = {"label": "Healthy",  "color": "#22c55e", "icon": "🟢", "fr": "Sain"}

    # ── Sync computed metrics back to project record ───────────
    try:
        proj = _project_or_404(db, project_id, current_user.org_id)

        # Progress from ClickUp
        if clickup_stats and "progress" in clickup_stats:
            proj.progress = clickup_stats["progress"]

        # Blockers from ClickUp
        if clickup_stats:
            proj.blockers = clickup_stats.get("blocked", 0)

        # Risk level from risk_score
        proj.risk_level = "High" if risk_score >= 60 else "Medium" if risk_score >= 35 else "Low"

        # Status badge from risk_score
        proj.status = "off_track" if risk_score >= 60 else "at_risk" if risk_score >= 35 else "on_track"

        # Sentiment from slack + gmail
        neg_pct = 0
        pos_pct = 0
        if slack_stats:
            neg_pct += slack_stats.get("negative", 0)
            pos_pct += slack_stats.get("positive", 0)
        if gmail_stats:
            neg_pct += gmail_stats.get("negative", 0)
        if neg_pct > 40:
            proj.sentiment = "Negative"
        elif pos_pct > 50:
            proj.sentiment = "Positive"
        else:
            proj.sentiment = "Neutral"

        db.commit()
    except Exception:
        pass

    return {
        "sources": {
            "clickup":  {"connected": "clickup"  in source_map, "config": source_map.get("clickup",  {})},
            "slack":    {"connected": "slack"    in source_map, "config": source_map.get("slack",    {})},
            "onedrive": {"connected": "onedrive" in source_map, "config": source_map.get("onedrive", {})},
        },
        "clickup":       clickup_stats,
        "clickup_brief": clickup_summary_text,
        "slack":         slack_stats,
        "gmail":         gmail_stats,
        "signals_count": signals_count,
        "climate":       climate,
        "risk_score":    risk_score,
    }


# ── Project Ask Anything (RAG + project context) ──────────────────────────────

class ProjectAskRequest(BaseModel):
    question: str
    top_k: int = 8


@router.post("/{project_id}/ask")
async def project_ask(project_id: str, body: ProjectAskRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    RAG-powered Q&A with full project context:
    - ChromaDB semantic search (emails + Slack messages)
    - ClickUp tasks summary (if linked)
    - Project members + notes
    - Ollama generates the final answer
    """
    import datetime as _dt
    from intelligence.rag.retriever import retrieve
    from intelligence.rag.embedder import get_collection
    from core.config import settings

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    p = _project_or_404(db, project_id, current_user.org_id)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    notes   = db.query(ProjectNote).filter(ProjectNote.project_id == project_id).order_by(ProjectNote.created_at.desc()).limit(3).all()
    sources = db.query(ProjectSource).filter(ProjectSource.project_id == project_id).all()
    source_map = {s.source_type: s.config if isinstance(s.config, dict) else {} for s in sources}

    # ── 1. RAG — semantic search ───────────────────────────────
    col = get_collection()
    indexed = col.count() if col else 0
    rag_docs = retrieve(question, top_k=body.top_k) if indexed > 0 else []
    rag_docs = [d for d in rag_docs if d.score <= 0.75]

    # ── 2. ClickUp context ─────────────────────────────────────
    clickup_ctx = ""
    if "clickup" in source_map:
        try:
            resp = await clickup_summary(project_id, db)
            st = resp.get("stats", {})
            clickup_ctx = (
                f"ClickUp Tasks: {st.get('total',0)} total, {st.get('done',0)} done, "
                f"{st.get('open',0)} open, {st.get('urgent',0)} urgent, "
                f"{st.get('blocked',0)} blocked, {st.get('overdue',0)} overdue. "
                f"Progress: {st.get('progress',0)}%."
            )
        except Exception:
            pass

    # ── 3. Build prompt ────────────────────────────────────────
    member_str = ", ".join(f"{m.name} ({m.role})" for m in members) or "No members listed"
    notes_str  = "\n".join(f"- {n.content[:200]}" for n in notes) if notes else "No notes."
    source_str = ", ".join(source_map.keys()) if source_map else "none"

    rag_ctx = ""
    if rag_docs:
        parts = []
        for i, d in enumerate(rag_docs, 1):
            ts = d.timestamp[:10] if d.timestamp else "?"
            parts.append(
                f"[{i}] {d.source.upper()} | {d.author} | {ts}\n"
                f"Subject: {d.title}\n"
                f"Excerpt: {d.text[:400]}\n"
                f"Sentiment: {d.sentiment_label or 'N/A'} | Business: {d.business_label or 'N/A'}"
            )
        rag_ctx = "\n\n---\n".join(parts)
    else:
        rag_ctx = "No messages indexed yet for this project."

    prompt = f"""You are the AI assistant for a CEO. Your primary focus is the project "{p.name}".
Answer the CEO's question concisely and in the same language as the question.
Use bullet points when listing items. Cite sources with [1], [2]... only when they directly support your answer.

IMPORTANT: The messages below come from a GLOBAL semantic search (all emails/Slack).
They may or may not be specific to this project. Prioritize the PROJECT CONTEXT (ClickUp tasks, members)
over the messages. Only cite a message if it is clearly relevant to THIS project.

=== PROJECT CONTEXT (authoritative) ===
Project: {p.name}
Description: {p.description or 'N/A'}
Members: {member_str}
Connected sources: {source_str}
{clickup_ctx}

=== CEO NOTES ===
{notes_str}

=== MESSAGES (global search — may include content from other contexts) ===
{rag_ctx}

=== CEO QUESTION ===
{question}

=== ANSWER ==="""

    # ── 4. Call LLM (Ollama ou Azure GPT-4o) ──────────────────
    from intelligence.llm.client import complete as llm_complete
    try:
        answer = await llm_complete(
            system="You are the AI assistant for a CEO. Answer concisely in the same language as the question.",
            user=prompt,
            use_tools=False,
            temperature=0.3,
            max_tokens=500,
        )
    except Exception as e:
        answer = f"⚠️ LLM unavailable: {e}"

    sources_out = [
        {
            "id":        d.id,
            "source":    d.source,
            "title":     d.title or "(no subject)",
            "author":    d.author,
            "timestamp": d.timestamp[:10] if d.timestamp else "",
            "sentiment": d.sentiment_label,
            "excerpt":   d.text[:150] + "…",
            "url":       d.url or "",
        }
        for d in rag_docs[:5]
    ]

    return {
        "answer":        answer,
        "sources":       sources_out,
        "indexed_count": indexed,
        "question":      question,
    }
