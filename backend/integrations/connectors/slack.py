"""
Slack Connector — API réelle via slack-sdk
==========================================
Récupère les messages des canaux publics auxquels le bot est invité.

Config keys (dans ConnectorManager / .env) :
    token (str)          : Bot OAuth token (xoxb-...) — lu depuis settings si absent
    channel_ids (list)   : IDs de canaux à monitorer (ex: ["C12345", "C67890"])
                           Si vide → on liste automatiquement tous les canaux publics
    max_messages (int)   : Limite par canal (défaut : 50)
    use_mock (bool)      : Forcer mock data (défaut : False)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

logger = logging.getLogger(__name__)


@ConnectorRegistry.register(SourceType.SLACK)
class SlackConnector(BaseConnector):

    # Cache username → display name pour éviter N appels API
    _user_cache: dict[str, str] = {}

    def _get_token(self) -> str:
        token = self.config.get("token", "")
        if not token:
            from core.config import settings
            token = settings.slack_bot_token
        return token

    def _get_client(self):
        from slack_sdk import WebClient
        return WebClient(token=self._get_token())

    # ── Authenticate ──────────────────────────────────────────

    async def authenticate(self) -> None:
        if self.config.get("use_mock", False):
            self._authenticated = True
            return

        token = self._get_token()
        if not token:
            raise ValueError("Slack bot token manquant — ajoute SLACK_BOT_TOKEN dans .env")

        try:
            client = self._get_client()
            resp = client.auth_test()
            if not resp["ok"]:
                raise ValueError(f"Slack auth_test failed : {resp.get('error')}")
            logger.info("[Slack] Authentifié en tant que bot : %s (workspace : %s)",
                        resp.get("bot_id"), resp.get("team"))
        except Exception as e:
            raise ValueError(f"Impossible de s'authentifier à Slack : {e}")

        self._authenticated = True

    # ── Fetch raw ─────────────────────────────────────────────

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        if self.config.get("use_mock", False):
            return []

        client = self._get_client()
        oldest = str(since.replace(tzinfo=timezone.utc).timestamp())
        max_msg = self.config.get("max_messages", 50)

        # Déterminer les canaux à monitorer
        channel_ids = self.config.get("channel_ids", [])
        if not channel_ids:
            channel_ids = self._list_public_channels(client)

        messages: list[dict[str, Any]] = []
        for channel_id in channel_ids:
            channel_msgs = self._fetch_channel(client, channel_id, oldest, max_msg)
            messages.extend(channel_msgs)

        logger.info("[Slack] %d messages récupérés depuis %d canaux.", len(messages), len(channel_ids))
        return messages

    def _list_public_channels(self, client) -> list[str]:
        """Liste tous les canaux publics auxquels le bot a accès."""
        try:
            resp = client.conversations_list(
                types="public_channel",
                exclude_archived=True,
                limit=200,
            )
            channels = resp.get("channels", [])
            ids = [c["id"] for c in channels if not c.get("is_archived")]
            logger.info("[Slack] %d canaux publics trouvés.", len(ids))
            return ids
        except Exception as e:
            logger.warning("[Slack] Impossible de lister les canaux : %s", e)
            return []

    def _fetch_channel(self, client, channel_id: str, oldest: str, limit: int) -> list[dict]:
        """Récupère les messages d'un canal depuis `oldest`."""
        try:
            resp = client.conversations_history(
                channel=channel_id,
                oldest=oldest,
                limit=limit,
            )
            if not resp["ok"]:
                logger.warning("[Slack] conversations_history failed pour %s : %s",
                               channel_id, resp.get("error"))
                return []

            # Résoudre le nom du canal
            try:
                info = client.conversations_info(channel=channel_id)
                channel_name = info["channel"].get("name", channel_id)
            except Exception:
                channel_name = channel_id

            msgs = []
            for msg in resp.get("messages", []):
                # Ignorer les messages système / bot
                if msg.get("subtype") in ("channel_join", "channel_leave", "bot_message"):
                    continue
                if not msg.get("text", "").strip():
                    continue

                msg["channel"] = channel_id
                msg["channel_name"] = channel_name
                msg["username"] = self._resolve_username(client, msg.get("user", ""))
                msgs.append(msg)

            return msgs

        except Exception as e:
            logger.warning("[Slack] Erreur fetch canal %s : %s", channel_id, e)
            return []

    def _resolve_username(self, client, user_id: str) -> str:
        """Résout un user_id Slack en nom d'affichage (avec cache)."""
        if not user_id:
            return "unknown"
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            resp = client.users_info(user=user_id)
            profile = resp["user"].get("profile", {})
            name = (
                profile.get("display_name")
                or profile.get("real_name")
                or resp["user"].get("name")
                or user_id
            )
            self._user_cache[user_id] = name
            return name
        except Exception:
            self._user_cache[user_id] = user_id
            return user_id

    # ── Normalize ─────────────────────────────────────────────

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        ts_float = float(raw["ts"])
        timestamp = datetime.utcfromtimestamp(ts_float)
        channel_name = raw.get("channel_name", raw.get("channel", "unknown"))

        return DataItem(
            id=f"slack_{raw['ts']}_{raw.get('channel', '')}",
            source=SourceType.SLACK,
            type=ItemType.MESSAGE,
            title=f"#{channel_name}",
            content=raw.get("text", ""),
            author=raw.get("username", raw.get("user", "unknown")),
            timestamp=timestamp,
            url=raw.get("permalink", ""),
            tags=[channel_name],
            metadata={
                "channel_id":   raw.get("channel"),
                "channel_name": channel_name,
                "user_id":      raw.get("user"),
                "thread_ts":    raw.get("thread_ts"),
            },
            raw=raw,
        )
