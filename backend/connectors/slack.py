from datetime import datetime
from typing import Any

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

# Mock data — replace with real Slack Web API calls when you have a token
def _ts(iso: str) -> str:
    """Convert ISO date string to a Slack-style Unix timestamp string."""
    from datetime import timezone
    dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    return f"{dt.timestamp():.6f}"


MOCK_SLACK_MESSAGES = [
    {
        "ts": _ts("2026-04-01T08:00:00"),
        "channel": "C_GENERAL",
        "channel_name": "general",
        "user": "U_ALICE",
        "username": "alice",
        "text": "The Q1 report is ready, revenue is up 12% vs last quarter.",
        "permalink": "https://slack.com/archives/C_GENERAL/p1",
    },
    {
        "ts": _ts("2026-04-01T11:30:00"),
        "channel": "C_ENGINEERING",
        "channel_name": "engineering",
        "user": "U_BOB",
        "username": "bob",
        "text": "Production deploy failed — rolling back v2.4.1. Investigating now.",
        "permalink": "https://slack.com/archives/C_ENGINEERING/p2",
    },
    {
        "ts": _ts("2026-04-01T15:00:00"),
        "channel": "C_MARKETING",
        "channel_name": "marketing",
        "user": "U_CAROL",
        "username": "carol",
        "text": "Campaign launch delayed by two weeks due to asset approvals.",
        "permalink": "https://slack.com/archives/C_MARKETING/p3",
    },
]


@ConnectorRegistry.register(SourceType.SLACK)
class SlackConnector(BaseConnector):
    """
    Fetches messages from configured Slack channels.

    Config keys:
        token (str)         : Slack Bot OAuth token (xoxb-…)
        channel_ids (list)  : list of channel IDs to monitor
        use_mock (bool)     : use mock data instead of real API (default True)
    """

    async def authenticate(self) -> None:
        token = self.config.get("token")
        if not self.config.get("use_mock", True):
            if not token:
                raise ValueError("Slack token is required when use_mock=False")
            # TODO: call slack_sdk.WebClient(token=token).auth_test()
        self._authenticated = True

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        if self.config.get("use_mock", True):
            # Filter mock messages by timestamp
            cutoff = since.timestamp()
            return [m for m in MOCK_SLACK_MESSAGES if float(m["ts"]) >= cutoff]

        # TODO: real Slack API implementation
        # from slack_sdk.web.async_client import AsyncWebClient
        # client = AsyncWebClient(token=self.config["token"])
        # results = []
        # for channel_id in self.config.get("channel_ids", []):
        #     resp = await client.conversations_history(
        #         channel=channel_id, oldest=str(since.timestamp())
        #     )
        #     for msg in resp["messages"]:
        #         msg["channel"] = channel_id
        #         results.append(msg)
        # return results
        return []

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        ts = float(raw["ts"])
        return DataItem(
            id=f"slack_{raw['ts']}",
            source=SourceType.SLACK,
            type=ItemType.MESSAGE,
            title=f"#{raw.get('channel_name', raw.get('channel', 'unknown'))}",
            content=raw.get("text", ""),
            author=raw.get("username", raw.get("user", "unknown")),
            timestamp=datetime.utcfromtimestamp(ts),
            url=raw.get("permalink"),
            tags=[raw.get("channel_name", "")],
            raw=raw,
        )
