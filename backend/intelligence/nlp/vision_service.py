"""
Vision — caption générale d'une image (contexte visuel)
============================================================================
Modèle : BLIP-base pré-entraîné (Salesforce/blip-image-captioning-base),
retenu par le benchmark Phase 0 (meilleur des 3 modèles testés, cf.
backend/BENCHMARK_RESULTS.md). Décision (28/08/2026, cf. mémoire
project_vision_finetuning) : PAS de fine-tuning en production — le
fine-tuning tenté a montré un gain modeste (+6% CLIP) mais une dégradation
de cohérence sur les images à contenu énuméré complexe (dashboards, tableaux).
Le modèle de base seul, complété par l'OCR (source de vérité pour le texte
exact) et la fusion LLM (image_processor.py), est suffisant : ce module n'a
besoin de fournir qu'un indice visuel général, pas une description parfaite.

`no_repeat_ngram_size=3` appliqué à la génération pour éviter la
dégénérescence par répétition observée en Phase 0 sur les images hors
distribution COCO (cf. BENCHMARK_RESULTS.md, section "Défaut observé").
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from ._model_lock import MODEL_LOAD_LOCK

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    with MODEL_LOAD_LOCK:
        from transformers import BlipProcessor, BlipForConditionalGeneration
        from core.config import settings

        logger.info("[NLP/Vision] Loading BLIP model: %s (device=%s)",
                    settings.vision_model_name, settings.vision_device)
        processor = BlipProcessor.from_pretrained(settings.vision_model_name)
        model = BlipForConditionalGeneration.from_pretrained(
            settings.vision_model_name, low_cpu_mem_usage=False,
        )
        model.to(settings.vision_device)
        model.eval()
        return processor, model


def generate_caption(image_path: str | Path) -> str | None:
    """Génère une caption visuelle générale. Retourne None si échec (jamais d'exception)."""
    try:
        from PIL import Image
        from core.config import settings

        processor, model = _load_model()
        image = Image.open(image_path).convert("RGB")
        inputs = processor(image, return_tensors="pt").to(settings.vision_device)
        out = model.generate(**inputs, max_new_tokens=40, num_beams=4, no_repeat_ngram_size=3)
        caption = processor.decode(out[0], skip_special_tokens=True).strip()
        return caption or None
    except Exception as e:
        logger.warning("[NLP/Vision] Captioning echoue sur %s: %s", image_path, e)
        return None
