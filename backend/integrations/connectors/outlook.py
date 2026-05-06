"""
Microsoft Outlook Mail Connector — Microsoft Graph API
======================================================
Fetches emails from the user's Outlook mailbox.

Config keys:
    max_emails (int)  : Max emails to fetch (default: 100)

Authentication:
    Token stored in source_configs DB table with source="outlook".
    Scopes: Mail.Read offline_access
    Run GET /auth/outlook/connect to start the OAuth flow.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.microsoft.com/v1.0"

MOCK_EMAILS = [
    {
        "id": "outlook_mock_001",
        "subject": "Budget Q2 — Validation direction requise",
        "from": {"emailAddress": {"name": "Marie Dupont", "address": "m.dupont@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
        "bodyPreview": "Le comité finance demande votre validation pour les 450K€ d'investissement R&D Q2 avant vendredi.",
        "body": {"contentType": "text", "content": "Le comité finance demande votre validation pour les 450K€ d'investissement R&D Q2 avant vendredi. Sans réponse, le budget sera gelé."},
        "importance": "high", "isRead": False, "hasAttachments": True, "webLink": "", "conversationId": "conv_001",
    },
    {
        "id": "outlook_mock_002",
        "subject": "URGENT — Escalade client Renault",
        "from": {"emailAddress": {"name": "Ahmed Ben Ali", "address": "a.benali@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=5)).isoformat() + "Z",
        "bodyPreview": "Le client Renault bloque la livraison Sprint 7. Ils demandent une réunion avec vous avant vendredi.",
        "body": {"contentType": "text", "content": "Le client Renault bloque la livraison Sprint 7. Ils demandent une réunion avec le CEO avant vendredi. Risque de résiliation du contrat 600K€."},
        "importance": "urgent", "isRead": False, "hasAttachments": False, "webLink": "", "conversationId": "conv_002",
    },
    {
        "id": "outlook_mock_003",
        "subject": "Rapport hebdo — Surcharge équipe Tech",
        "from": {"emailAddress": {"name": "Sophie Martin", "address": "s.martin@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=10)).isoformat() + "Z",
        "bodyPreview": "3 développeurs signalent une surcharge critique. Sprints 2 semaines de retard sur le planning.",
        "body": {"contentType": "text", "content": "3 développeurs signalent une surcharge critique. Sprints 2 semaines de retard sur le planning initial. Besoin d'arbitrage urgentement."},
        "importance": "high", "isRead": True, "hasAttachments": False, "webLink": "", "conversationId": "conv_003",
    },
    {
        "id": "outlook_mock_004",
        "subject": "Partenariat TechCorp — Contrat signé",
        "from": {"emailAddress": {"name": "Karim Haddad", "address": "k.haddad@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=15)).isoformat() + "Z",
        "bodyPreview": "Partenariat signé avec TechCorp. Contrat 18 mois, 450K€. Kick-off prévu le 15.",
        "body": {"contentType": "text", "content": "Partenariat signé avec TechCorp. Contrat 18 mois, 450K€. Kick-off prévu le 15. Excellentes nouvelles pour le Q3."},
        "importance": "normal", "isRead": True, "hasAttachments": True, "webLink": "", "conversationId": "conv_004",
    },
    {
        "id": "outlook_mock_005",
        "subject": "Réunion stratégique Q3 — Ordre du jour",
        "from": {"emailAddress": {"name": "Léa Fontaine", "address": "l.fontaine@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z",
        "bodyPreview": "OJ pour la réunion stratégique Q3 : expansion MENA, recrutement 12 profils seniors, roadmap produit.",
        "body": {"contentType": "text", "content": "OJ pour la réunion stratégique Q3 : expansion MENA, recrutement 12 profils seniors, roadmap produit 2027."},
        "importance": "normal", "isRead": True, "hasAttachments": True, "webLink": "", "conversationId": "conv_005",
    },
    {
        "id": "outlook_mock_006",
        "subject": "Alerte sécurité — Accès suspect détecté",
        "from": {"emailAddress": {"name": "IT Security", "address": "security@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=28)).isoformat() + "Z",
        "bodyPreview": "Accès suspect depuis une IP non reconnue sur votre compte. Changement de mot de passe recommandé.",
        "body": {"contentType": "text", "content": "Accès suspect depuis une IP non reconnue (45.82.x.x) sur votre compte à 03h14. Changement de mot de passe recommandé immédiatement."},
        "importance": "high", "isRead": False, "hasAttachments": False, "webLink": "", "conversationId": "conv_006",
    },
    {
        "id": "outlook_mock_007",
        "subject": "Feedback investisseurs — Post-présentation",
        "from": {"emailAddress": {"name": "Pierre Leblanc", "address": "p.leblanc@vc-fund.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=36)).isoformat() + "Z",
        "bodyPreview": "Excellente présentation. Notre comité d'investissement se réunit mardi. Term sheet attendue sous 10 jours.",
        "body": {"contentType": "text", "content": "Excellente présentation hier. Notre comité d'investissement se réunit mardi prochain. Term sheet attendue sous 10 jours si vote favorable."},
        "importance": "normal", "isRead": True, "hasAttachments": False, "webLink": "", "conversationId": "conv_007",
    },
    {
        "id": "outlook_mock_008",
        "subject": "NPS Q1 — Score 72 — Analyse détaillée",
        "from": {"emailAddress": {"name": "Clara Rousseau", "address": "c.rousseau@company.com"}},
        "toRecipients": [{"emailAddress": {"address": "ceo@company.com"}}],
        "receivedDateTime": (datetime.utcnow() - timedelta(hours=48)).isoformat() + "Z",
        "bodyPreview": "NPS Q1 = 72. En hausse de 8 points vs Q4. Rapport complet en PJ.",
        "body": {"contentType": "text", "content": "Le NPS Q1 s'établit à 72, en hausse de 8 points vs Q4. Les principaux drivers de satisfaction : support client et time-to-market. Rapport complet en PJ."},
        "importance": "normal", "isRead": True, "hasAttachments": True, "webLink": "", "conversationId": "conv_008",
    },
]


@ConnectorRegistry.register(SourceType.OUTLOOK)
class OutlookConnector(BaseConnector):

    def _load_token_from_db(self) -> dict | None:
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                row = db.query(SourceConfig).filter(SourceConfig.source == "outlook").first()
                if row:
                    return row.config if isinstance(row.config, dict) else json.loads(row.config)
            finally:
                db.close()
        except Exception as e:
            logger.warning("[Outlook] Cannot load token from DB: %s", e)
        return None

    def _save_token_to_db(self, token_data: dict) -> None:
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                row = db.query(SourceConfig).filter(SourceConfig.source == "outlook").first()
                if row:
                    row.config = token_data
                else:
                    db.add(SourceConfig(source="outlook", config=token_data))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("[Outlook] Cannot save token to DB: %s", e)

    async def _refresh_token(self, refresh_token: str) -> str | None:
        from core.config import settings
        tenant = settings.outlook_tenant or "common"
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(token_url, data={
                    "client_id":     settings.outlook_client_id,
                    "client_secret": settings.outlook_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type":    "refresh_token",
                    "scope":         "Mail.Read Calendars.Read offline_access",
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
                logger.warning("[Outlook] Token refresh failed: %s", resp.status_code)
        except Exception as e:
            logger.warning("[Outlook] Token refresh error: %s", e)
        return None

    async def _get_access_token(self) -> str | None:
        cfg = self._load_token_from_db()
        if not cfg:
            return None
        access_token   = cfg.get("access_token")
        refresh_token  = cfg.get("refresh_token")
        refreshed_at   = cfg.get("refreshed_at")
        expires_in     = cfg.get("expires_in", 3600)

        if refreshed_at:
            age = (datetime.utcnow() - datetime.fromisoformat(refreshed_at)).total_seconds()
            if age > expires_in - 300 and refresh_token:
                logger.info("[Outlook] Token expired, refreshing…")
                new_token = await self._refresh_token(refresh_token)
                if new_token:
                    return new_token

        return access_token

    async def authenticate(self) -> None:
        token = await self._get_access_token()
        if not token:
            logger.info("[Outlook] No OAuth token — running in mock mode")
            self._token_cache = None
        else:
            self._token_cache = token
        self._authenticated = True

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        token = getattr(self, "_token_cache", None) or await self._get_access_token()
        if not token:
            use_mock = self.config.get("use_mock", True)
            if use_mock:
                logger.info("[Outlook] No access token — returning mock data")
                return [e for e in MOCK_EMAILS if datetime.fromisoformat(e["receivedDateTime"].rstrip("Z")) >= since]
            logger.warning("[Outlook] No access token and mock disabled — returning empty")
            return []

        headers  = {"Authorization": f"Bearer {token}"}
        max_mail = self.config.get("max_emails", 100)
        since_iso = since.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        emails: list[dict] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "$top":     max_mail,
                    "$filter":  f"receivedDateTime ge {since_iso}",
                    "$orderby": "receivedDateTime desc",
                    "$select":  "id,subject,from,toRecipients,receivedDateTime,bodyPreview,body,importance,isRead,webLink,conversationId,hasAttachments",
                }
                r = await client.get(f"{GRAPH_API}/me/messages", headers=headers, params=params)
                if r.status_code == 200:
                    emails = r.json().get("value", [])
                    logger.info("[Outlook] %d emails fetched", len(emails))
                else:
                    logger.warning("[Outlook] /me/messages → %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("[Outlook] Fetch error: %s", e)

        return emails

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        from_obj  = (raw.get("from") or {}).get("emailAddress") or {}
        author    = from_obj.get("name") or from_obj.get("address") or "unknown"

        body      = raw.get("body") or {}
        content   = body.get("content", raw.get("bodyPreview", ""))
        if body.get("contentType") == "html":
            content = re.sub(r"<[^>]+>", " ", content).strip()
            content = re.sub(r"\s+", " ", content).strip()

        ts_str = raw.get("receivedDateTime", "")
        try:
            timestamp = datetime.fromisoformat(ts_str.rstrip("Z"))
        except Exception:
            timestamp = datetime.utcnow()

        importance = raw.get("importance", "normal")
        tags = []
        if importance in ("high", "urgent"):
            tags.append(importance)
        if not raw.get("isRead", True):
            tags.append("unread")
        if raw.get("hasAttachments"):
            tags.append("attachment")

        recipients = [
            r.get("emailAddress", {}).get("address", "")
            for r in (raw.get("toRecipients") or [])
        ]

        return DataItem(
            id=f"outlook_{raw['id']}",
            source=SourceType.OUTLOOK,
            type=ItemType.EMAIL,
            title=raw.get("subject") or "(sans objet)",
            content=content,
            author=author,
            timestamp=timestamp,
            url=raw.get("webLink", ""),
            tags=tags,
            metadata={
                "from_email":      from_obj.get("address", ""),
                "importance":      importance,
                "is_read":         raw.get("isRead", True),
                "has_attachments": raw.get("hasAttachments", False),
                "conversation_id": raw.get("conversationId", ""),
                "recipients":      recipients,
            },
            raw=raw,
        )
