"""
Emotion Processor — HuggingFace Level
Détecte l'émotion dominante dans un message.

Modèle : j-hartmann/emotion-english-distilroberta-base
Labels : anger | disgust | fear | joy | neutral | sadness | surprise

Mapping business :
  anger/disgust  → frustration (signal d'insatisfaction)
  fear/sadness   → concern     (signal de risque)
  joy            → satisfaction
  surprise       → urgency     (inattendu)
  neutral        → neutral
"""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import Optional

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)

EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"
MAX_LENGTH = 512

# Mapping vers labels business lisibles
_EMOTION_MAP = {
    "anger":    "frustration",
    "disgust":  "frustration",
    "fear":     "concern",
    "sadness":  "concern",
    "joy":      "satisfaction",
    "surprise": "urgency",
    "neutral":  "neutral",
}


@lru_cache(maxsize=1)
def _load_pipeline():
    from transformers import pipeline
    logger.info("[NLP/Emotion] Loading model: %s", EMOTION_MODEL)
    return pipeline(
        "text-classification",
        model=EMOTION_MODEL,
        truncation=True,
        max_length=MAX_LENGTH,
    )


class EmotionProcessor(BaseProcessor):
    """
    HuggingFace emotion detection.
    Ajoute emotion_label + emotion_score à l'EnrichedItem.
    """

    def process(self, item: EnrichedItem) -> EnrichedItem:
        result = _classify(item.content)
        if result:
            item.emotion_label = result["label"]
            item.emotion_score = round(result["score"], 4)
        return item


def _classify(text: str) -> Optional[dict]:
    try:
        pipe = _load_pipeline()
        output = pipe(text[:1000])[0]
        raw_label = output.get("label", "neutral").lower()
        label = _EMOTION_MAP.get(raw_label, "neutral")
        return {"label": label, "score": output.get("score", 0.0)}
    except Exception as e:
        logger.warning("[NLP/Emotion] Classification failed: %s", e)
        return None
