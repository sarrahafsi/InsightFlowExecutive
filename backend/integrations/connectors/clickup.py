"""
ClickUp Connector — InsightFlow Executive
==========================================
Uses the ClickUp REST API v2 with a personal API token.

Config keys (stored in source_configs table, source = "clickup"):
    api_token (str)   : ClickUp personal API token
    team_id   (str)   : ClickUp Workspace/Team ID (optional — auto-detected)
    space_ids (list)  : Space IDs to sync (optional — syncs all spaces)
    max_tasks (int)   : max tasks per list (default: 100)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

logger = logging.getLogger(__name__)

CLICKUP_API = "https://api.clickup.com/api/v2"

PRIORITY_MAP = {
    # numeric id (int or string)
    1: "Urgent", 2: "High", 3: "Normal", 4: "Low",
    "1": "Urgent", "2": "High", "3": "Normal", "4": "Low",
    # text label (lowercase)
    "urgent": "Urgent", "high": "High", "normal": "Normal", "low": "Low",
    None: "Normal",
}
STATUS_DONE  = {"complete", "done", "closed", "resolved"}


@ConnectorRegistry.register(SourceType.CLICKUP)
class ClickUpConnector(BaseConnector):

    def _load_db_config(self) -> dict | None:
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            org_id = self.config.get("org_id")
            db = SessionLocal()
            try:
                q = db.query(SourceConfig).filter(SourceConfig.source == "clickup")
                if org_id:
                    q = q.filter(SourceConfig.org_id == org_id)
                row = q.first()
                if row:
                    return row.config if isinstance(row.config, dict) else {}
            finally:
                db.close()
        except Exception:
            pass
        return None

    def _delete_stale_token(self) -> None:
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            org_id = self.config.get("org_id")
            db = SessionLocal()
            try:
                q = db.query(SourceConfig).filter(SourceConfig.source == "clickup")
                if org_id:
                    q = q.filter(SourceConfig.org_id == org_id)
                q.delete(synchronize_session=False)
                db.commit()
            finally:
                db.close()
        except Exception:
            pass

    def _get_token(self) -> str:
        # Priorité : config passée directement > DB
        if self.config.get("api_token"):
            return self.config["api_token"]
        db_cfg = self._load_db_config()
        if db_cfg and db_cfg.get("api_token"):
            return db_cfg["api_token"]
        return ""

    def _headers(self) -> dict:
        return {"Authorization": self._get_token(), "Content-Type": "application/json"}

    # ── Authenticate ────────────────────────────────────────────────────────────

    async def authenticate(self) -> None:
        token = self._get_token()
        if not token:
            # Not configured — skip silently (no crash, no error log)
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{CLICKUP_API}/user", headers=self._headers())
            if resp.status_code != 200:
                # Invalid/expired token — delete it from DB and skip silently
                self._delete_stale_token()
                logger.debug("[ClickUp] Token invalide supprimé — sync ignoré jusqu'à reconnexion")
                return  # _authenticated stays False → BaseConnector.sync() skips
            user = resp.json().get("user", {})
            logger.info("[ClickUp] Authenticated as: %s", user.get("username"))

        self._authenticated = True

    # ── Fetch raw ───────────────────────────────────────────────────────────────

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        db_cfg = self._load_db_config() or {}
        max_tasks = db_cfg.get("max_tasks", self.config.get("max_tasks", 100))

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Get all accessible teams (workspaces)
            team_ids = await self._get_team_ids(client, db_cfg)
            if not team_ids:
                logger.warning("[ClickUp] No teams found")
                return []

            all_tasks: list[dict] = []
            for team_id in team_ids:
                # 2. Get all spaces in this team
                space_ids = db_cfg.get("space_ids") or await self._get_space_ids(client, team_id)
                for space_id in space_ids:
                    # 3. Get all lists in every folder + folderless lists
                    list_ids = await self._get_list_ids(client, space_id)
                    for list_id in list_ids:
                        tasks = await self._fetch_tasks(client, list_id, since, max_tasks)
                        all_tasks.extend(tasks)

        logger.info("[ClickUp] %d tasks fetched total", len(all_tasks))
        return all_tasks

    async def _get_team_ids(self, client: httpx.AsyncClient, db_cfg: dict) -> list[str]:
        # Use stored team_id if available
        if db_cfg.get("team_id"):
            return [db_cfg["team_id"]]
        try:
            resp = await client.get(f"{CLICKUP_API}/team", headers=self._headers())
            resp.raise_for_status()
            teams = resp.json().get("teams", [])
            return [str(t["id"]) for t in teams]
        except Exception as e:
            logger.warning("[ClickUp] get teams error: %s", e)
            return []

    async def _get_space_ids(self, client: httpx.AsyncClient, team_id: str) -> list[str]:
        try:
            resp = await client.get(
                f"{CLICKUP_API}/team/{team_id}/space",
                headers=self._headers(),
                params={"archived": "false"},
            )
            resp.raise_for_status()
            spaces = resp.json().get("spaces", [])
            return [str(s["id"]) for s in spaces]
        except Exception as e:
            logger.warning("[ClickUp] get spaces error: %s", e)
            return []

    async def _get_list_ids(self, client: httpx.AsyncClient, space_id: str) -> list[str]:
        list_ids: list[str] = []
        try:
            # Folderless lists
            resp = await client.get(
                f"{CLICKUP_API}/space/{space_id}/list",
                headers=self._headers(),
                params={"archived": "false"},
            )
            if resp.status_code == 200:
                for lst in resp.json().get("lists", []):
                    list_ids.append(str(lst["id"]))

            # Lists inside folders
            resp2 = await client.get(
                f"{CLICKUP_API}/space/{space_id}/folder",
                headers=self._headers(),
                params={"archived": "false"},
            )
            if resp2.status_code == 200:
                for folder in resp2.json().get("folders", []):
                    for lst in folder.get("lists", []):
                        list_ids.append(str(lst["id"]))
        except Exception as e:
            logger.warning("[ClickUp] get lists error for space %s: %s", space_id, e)
        return list_ids

    async def _fetch_tasks(
        self, client: httpx.AsyncClient, list_id: str, since: datetime, max_tasks: int
    ) -> list[dict]:
        tasks: list[dict] = []
        page = 0
        since_ms = int(since.timestamp() * 1000)

        while len(tasks) < max_tasks:
            try:
                resp = await client.get(
                    f"{CLICKUP_API}/list/{list_id}/task",
                    headers=self._headers(),
                    params={
                        "page":          page,
                        "order_by":      "updated",
                        "reverse":       "true",
                        "include_closed": "true",
                        "date_updated_gt": since_ms,
                    },
                )
                if resp.status_code != 200:
                    break
                batch = resp.json().get("tasks", [])
                if not batch:
                    break
                tasks.extend(batch)
                if len(batch) < 100:  # ClickUp returns max 100 per page
                    break
                page += 1
            except Exception as e:
                logger.warning("[ClickUp] fetch tasks error list %s: %s", list_id, e)
                break

        return tasks[:max_tasks]

    # ── Normalize ───────────────────────────────────────────────────────────────

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        task_id   = raw.get("id", "unknown")
        title     = raw.get("name", "(no title)")
        content   = raw.get("description") or ""
        url       = raw.get("url", "")

        # Status
        status_obj = raw.get("status") or {}
        status     = status_obj.get("status", "unknown")
        is_done    = status_obj.get("type", "").lower() == "closed" or status.lower() in STATUS_DONE

        # Priority — ClickUp returns {"priority": "high", "id": "2", ...}
        priority_obj  = raw.get("priority") or {}
        priority_raw  = priority_obj.get("priority") or priority_obj.get("id")
        priority_name = PRIORITY_MAP.get(
            priority_raw.lower() if isinstance(priority_raw, str) else priority_raw,
            "Normal"
        )

        # Assignees
        assignees     = raw.get("assignees") or []
        assignee_name = assignees[0].get("username", "Unassigned") if assignees else "Unassigned"
        assignee_list = [a.get("username", "") for a in assignees]

        # Creator
        creator  = raw.get("creator") or {}
        reporter = creator.get("username", "Unknown")

        # List / Space
        list_obj  = raw.get("list") or {}
        list_name = list_obj.get("name", "")
        folder_obj  = raw.get("folder") or {}
        folder_name = folder_obj.get("name", "")
        space_obj   = raw.get("space") or {}
        space_name  = space_obj.get("name", "")

        # Tags
        tags = [t.get("name", "") for t in (raw.get("tags") or []) if t.get("name")]

        # Timestamps (ms → datetime)
        def _ms(val) -> datetime:
            try:
                return datetime.utcfromtimestamp(int(val) / 1000)
            except Exception:
                return datetime.utcnow()

        updated   = _ms(raw.get("date_updated") or raw.get("date_created"))
        created   = _ms(raw.get("date_created") or raw.get("date_updated"))
        due_dt    = _ms(raw.get("due_date")) if raw.get("due_date") else None

        # Custom fields
        custom_fields = raw.get("custom_fields") or []
        cf_dict = {cf.get("name", ""): cf.get("value") for cf in custom_fields}
        story_points = cf_dict.get("Story Points") or cf_dict.get("Points") or cf_dict.get("Estimation")

        content_full = f"{title}"
        if content:
            content_full += f"\n\n{content}"
        content_full += f"\n\nStatus: {status} | Priority: {priority_name}"
        if list_name:
            content_full += f" | List: {list_name}"
        if folder_name and folder_name != "hidden":
            content_full += f" | Folder: {folder_name}"

        return DataItem(
            id=f"clickup_{task_id}",
            source=SourceType.CLICKUP,
            type=ItemType.TICKET,
            title=title,
            content=content_full,
            author=assignee_name,
            timestamp=updated,
            url=url,
            tags=tags + [status, priority_name],
            metadata={
                "task_id":      task_id,
                "status":       status,
                "is_done":      is_done,
                "priority":     priority_name,
                "assignee":     assignee_name,
                "assignees":    assignee_list,
                "reporter":     reporter,
                "list_name":    list_name,
                "folder_name":  folder_name,
                "space_name":   space_name,
                "story_points": float(story_points) if story_points else None,
                "created":      created.isoformat(),
                "due_date":     due_dt.isoformat() if due_dt else None,
                "cycle_time_days": round((updated - created).total_seconds() / 86400, 1),
            },
            raw=raw,
        )
