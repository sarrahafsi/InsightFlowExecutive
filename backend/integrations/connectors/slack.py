"""
Slack Connector — API réelle via slack-sdk
==========================================
Récupère les messages des canaux publics auxquels le bot est invité.

Config keys (dans ConnectorManager / .env) :
    token (str)          : Bot OAuth token (xoxb-...) — passé directement (legacy)
    org_id (str)          : Si présent, le token est chargé depuis source_configs
                            (installé via /auth/slack — un token par organisation).
                            Sinon, fallback sur SLACK_BOT_TOKEN (.env, workspace unique, dev/legacy).
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

    def _load_db_config(self) -> dict | None:
        """Charge le token installé via OAuth pour cette org (source_configs, source='slack')."""
        org_id = self.config.get("org_id")
        if not org_id:
            return None
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                row = db.query(SourceConfig).filter(
                    SourceConfig.source == "slack", SourceConfig.org_id == org_id,
                ).first()
                if row:
                    return row.config if isinstance(row.config, dict) else {}
            finally:
                db.close()
        except Exception:
            pass
        return None

    def _delete_stale_token(self) -> None:
        """Token invalide/révoqué — le supprimer de la DB pour forcer une reconnexion."""
        org_id = self.config.get("org_id")
        if not org_id:
            return
        try:
            from core.database import SessionLocal
            from core.models import SourceConfig
            db = SessionLocal()
            try:
                db.query(SourceConfig).filter(
                    SourceConfig.source == "slack", SourceConfig.org_id == org_id,
                ).delete(synchronize_session=False)
                db.commit()
            finally:
                db.close()
        except Exception:
            pass

    def _get_token(self) -> str:
        # Priorité : config passée directement (legacy/tests) > DB (org OAuth) > .env global
        if self.config.get("token"):
            return self.config["token"]
        db_cfg = self._load_db_config()
        if db_cfg and db_cfg.get("bot_token"):
            return db_cfg["bot_token"]
        from core.config import settings
        return settings.slack_bot_token

    def _get_client(self):
        from slack_sdk import WebClient
        return WebClient(token=self._get_token())

    # ── Write ─────────────────────────────────────────────────

    def send_message(self, channel_id: str, text: str, thread_ts: str | None = None) -> str:
        """Poste un message (chat:write). Retourne le ts du message envoyé."""
        client = self._get_client()
        resp = client.chat_postMessage(channel=channel_id, text=text, thread_ts=thread_ts)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "chat_postMessage failed"))
        return resp["ts"]

    def open_dm(self, user_id: str) -> str:
        """Ouvre (ou récupère) le canal DM avec un utilisateur (im:write). Retourne le channel id."""
        client = self._get_client()
        resp = client.conversations_open(users=[user_id])
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "conversations_open failed"))
        return resp["channel"]["id"]

    # ── Authenticate ──────────────────────────────────────────

    async def authenticate(self) -> None:
        if self.config.get("use_mock", False):
            self._authenticated = True
            return

        token = self._get_token()
        if not token:
            # Pas de credentials — skip silencieusement (BaseConnector.sync() gère le cas)
            return

        try:
            client = self._get_client()
            resp = client.auth_test()
            if not resp["ok"]:
                self._delete_stale_token()
                logger.debug("[Slack] Token invalide supprimé — sync ignoré jusqu'à reconnexion")
                return
            logger.info("[Slack] Authentifié en tant que bot : %s (workspace : %s)",
                        resp.get("bot_id"), resp.get("team"))
        except Exception as e:
            self._delete_stale_token()
            logger.warning("[Slack] Échec d'authentification, credentials supprimés : %s", e)
            return

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

        await self._transcribe_voice_messages(messages)
        await self._download_images(messages)

        logger.info("[Slack] %d messages récupérés depuis %d canaux.", len(messages), len(channel_ids))
        return messages

    async def _transcribe_voice_messages(self, messages: list[dict[str, Any]]) -> None:
        """Télécharge + transcrit les messages vocaux (mutate en place : `_voice_transcript`)."""
        from intelligence.nlp.transcription import download_and_transcribe

        token = self._get_token()
        for msg in messages:
            if not msg.get("_is_voice") or not msg.get("_audio_url"):
                continue
            transcript = await download_and_transcribe(
                msg["_audio_url"], headers={"Authorization": f"Bearer {token}"},
            )
            if transcript:
                msg["_voice_transcript"] = transcript
            else:
                logger.warning("[Slack] Transcription échouée pour un message vocal (channel=%s)",
                                msg.get("channel"))

    async def _download_images(self, messages: list[dict[str, Any]]) -> None:
        """Télécharge les images en pièce jointe (mutate en place :
        `_pending_image_bytes`) — le téléchargement est forcément spécifique à
        Slack (auth par token Bearer), mais l'analyse (OCR+Vision+fusion) ne
        l'est pas : elle est centralisée dans BaseConnector.sync() pour tous
        les connecteurs, pas dupliquée ici (cf. image_processor.py)."""
        import httpx

        token = self._get_token()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for msg in messages:
                if not msg.get("_image_url"):
                    continue
                try:
                    resp = await client.get(
                        msg["_image_url"], headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code != 200:
                        logger.warning("[Slack] Téléchargement image échoué (%s) pour channel=%s",
                                        resp.status_code, msg.get("channel"))
                        continue
                    msg["_pending_image_bytes"] = resp.content
                except Exception as e:
                    logger.warning("[Slack] Téléchargement image échoué (channel=%s) : %s",
                                    msg.get("channel"), e)

    def _list_public_channels(self, client) -> list[str]:
        """Liste tous les canaux publics et y fait rejoindre le bot au besoin (channels:join)."""
        try:
            resp = client.conversations_list(
                types="public_channel",
                exclude_archived=True,
                limit=200,
            )
            channels = [c for c in resp.get("channels", []) if not c.get("is_archived")]
        except Exception as e:
            logger.warning("[Slack] Impossible de lister les canaux : %s", e)
            return []

        ids = []
        for c in channels:
            cid = c["id"]
            if not c.get("is_member"):
                try:
                    client.conversations_join(channel=cid)
                except Exception as e:
                    logger.debug("[Slack] Impossible de rejoindre #%s : %s", c.get("name", cid), e)
                    continue
            ids.append(cid)

        logger.info("[Slack] %d canaux publics accessibles.", len(ids))
        return ids

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

                audio_file = next(
                    (f for f in msg.get("files", []) if str(f.get("mimetype", "")).startswith("audio/")),
                    None,
                )
                image_file = next(
                    (f for f in msg.get("files", []) if str(f.get("mimetype", "")).startswith("image/")),
                    None,
                )
                if audio_file:
                    msg["_is_voice"] = True
                    msg["_audio_url"] = audio_file.get("url_private_download")
                if image_file:
                    msg["_image_url"] = image_file.get("url_private_download")
                if not audio_file and not image_file and not msg.get("text", "").strip():
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

        # L'enrichissement image (contenu, tag "image", metadata.is_image) est
        # applique apres coup par BaseConnector.sync() (enrich_data_items_with_images),
        # pas ici — voir intelligence/nlp/image_processor.py.
        is_voice = raw.get("_is_voice", False)
        content = raw.get("_voice_transcript") or raw.get("text", "") if is_voice else raw.get("text", "")
        tags = [channel_name] + (["voice"] if is_voice else [])

        return DataItem(
            id=self.scoped_id(f"{raw['ts']}_{raw.get('channel', '')}"),
            source=SourceType.SLACK,
            type=ItemType.MESSAGE,
            title=f"#{channel_name}",
            content=content,
            author=raw.get("username", raw.get("user", "unknown")),
            timestamp=timestamp,
            url=raw.get("permalink", ""),
            tags=tags,
            metadata={
                "channel_id":   raw.get("channel"),
                "channel_name": channel_name,
                "user_id":      raw.get("user"),
                "thread_ts":    raw.get("thread_ts"),
                "is_voice":     is_voice,
            },
            raw=raw,
        )
