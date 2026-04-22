"""
Jira Connector -- API reelle via Jira Agile REST API
=====================================================
Utilise l'API Board (agile/1.0) pour les projets Next-Gen Jira.

Config keys :
    base_url (str)        : ex: "https://sarahhafsi123.atlassian.net"
    email (str)           : email Atlassian
    api_token (str)       : Jira API token
    project_keys (list)   : ex: ["SCRUM"]
    max_results (int)     : limite par board (defaut: 50)
    use_mock (bool)       : forcer mock data (defaut: False)
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


@ConnectorRegistry.register(SourceType.JIRA)
class JiraConnector(BaseConnector):

    def _load_db_config(self) -> dict | None:
        """Charge les credentials depuis source_configs (saisis par le CEO dans l'onboarding)."""
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                row = db.query(SourceConfig).filter(SourceConfig.source == "jira").first()
                if row:
                    return row.config if isinstance(row.config, dict) else {}
            finally:
                db.close()
        except Exception:
            pass
        return None

    def _get_credentials(self) -> tuple[str, str, str]:
        db_cfg = self._load_db_config()
        if db_cfg and db_cfg.get("base_url") and db_cfg.get("api_token"):
            return db_cfg["base_url"].rstrip("/"), db_cfg["email"], db_cfg["api_token"]
        from core.config import settings
        base_url  = self.config.get("base_url")  or settings.jira_base_url
        email     = self.config.get("email")      or settings.jira_email
        api_token = self.config.get("api_token")  or settings.jira_api_token
        return base_url.rstrip("/"), email, api_token

    def _get_project_keys(self) -> list[str]:
        db_cfg = self._load_db_config()
        if db_cfg and db_cfg.get("project_keys"):
            keys = db_cfg["project_keys"]
            if isinstance(keys, list):
                return keys
            return [k.strip() for k in keys.split(",") if k.strip()]
        from core.config import settings
        keys = self.config.get("project_keys", [])
        if not keys:
            keys = [k.strip() for k in settings.jira_project_keys.split(",") if k.strip()]
        return keys

    # -- Authenticate --

    async def authenticate(self) -> None:
        if self.config.get("use_mock", False):
            self._authenticated = True
            return

        base_url, email, api_token = self._get_credentials()
        if not all([base_url, email, api_token]):
            raise ValueError("Jira base_url, email et api_token sont requis dans .env")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{base_url}/rest/api/3/myself",
                    auth=(email, api_token),
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                user = resp.json()
                logger.info("[Jira] Authentifie : %s", user.get("displayName"))
        except Exception as e:
            raise ValueError(f"Impossible de s'authentifier a Jira : {e}")

        self._authenticated = True

    # -- Fetch raw --

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        if self.config.get("use_mock", False):
            return []

        base_url, email, api_token = self._get_credentials()
        project_keys = self._get_project_keys()
        max_results = self.config.get("max_results", 50)

        all_issues: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for project_key in project_keys:
                # Etape 1 : recuperer les issues via JQL (API standard — champs complets garantis)
                issues = await self._fetch_jql_issues(client, base_url, email, api_token, project_key, max_results)

                # Etape 2 : enrichir les story points depuis les sprints (Agile API)
                board_id = await self._get_board_id(client, base_url, email, api_token, project_key)
                if board_id:
                    sp_lookup = await self._fetch_sprint_story_points(client, base_url, email, api_token, board_id, max_results)
                    for issue in issues:
                        key = issue.get("key", "")
                        fields_dict = issue.setdefault("fields", {})
                        if key in sp_lookup and sp_lookup[key] is not None:
                            fields_dict["customfield_10016"] = sp_lookup[key]
                        itype = sp_lookup.get(f"__type_{key}")
                        if itype and not (fields_dict.get("issuetype") or {}).get("name"):
                            fields_dict["issuetype"] = {"name": itype}

                # Etape 3 : filtrer par date
                filtered = []
                for issue in issues:
                    updated_str = issue.get("fields", {}).get("updated", "")
                    try:
                        updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if updated >= since:
                            filtered.append(issue)
                    except Exception:
                        filtered.append(issue)

                logger.info("[Jira] %d issues pour le projet %s", len(filtered), project_key)
                all_issues.extend(filtered)

        return all_issues

    async def _fetch_sprint_story_points(self, client, base_url, email, api_token, board_id, max_results) -> dict:
        """Fetch story points from all sprints (active + closed)."""
        sp_lookup: dict = {}
        try:
            # Get all sprints for this board
            resp = await client.get(
                f"{base_url}/rest/agile/1.0/board/{board_id}/sprint",
                params={"maxResults": 50},
                auth=(email, api_token),
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return sp_lookup
            sprints = resp.json().get("values", [])
            for sprint in sprints:
                sprint_id = sprint["id"]
                try:
                    resp2 = await client.get(
                        f"{base_url}/rest/agile/1.0/sprint/{sprint_id}/issue",
                        params={"maxResults": max_results, "fields": "customfield_10016,issuetype"},
                        auth=(email, api_token),
                        headers={"Accept": "application/json"},
                    )
                    if resp2.status_code == 200:
                        for issue in resp2.json().get("issues", []):
                            key = issue.get("key", "")
                            sp = issue.get("fields", {}).get("customfield_10016")
                            if key and sp is not None:
                                sp_lookup[key] = sp
                            # Also enrich issuetype
                            itype = (issue.get("fields", {}).get("issuetype") or {}).get("name")
                            if itype:
                                sp_lookup[f"__type_{key}"] = itype
                except Exception as e:
                    logger.warning("[Jira] Erreur fetch sprint %d issues : %s", sprint_id, e)
        except Exception as e:
            logger.warning("[Jira] Erreur fetch sprints : %s", e)
        return sp_lookup

    async def _fetch_jql_issues(self, client, base_url, email, api_token, project_key, max_results) -> list[dict]:
        """
        Fetch issues via the standard Jira REST API (JQL search).
        This always returns fully populated fields (status, priority, issuetype, etc.)
        regardless of board type (classic or team-managed).
        """
        issues: list[dict] = []
        start_at = 0
        batch_size = min(max_results, 100)
        fields = "summary,description,status,priority,assignee,reporter,created,updated,labels,issuetype,customfield_10016"

        while len(issues) < max_results:
            try:
                resp = await client.get(
                    f"{base_url}/rest/api/3/search/jql",
                    params={
                        "jql": f"project={project_key} ORDER BY updated DESC",
                        "maxResults": batch_size,
                        "startAt": start_at,
                        "fields": fields,
                    },
                    auth=(email, api_token),
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                batch = data.get("issues", [])
                issues.extend(batch)
                if len(batch) < batch_size:
                    break
                start_at += len(batch)
            except Exception as e:
                logger.warning("[Jira] Erreur JQL search pour %s : %s", project_key, e)
                break

        return issues[:max_results]

    async def _get_board_id(self, client, base_url, email, api_token, project_key) -> int | None:
        try:
            resp = await client.get(
                f"{base_url}/rest/agile/1.0/board",
                params={"projectKeyOrId": project_key},
                auth=(email, api_token),
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            boards = resp.json().get("values", [])
            return boards[0]["id"] if boards else None
        except Exception as e:
            logger.warning("[Jira] Erreur get board : %s", e)
            return None

    # -- Normalize --

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        fields   = raw.get("fields", {})
        key      = raw.get("key", "UNKNOWN")
        base_url, _, _ = self._get_credentials()

        summary    = fields.get("summary", "(sans titre)")
        status     = (fields.get("status") or {}).get("name", "Unknown")
        priority   = (fields.get("priority") or {}).get("name", "Medium")
        labels     = fields.get("labels", [])
        issue_type = (fields.get("issuetype") or {}).get("name", "Task")
        story_points = fields.get("customfield_10016") or fields.get("story_points")

        assignee_obj   = fields.get("assignee") or {}
        assignee_name  = assignee_obj.get("displayName") or assignee_obj.get("emailAddress") or "Non assigne"
        assignee_email = assignee_obj.get("emailAddress", "")

        reporter_obj  = fields.get("reporter") or {}
        reporter_name = reporter_obj.get("displayName") or "Unknown"

        description = self._extract_description(fields.get("description"))

        updated_str = fields.get("updated", "")
        created_str = fields.get("created", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            updated = datetime.utcnow()
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            created = updated

        content = f"{summary}\n\n{description}\n\nStatut: {status} | Priorite: {priority} | Type: {issue_type}"
        if labels:
            content += f" | Labels: {', '.join(labels)}"

        return DataItem(
            id=f"jira_{key}",
            source=SourceType.JIRA,
            type=ItemType.TICKET,
            title=f"[{key}] {summary}",
            content=content,
            author=assignee_name,
            timestamp=updated,
            url=f"{base_url}/browse/{key}",
            tags=labels + [status, priority, issue_type],
            metadata={
                "key":           key,
                "status":        status,
                "priority":      priority,
                "issue_type":    issue_type,
                "story_points":  float(story_points) if story_points else None,
                "assignee":      assignee_email,
                "assignee_name": assignee_name,
                "reporter":      reporter_name,
                "created":       created_str,
                "cycle_time_days": round((updated - created).total_seconds() / 86400, 1),
            },
            raw=raw,
        )

    @staticmethod
    def _extract_description(desc: Any) -> str:
        if not desc:
            return ""
        if isinstance(desc, str):
            return desc
        texts = []
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    texts.append(node.get("text", ""))
                for child in node.get("content", []):
                    walk(child)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(desc)
        return " ".join(texts).strip()
