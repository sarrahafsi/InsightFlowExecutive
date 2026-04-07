from datetime import datetime
from typing import Any

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

MOCK_JIRA_ISSUES = [
    {
        "key": "PROJ-142",
        "summary": "API rate limiting not working under load",
        "description": "Under 500 concurrent users the rate limiter fails to throttle correctly, causing downstream service overload.",
        "status": "In Progress",
        "priority": "High",
        "assignee": "bob@company.com",
        "assignee_name": "Bob",
        "reporter": "alice@company.com",
        "created": "2026-03-28T10:00:00Z",
        "updated": "2026-04-01T16:30:00Z",
        "labels": ["backend", "performance"],
        "url": "https://jira.company.com/browse/PROJ-142",
    },
    {
        "key": "PROJ-138",
        "summary": "Dashboard load time exceeds 5 seconds for large datasets",
        "description": "The executive dashboard takes 5-8 seconds to load when the dataset exceeds 100k rows.",
        "status": "Open",
        "priority": "Medium",
        "assignee": "carol@company.com",
        "assignee_name": "Carol",
        "reporter": "ceo@company.com",
        "created": "2026-03-25T09:00:00Z",
        "updated": "2026-03-30T11:00:00Z",
        "labels": ["frontend", "performance"],
        "url": "https://jira.company.com/browse/PROJ-138",
    },
    {
        "key": "MKTG-55",
        "summary": "Q2 campaign assets — approval blocked",
        "description": "Legal has not approved the Q2 campaign assets. Launch date at risk.",
        "status": "Blocked",
        "priority": "High",
        "assignee": "carol@company.com",
        "assignee_name": "Carol",
        "reporter": "vp_marketing@company.com",
        "created": "2026-03-20T08:00:00Z",
        "updated": "2026-04-01T09:00:00Z",
        "labels": ["marketing", "blocked"],
        "url": "https://jira.company.com/browse/MKTG-55",
    },
]


@ConnectorRegistry.register(SourceType.JIRA)
class JiraConnector(BaseConnector):
    """
    Fetches issues from a Jira project.

    Config keys:
        base_url (str)   : e.g. "https://yourcompany.atlassian.net"
        email (str)      : Atlassian account email
        api_token (str)  : Jira API token
        project_keys (list[str]) : e.g. ["PROJ", "MKTG"]
        use_mock (bool)  : use mock data (default True)
    """

    async def authenticate(self) -> None:
        if not self.config.get("use_mock", True):
            if not self.config.get("api_token"):
                raise ValueError("Jira api_token is required when use_mock=False")
            # TODO: validate credentials with a /rest/api/3/myself call
        self._authenticated = True

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        if self.config.get("use_mock", True):
            return [
                issue for issue in MOCK_JIRA_ISSUES
                if datetime.fromisoformat(issue["updated"].replace("Z", "+00:00")).replace(tzinfo=None) >= since
            ]

        # TODO: real Jira API
        # import httpx
        # jql = (
        #     f"project in ({','.join(self.config['project_keys'])}) "
        #     f"AND updated >= '{since.strftime('%Y-%m-%d %H:%M')}' "
        #     f"ORDER BY updated DESC"
        # )
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         f"{self.config['base_url']}/rest/api/3/search",
        #         params={"jql": jql, "maxResults": 100},
        #         auth=(self.config["email"], self.config["api_token"]),
        #     )
        #     resp.raise_for_status()
        #     return resp.json()["issues"]
        return []

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        updated = datetime.fromisoformat(raw["updated"].replace("Z", "+00:00")).replace(tzinfo=None)
        return DataItem(
            id=f"jira_{raw['key']}",
            source=SourceType.JIRA,
            type=ItemType.TICKET,
            title=f"[{raw['key']}] {raw['summary']}",
            content=raw.get("description", ""),
            author=raw.get("assignee_name", raw.get("assignee", "unassigned")),
            timestamp=updated,
            url=raw.get("url"),
            tags=raw.get("labels", []) + [raw.get("status", ""), raw.get("priority", "")],
            metadata={
                "key": raw["key"],
                "status": raw.get("status"),
                "priority": raw.get("priority"),
                "assignee": raw.get("assignee"),
            },
            raw=raw,
        )
