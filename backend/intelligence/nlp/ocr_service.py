"""
OCR — extraction de texte exact depuis les images (captures d'écran pro)
============================================================================
Moteur : Tesseract (pytesseract), retenu par le benchmark Phase 0
(backend/BENCHMARK_RESULTS.md — précision parfaite, le plus rapide des 3
moteurs testés). Source primaire de vérité pour le texte visible dans une
image (chiffres, statuts, noms) — le captioning Vision (vision_service.py)
n'est qu'un complément pour le contexte visuel général.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _configure_tesseract() -> bool:
    import pytesseract
    from core.config import settings

    cmd_path = Path(settings.tesseract_cmd_path)
    if cmd_path.exists():
        pytesseract.pytesseract.tesseract_cmd = str(cmd_path)
    # Sinon on laisse pytesseract chercher "tesseract" dans le PATH système
    # (cas typique d'une installation Linux via apt-get install tesseract-ocr)
    return True


def extract_text(image_path: str | Path) -> str | None:
    """Extrait le texte visible d'une image. Retourne None si échec (jamais d'exception)."""
    try:
        import pytesseract
        from PIL import Image

        _configure_tesseract()
        image = Image.open(image_path).convert("RGB")
        text = pytesseract.image_to_string(image).strip()
        return text or None
    except Exception as e:
        logger.warning("[NLP/OCR] Extraction echouee sur %s: %s", image_path, e)
        return None
