"""
Détecteur de tendance visuelle (heuristique CV, pas de deep learning)
============================================================================
Ni l'OCR ni le captioning Vision (BLIP) ne rapportent fiablement la
direction d'une courbe (hausse/baisse) — l'OCR lit du texte, pas des
formes, et BLIP est trop faible pour ça sur ce domaine. Ce module comble
ce trou avec une heuristique simple : repérer les pixels colorés (la
courbe tracée, généralement la seule couleur saturée sur fond
blanc/gris/texte noir) et comparer leur hauteur moyenne entre le début et
la fin de l'image.

Best-effort seulement : retourne None si le signal n'est pas assez net pour
être fiable, plutôt que d'inventer une réponse.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_line_trend(image_path: str | Path) -> str | None:
    """Retourne 'increasing' / 'decreasing' / 'flat', ou None si indetermine."""
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img.thumbnail((300, 300))
        w, h = img.size
        pixels = img.load()

        # Ignore le premier ~18% de la hauteur : c'est presque toujours le titre/
        # en-tete (texte colore) du graphique, qui fausserait la mesure sinon.
        y_start = int(h * 0.18)

        left_ys: list[int] = []
        right_ys: list[int] = []
        for x in range(w):
            in_left = x < w / 3
            in_right = x > 2 * w / 3
            if not in_left and not in_right:
                continue
            for y in range(y_start, h):
                r, g, b = pixels[x, y]
                mx, mn = max(r, g, b), min(r, g, b)
                saturation = 0 if mx == 0 else (mx - mn) / mx
                brightness = mx / 255
                if saturation > 0.22 and 0.15 < brightness < 0.97:
                    (left_ys if in_left else right_ys).append(y)

        # Il faut un minimum de pixels colores de chaque cote pour un signal fiable
        if len(left_ys) < 5 or len(right_ys) < 5:
            return None

        left_avg = sum(left_ys) / len(left_ys)
        right_avg = sum(right_ys) / len(right_ys)
        diff = left_avg - right_avg  # positif = droite plus haut a l'ecran (y plus petit) = hausse

        threshold = h * 0.04
        if diff > threshold:
            return "increasing"
        if diff < -threshold:
            return "decreasing"
        return "flat"
    except Exception as e:
        logger.warning("[NLP/TrendDetector] Echec sur %s: %s", image_path, e)
        return None
