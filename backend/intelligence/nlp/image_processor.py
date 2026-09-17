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
from intelligence.nlp.trend_detector import detect_line_trend
from intelligence.nlp.vision_service import generate_caption

logger = logging.getLogger(__name__)

FUSION_SYSTEM_PROMPT = """You analyze a business screenshot (dashboard, ticket, \
error message, chat, email, chart, table, document, or workflow) using up to \
three signals extracted from it:
1. OCR text — the exact text read from the image (may be noisy or incomplete).
2. Vision caption — a general visual description (may be vague, ignore it if \
it contradicts the OCR text).
3. Detected line trend — a best-effort pixel-based signal (increasing/\
decreasing/flat/not detected), only meaningful if the image is a line chart. \
Neither the OCR text nor the vision caption can reliably report a chart's \
trend direction on their own — trust this signal for that specific fact when \
present, alongside the OCR text for exact values.

Combine all available signals into a short structured JSON object with \
exactly these fields:
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
ones that are not in the OCR text. "image_type" and "status" must stay one \
of the fixed English category values listed above — but "summary" and \
"business_context" must ALWAYS be written in FRENCH, regardless of the \
language of the OCR text or the vision caption (the vision caption is \
always in English regardless of the image's actual language — do not let \
it dictate the output language). Respond with ONLY the JSON object, no \
other text."""


def _build_user_prompt(ocr_text: str | None, vision_caption: str | None, line_trend: str | None) -> str:
    ocr_part = ocr_text if ocr_text else "(no text detected)"
    vision_part = vision_caption if vision_caption else "(no caption available)"
    trend_part = line_trend if line_trend else "(not detected / not a line chart)"
    return (f"OCR text:\n{ocr_part}\n\nVision caption:\n{vision_part}\n\n"
            f"Detected line trend:\n{trend_part}")


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


async def _fuse_with_llm_async(ocr_text: str | None, vision_caption: str | None,
                                line_trend: str | None) -> dict[str, Any] | None:
    from intelligence.llm.client import complete

    user_prompt = _build_user_prompt(ocr_text, vision_caption, line_trend)
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
    ocr_text = await asyncio.to_thread(extract_text, image_path)
    vision_caption = await asyncio.to_thread(generate_caption, image_path)
    line_trend = await asyncio.to_thread(detect_line_trend, image_path)

    structured = await _fuse_with_llm_async(ocr_text, vision_caption, line_trend)
    if structured is None:
        structured = _fallback_structured(ocr_text, vision_caption)

    return {
        "ocr_text": ocr_text,
        "vision_caption": vision_caption,
        "line_trend": line_trend,
        "structured": structured,
        "content": _to_content_text(structured),
    }


def process_image(image_path: str | Path) -> dict[str, Any]:
    """Version synchrone — a utiliser depuis un script/CLI classique (pas de
    boucle asyncio deja active). Pour un contexte deja async, utiliser
    process_image_async() directement (await) plutot que cette fonction."""
    return asyncio.run(process_image_async(image_path))


async def process_image_bytes_async(image_bytes: bytes, suffix: str = ".img") -> dict[str, Any]:
    """Comme process_image_async, mais a partir de bytes bruts (ex: telecharges
    depuis un connecteur — Slack, Teams...) plutot qu'un fichier deja sur disque.
    Meme pattern que transcribe_audio() dans transcription.py : fichier temporaire,
    toujours nettoye. Ne leve jamais d'exception."""
    import tempfile
    import os

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        return await process_image_async(tmp_path)
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


async def enrich_data_items_with_images(items: list) -> None:
    """Point de centralisation UNIQUE, appele une seule fois pour TOUS les
    connecteurs (depuis BaseConnector.sync(), pas depuis chaque connecteur) —
    exactement comme le pipeline NLP texte est centralise dans
    data/etl/loader.py plutot que reimplemente par connecteur.

    Convention : un connecteur qui detecte une piece jointe image n'a qu'une
    seule chose a faire pendant fetch_raw() — telecharger les bytes et les
    stocker dans raw["_pending_image_bytes"]. Tout le reste (OCR, Vision,
    fusion LLM, fusion dans content, tag "image", metadata.is_image) est geré
    ici, une seule fois — un nouveau connecteur futur en beneficie
    automatiquement des qu'il respecte cette convention, sans avoir a
    reimplementer l'analyse elle-meme.

    Mute les DataItem en place. Ne leve jamais d'exception (une image qui
    echoue ne doit jamais faire echouer toute la synchronisation)."""
    for item in items:
        image_bytes = (item.raw or {}).get("_pending_image_bytes")
        if not image_bytes:
            continue
        try:
            result = await process_image_bytes_async(image_bytes)
        except Exception as e:
            logger.warning("[NLP/ImageProcessor] Enrichissement de %s echoue: %s", item.id, e)
            continue

        image_text = result.get("content")
        if not image_text:
            continue

        item.content = (f"{item.content}\n\n[Image] {image_text}"
                         if (item.content or "").strip() else f"[Image] {image_text}")
        if "image" not in (item.tags or []):
            item.tags = (item.tags or []) + ["image"]
        item.metadata = {**(item.metadata or {}), "is_image": True}

