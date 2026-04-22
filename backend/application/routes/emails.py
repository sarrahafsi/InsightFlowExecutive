"""
Emails — Draft generation (LLM) + Send via Gmail API
=====================================================
POST /api/emails/draft/{item_id}  → génère un brouillon de réponse (Ollama)
POST /api/emails/send             → envoie un email via Gmail API
"""
from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from application.deps import get_store
from core.config import settings
from core.store import ItemStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["emails"])


# ── Schemas ───────────────────────────────────────────────────

class SendRequest(BaseModel):
    to:        str
    subject:   str
    body:      str
    thread_id: str | None = None


# ── Draft generation ──────────────────────────────────────────

@router.post("/draft/{item_id}")
async def generate_draft(
    item_id: str,
    store: Annotated[ItemStore, Depends(get_store)],
):
    """
    Génère un brouillon de réponse pour un email en utilisant Ollama.
    Le LLM reçoit le contenu de l'email + le contexte NLP (business label, sentiment)
    et produit une réponse professionnelle adaptée au CEO.
    """
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Email '{item_id}' introuvable.")
    if item.source != "gmail":
        raise HTTPException(status_code=400, detail="Le draft est disponible uniquement pour les emails Gmail.")

    meta           = item.metadata or {}
    business_label = meta.get("business_label") or "Neutral Update"
    sentiment      = meta.get("sentiment_label") or "NEUTRAL"
    topic          = meta.get("topic") or ""
    reason         = meta.get("business_reason") or ""

    prompt = f"""Tu es l'assistant exécutif d'un CEO. Tu dois rédiger une réponse professionnelle et concise à l'email suivant.

--- EMAIL REÇU ---
De      : {item.author}
Objet   : {item.title}
Contenu : {(item.content or '')[:1500]}

--- CONTEXTE IA ---
Priorité     : {business_label}
Sentiment    : {sentiment}
Sujet détecté: {topic}
Analyse      : {reason}

--- INSTRUCTIONS ---
- Réponds de manière professionnelle, directe et adaptée au niveau CEO.
- La réponse doit être courte (3-6 phrases maximum).
- Ne mentionne pas l'analyse IA dans ta réponse.
- Commence directement par la réponse, sans formule d'introduction comme "Voici un brouillon".
- Termine par une formule de politesse appropriée.

RÉPONSE :"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url.rstrip('/v1')}/api/generate",
                json={
                    "model":  settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            draft = resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning("[Emails/Draft] Ollama failed: %s", e)
        raise HTTPException(status_code=503, detail=f"LLM indisponible : {e}")

    return {
        "item_id":   item_id,
        "to":        meta.get("from_email", item.author),
        "subject":   f"Re: {item.title}",
        "thread_id": meta.get("thread_id"),
        "draft":     draft,
    }


# ── Send email ────────────────────────────────────────────────

@router.post("/send")
async def send_email(body: SendRequest):
    """
    Envoie un email via Gmail API.
    Nécessite que Gmail soit authentifié (OAuth2).
    """
    try:
        from application.routes.auth import get_gmail_credentials
        from googleapiclient.discovery import build
        from integrations.connectors.gmail import GmailConnector

        creds = get_gmail_credentials()
        if not creds or not creds.valid:
            raise HTTPException(
                status_code=401,
                detail="Gmail non authentifié. Reconnectez-vous via /auth/gmail."
            )

        connector = GmailConnector(config={})
        connector._service = build("gmail", "v1", credentials=creds)
        connector._authenticated = True

        message_id = connector.send_email(
            to=body.to,
            subject=body.subject,
            body=body.body,
            thread_id=body.thread_id,
        )

        logger.info("[Emails/Send] Email envoyé à %s (message_id=%s)", body.to, message_id)
        return {"sent": True, "message_id": message_id, "to": body.to}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Emails/Send] Erreur envoi : %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'envoi : {e}")
