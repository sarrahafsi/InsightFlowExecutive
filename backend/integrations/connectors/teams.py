"""
Microsoft Teams Connector — Microsoft Graph API
===============================================
Fetches channel messages and chat messages from Microsoft Teams.

Config keys:
    use_mock (bool)       : Return mock data (default: True)
    max_messages (int)    : Max messages per channel (default: 50)
    team_ids (list)       : Specific team IDs to monitor (default: all joined teams)

Authentication:
    Token stored in source_configs DB table with source="teams".
    Scopes: ChannelMessage.Read.All Team.ReadBasic.All Channel.ReadBasic.All offline_access
    Run GET /auth/teams to start the OAuth flow.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.microsoft.com/v1.0"

MOCK_MESSAGES = [
    {
        "id": "teams_msg_001",
        "createdDateTime": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
        "from": {"user": {"displayName": "Marie Dupont"}},
        "body": {"content": "Budget Q2 approuvé par le comité de direction. Nous avons 15% de marge supplémentaire — à allouer sur R&D et recrutement.", "contentType": "text"},
        "team_name": "Finance",
        "channel_name": "budget-review",
        "team_id": "team_finance",
        "channel_id": "chan_budget",
        "subject": "Budget Q2 approuvé",
        "importance": "high",
        "webUrl": "",
    },
    {
        "id": "teams_msg_002",
        "createdDateTime": (datetime.utcnow() - timedelta(hours=3)).isoformat() + "Z",
        "from": {"user": {"displayName": "Ahmed Ben Ali"}},
        "body": {"content": "URGENT — Client Renault bloque la livraison Sprint 7. Ils demandent une réunion avec le CEO avant vendredi.", "contentType": "text"},
        "team_name": "Direction",
        "channel_name": "escalades",
        "team_id": "team_direction",
        "channel_id": "chan_escalades",
        "subject": "Escalade client Renault",
        "importance": "urgent",
        "webUrl": "",
    },
    {
        "id": "teams_msg_003",
        "createdDateTime": (datetime.utcnow() - timedelta(hours=5)).isoformat() + "Z",
        "from": {"user": {"displayName": "Sophie Martin"}},
        "body": {"content": "Rapport hebdo : 3 développeurs signalent une surcharge critique. Sprints 2 semaines de retard sur le planning initial. Besoin d'arbitrage.", "contentType": "text"},
        "team_name": "Tech",
        "channel_name": "general",
        "team_id": "team_tech",
        "channel_id": "chan_general",
        "subject": "Surcharge équipe Dev",
        "importance": "high",
        "webUrl": "",
    },
    {
        "id": "teams_msg_004",
        "createdDateTime": (datetime.utcnow() - timedelta(hours=8)).isoformat() + "Z",
        "from": {"user": {"displayName": "Karim Haddad"}},
        "body": {"content": "Partenariat signé avec TechCorp. Contrat 18 mois, 450K€. Kick-off prévu le 15. Excellentes nouvelles pour le Q3.", "contentType": "text"},
        "team_name": "Business Dev",
        "channel_name": "deals",
        "team_id": "team_bd",
        "channel_id": "chan_deals",
        "subject": "Partenariat TechCorp signé",
        "importance": "normal",
        "webUrl": "",
    },
    {
        "id": "teams_msg_005",
        "createdDateTime": (datetime.utcnow() - timedelta(hours=12)).isoformat() + "Z",
        "from": {"user": {"displayName": "Leila Mansouri"}},
        "body": {"content": "Infrastructure cloud : pic à 94% de capacité hier soir. On risque une panne si on ne scale pas avant la semaine prochaine. Devis AWS joint.", "contentType": "text"},
        "team_name": "Tech",
        "channel_name": "infra",
        "team_id": "team_tech",
        "channel_id": "chan_infra",
        "subject": "Alerte capacité cloud",
        "importance": "urgent",
        "webUrl": "",
    },
    {
        "id": "teams_msg_006",
        "createdDateTime": (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z",
        "from": {"user": {"displayName": "Pierre Leblanc"}},
        "body": {"content": "Onboarding de 5 nouveaux consultants cette semaine. Processus RH bien rodé. Ambiance positive, tous opérationnels dès lundi.", "contentType": "text"},
        "team_name": "RH",
        "channel_name": "recrutement",
        "team_id": "team_rh",
        "channel_id": "chan_recrut",
        "subject": "Onboarding semaine 16",
        "importance": "normal",
        "webUrl": "",
    },
    {
        "id": "teams_msg_007",
        "createdDateTime": (datetime.utcnow() - timedelta(days=1, hours=3)).isoformat() + "Z",
        "from": {"user": {"displayName": "Nadia Cherkaoui"}},
        "body": {"content": "Audit sécurité terminé. 2 vulnérabilités critiques identifiées sur l'API publique. Patch en cours, délai max 48h selon l'équipe.", "contentType": "text"},
        "team_name": "Tech",
        "channel_name": "securite",
        "team_id": "team_tech",
        "channel_id": "chan_sec",
        "subject": "Résultats audit sécurité",
        "importance": "urgent",
        "webUrl": "",
    },
    {
        "id": "teams_msg_008",
        "createdDateTime": (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z",
        "from": {"user": {"displayName": "Thomas Richard"}},
        "body": {"content": "NPS du trimestre : 72 (vs 65 le trimestre dernier). Satisfaction client en nette progression. Témoignages positifs sur la réactivité du support.", "contentType": "text"},
        "team_name": "Customer Success",
        "channel_name": "kpis",
        "team_id": "team_cs",
        "channel_id": "chan_kpis",
        "subject": "NPS Q1 — résultats",
        "importance": "normal",
        "webUrl": "",
    },
]


@ConnectorRegistry.register(SourceType.TEAMS)
class TeamsConnector(BaseConnector):

    _token_cache: str | None = None

    def _load_token_from_db(self) -> dict | None:
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                row = db.query(SourceConfig).filter(SourceConfig.source == "teams").first()
                if row:
                    return row.config if isinstance(row.config, dict) else json.loads(row.config)
            finally:
                db.close()
        except Exception as e:
            logger.warning("[Teams] Cannot load token from DB: %s", e)
        return None

    def _save_token_to_db(self, token_data: dict) -> None:
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                row = db.query(SourceConfig).filter(SourceConfig.source == "teams").first()
                if row:
                    row.config = token_data
                else:
                    db.add(SourceConfig(source="teams", config=token_data))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("[Teams] Cannot save token to DB: %s", e)

    async def _refresh_token(self, refresh_token: str) -> str | None:
        from core.config import settings
        tenant = settings.teams_tenant or "common"
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(token_url, data={
                    "client_id":     settings.teams_client_id,
                    "client_secret": settings.teams_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type":    "refresh_token",
                    "scope":         "ChannelMessage.Read.All Team.ReadBasic.All Channel.ReadBasic.All Chat.Read offline_access",
                })
                if resp.status_code == 200:
                    tokens = resp.json()
                    token_data = {
                        "access_token":  tokens.get("access_token"),
                        "refresh_token": tokens.get("refresh_token", refresh_token),
                        "expires_in":    tokens.get("expires_in", 3600),
                        "refreshed_at":  datetime.utcnow().isoformat(),
                    }
                    self._save_token_to_db(token_data)
                    return token_data["access_token"]
                logger.warning("[Teams] Token refresh failed: %s %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("[Teams] Token refresh error: %s", e)
        return None

    async def _get_access_token(self) -> str | None:
        cfg = self._load_token_from_db()
        if not cfg:
            return None
        access_token = cfg.get("access_token")
        refresh_token_val = cfg.get("refresh_token")
        refreshed_at = cfg.get("refreshed_at")
        expires_in = cfg.get("expires_in", 3600)

        if refreshed_at:
            age = (datetime.utcnow() - datetime.fromisoformat(refreshed_at)).total_seconds()
            if age > expires_in - 300 and refresh_token_val:
                logger.info("[Teams] Token expired, refreshing…")
                new_token = await self._refresh_token(refresh_token_val)
                if new_token:
                    return new_token

        return access_token

    # ── Authenticate ─────────────────────────────────────────────

    async def authenticate(self) -> None:
        if self.config.get("use_mock", True):
            self._authenticated = True
            return

        token = await self._get_access_token()
        if not token:
            raise ValueError(
                "Teams token manquant. Lance le flow OAuth via GET /auth/teams"
            )
        self._token_cache = token
        self._authenticated = True

    # ── Fetch raw ─────────────────────────────────────────────────

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        if self.config.get("use_mock", True):
            cutoff = since.replace(tzinfo=None)
            return [
                m for m in MOCK_MESSAGES
                if datetime.fromisoformat(m["createdDateTime"].rstrip("Z")) >= cutoff
            ]

        token = self._token_cache or await self._get_access_token()
        if not token:
            logger.warning("[Teams] No access token — returning empty")
            return []

        headers = {"Authorization": f"Bearer {token}"}
        max_msg = self.config.get("max_messages", 50)
        team_ids = self.config.get("team_ids", [])
        messages: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            if not team_ids:
                team_ids = await self._list_teams(client, headers)

            for team_id in team_ids[:10]:
                team_name = team_id
                try:
                    r = await client.get(f"{GRAPH_API}/teams/{team_id}", headers=headers)
                    if r.status_code == 200:
                        team_name = r.json().get("displayName", team_id)
                except Exception:
                    pass

                channels = await self._list_channels(client, headers, team_id)
                for chan in channels[:20]:
                    chan_msgs = await self._fetch_channel_messages(
                        client, headers, team_id, chan["id"], chan.get("displayName", ""),
                        team_name, since, max_msg,
                    )
                    messages.extend(chan_msgs)

        logger.info("[Teams] %d messages fetched from %d teams", len(messages), len(team_ids))
        return messages

    async def _list_teams(self, client: httpx.AsyncClient, headers: dict) -> list[str]:
        try:
            r = await client.get(f"{GRAPH_API}/me/joinedTeams", headers=headers)
            if r.status_code == 200:
                return [t["id"] for t in r.json().get("value", [])]
            logger.warning("[Teams] joinedTeams failed: %s", r.status_code)
        except Exception as e:
            logger.warning("[Teams] Error listing teams: %s", e)
        return []

    async def _list_channels(self, client: httpx.AsyncClient, headers: dict, team_id: str) -> list[dict]:
        try:
            r = await client.get(f"{GRAPH_API}/teams/{team_id}/channels", headers=headers)
            if r.status_code == 200:
                return r.json().get("value", [])
            logger.warning("[Teams] channels failed for %s: %s", team_id, r.status_code)
        except Exception as e:
            logger.warning("[Teams] Error listing channels for %s: %s", team_id, e)
        return []

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        team_id: str,
        channel_id: str,
        channel_name: str,
        team_name: str,
        since: datetime,
        limit: int,
    ) -> list[dict]:
        try:
            since_iso = since.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            r = await client.get(
                f"{GRAPH_API}/teams/{team_id}/channels/{channel_id}/messages",
                headers=headers,
                params={
                    "$top": limit,
                    "$filter": f"createdDateTime ge {since_iso}",
                    "$orderby": "createdDateTime desc",
                },
            )
            if r.status_code != 200:
                logger.debug("[Teams] messages %s/%s → %s", team_id, channel_id, r.status_code)
                return []

            msgs = []
            for msg in r.json().get("value", []):
                if msg.get("messageType") != "message":
                    continue
                body_content = (msg.get("body") or {}).get("content", "")
                if not body_content.strip():
                    continue
                msg["team_name"] = team_name
                msg["channel_name"] = channel_name
                msg["team_id"] = team_id
                msg["channel_id"] = channel_id
                msgs.append(msg)
            return msgs

        except Exception as e:
            logger.warning("[Teams] Error fetching messages %s/%s: %s", team_id, channel_id, e)
            return []

    # ── Normalize ─────────────────────────────────────────────────

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        from_user = (raw.get("from") or {}).get("user") or {}
        author = from_user.get("displayName") or from_user.get("email") or "unknown"

        body = raw.get("body") or {}
        content = body.get("content", "")
        if body.get("contentType") == "html":
            import re
            content = re.sub(r"<[^>]+>", " ", content).strip()

        ts_str = raw.get("createdDateTime", "")
        try:
            timestamp = datetime.fromisoformat(ts_str.rstrip("Z"))
        except Exception:
            timestamp = datetime.utcnow()

        team_name = raw.get("team_name", "")
        channel_name = raw.get("channel_name", "")
        title = raw.get("subject") or f"#{channel_name}" or f"Teams — {team_name}"

        importance = raw.get("importance", "normal")
        tags = [team_name, channel_name] if team_name else [channel_name]
        if importance in ("urgent", "high"):
            tags.append(importance)

        return DataItem(
            id=f"teams_{raw['id']}",
            source=SourceType.TEAMS,
            type=ItemType.MESSAGE,
            title=title,
            content=content,
            author=author,
            timestamp=timestamp,
            url=raw.get("webUrl", ""),
            tags=[t for t in tags if t],
            metadata={
                "team_id":      raw.get("team_id", ""),
                "team_name":    team_name,
                "channel_id":   raw.get("channel_id", ""),
                "channel_name": channel_name,
                "importance":   importance,
                "message_type": raw.get("messageType", "message"),
            },
            raw=raw,
        )
