"""
Image Processor — fusion OCR + Vision → JSON structuré
============================================================================
Pipeline (cf. discussion PFE, architecture actée) :

    image
      |
      +-- OCR (Tesseract)        -> texte exact (chiffres, statuts, noms)
      +-- Vision (BLIP-base)     -> contexte visuel general
      |
      v
    LLM (Ollama/GPT-4o, deja configure dans intelligence/llm/client.py)
      |
      v
    JSON structure (image_type, summary, status, key_facts, business_context)
      |
      v
    DataItem.content (texte formate) -> pipeline NLP existant
    (sentiment / emotion / topic / business, inchange)

Ni l'OCR ni le Vision ne "voient" jamais le LLM texte-only par defaut
(Ollama) autrement que via ce texte intermediaire — coherent avec le mode
gratuit/local par defaut du projet (cf. core/config.py, llm_provider).

Aucune exception ne remonte : chaque etage echoue silencieusement vers une
valeur par defaut (comme transcription.py et ocr_service.py), pour ne
jamais casser l'ingestion ETL sur une image problematique.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from intelligence.nlp.ocr_service import extract_text
from intelligence.nlp.vision_service import generate_caption

logger = logging.getLogger(__name__)

FUSION_SYSTEM_PROMPT = """You analyze a business screenshot (dashboard, ticket, \
error message, chat, email, chart, table, document, or workflow) using two \
signals extracted from it:
1. OCR text — the exact text read from the image (may be noisy or incomplete).
2. Vision caption — a general visual description (may be vague, ignore it if \
it contradicts the OCR text).

Combine both into a short structured JSON object, in English, with exactly \
these fields:
{
  "image_type": one short category, e.g. "dashboard", "ticket", "error", \
"chat", "chart", "table", "document", "workflow", "email", or "other",
  "summary": one sentence describing the business situation shown,
  "status": the overall status if visible (e.g. "blocked", "on_track", \
"resolved", "at_risk", "healthy", "unknown"),
  "key_facts": a list of up to 4 short exact facts from the OCR text \
(numbers, names, statuses) — empty list if none,
  "business_context": one sentence on why this matters, or empty string if \
not inferable
}

Only rely on the OCR text for exact numbers/names/statuses — never invent \
ones that are not in the OCR text. Respond with ONLY the JSON object, no \
other text."""


def _build_user_prompt(ocr_text: str | None, vision_caption: str | None) -> str:
    ocr_part = ocr_text if ocr_text else "(no text detected)"
    vision_part = vision_caption if vision_caption else "(no caption available)"
    return f"OCR text:\n{ocr_part}\n\nVision caption:\n{vision_part}"


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


async def _fuse_with_llm_async(ocr_text: str | None, vision_caption: str | None) -> dict[str, Any] | None:
    from intelligence.llm.client import complete

    user_prompt = _build_user_prompt(ocr_text, vision_caption)
    try:
        raw = await complete(
            system=FUSION_SYSTEM_PROMPT,
            user=user_prompt,
            use_tools=False,
            temperature=0.1,
            max_tokens=300,
        )
    except Exception as e:
        logger.warning("[NLP/ImageProcessor] Appel LLM echoue: %s", e)
        return None

    parsed = _parse_llm_json(raw)
    if parsed is None:
        logger.warning("[NLP/ImageProcessor] Reponse LLM non parsable en JSON: %r", raw[:200])
    return parsed


def _fallback_structured(ocr_text: str | None, vision_caption: str | None) -> dict[str, Any]:
    """Utilisee si la fusion LLM echoue — degrade proprement plutot que de planter."""
    return {
        "image_type": "other",
        "summary": vision_caption or (ocr_text[:120] if ocr_text else "Image sans texte ni caption détectés."),
        "status": "unknown",
        "key_facts": [],
        "business_context": "",
    }


def _to_content_text(structured: dict[str, Any]) -> str:
    """Formate le JSON structure en texte pour le pipeline NLP existant (DataItem.content)."""
    parts = [structured.get("summary", "")]
    facts = structured.get("key_facts") or []
    if facts:
        parts.append("Details: " + "; ".join(str(f) for f in facts))
    if structured.get("business_context"):
        parts.append(structured["business_context"])
    return " ".join(p for p in parts if p).strip()


async def process_image_async(image_path: str | Path) -> dict[str, Any]:
    """Version async — a utiliser depuis un contexte deja async (routes FastAPI,
    Celery avec asyncio, etc.) pour eviter le conflit "asyncio.run() dans une
    boucle deja active" (RuntimeError). Ne leve jamais d'exception."""
    image_path = Path(image_path)
    ocr_text = extract_text(image_path)
    vision_caption = generate_caption(image_path)

    structured = await _fuse_with_llm_async(ocr_text, vision_caption)
    if structured is None:
        structured = _fallback_structured(ocr_text, vision_caption)

    return {
        "ocr_text": ocr_text,
        "vision_caption": vision_caption,
        "structured": structured,
        "content": _to_content_text(structured),
    }


def process_image(image_path: str | Path) -> dict[str, Any]:
    """Version synchrone — a utiliser depuis un script/CLI classique (pas de
    boucle asyncio deja active). Pour un contexte deja async, utiliser
    process_image_async() directement (await) plutot que cette fonction."""
    return asyncio.run(process_image_async(image_path))

