"""
Sentiment Processor — Fine-tuned XLM-RoBERTa
Détecte le sentiment général : POSITIVE / NEGATIVE / NEUTRAL

Modèle : insightflow-sentiment-xlm-v1 (fine-tuné sur dataset InsightFlow)
  eval_accuracy=0.991, eval_f1_macro=0.991
  Fallback : cardiffnlp/twitter-xlm-roberta-base-sentiment (HuggingFace)
"""
from __future__ import annotations
import logging
import os
from functools import lru_cache
from typing import Optional

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)

# Chemin vers le modèle fine-tuné local
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_MODEL  = os.path.join(_BACKEND_DIR, "..", "ml", "models", "insightflow-sentiment-xlm-v1")
_REMOTE_MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"

SENTIMENT_MODEL = _LOCAL_MODEL if os.path.isdir(_LOCAL_MODEL) else _REMOTE_MODEL
MAX_LENGTH = 512


@lru_cache(maxsize=1)
def _load_pipeline():
    """Lazy-load du modèle — chargé une seule fois en mémoire."""
    from transformers import pipeline
    source = "local" if os.path.isdir(_LOCAL_MODEL) else "HuggingFace"
    logger.info("[NLP/Sentiment] Loading model (%s): %s", source, SENTIMENT_MODEL)
    return pipeline(
        "sentiment-analysis",
        model=SENTIMENT_MODEL,
        truncation=True,
        max_length=MAX_LENGTH,
    )


# Mapping labels — le modèle fine-tuné retourne directement NEGATIVE/NEUTRAL/POSITIVE
_LABEL_MAP = {
    "LABEL_0": "NEGATIVE",
    "LABEL_1": "NEUTRAL",
    "LABEL_2": "POSITIVE",
    "NEGATIVE": "NEGATIVE",
    "NEUTRAL":  "NEUTRAL",
    "POSITIVE": "POSITIVE",
    "negative": "NEGATIVE",
    "neutral":  "NEUTRAL",
    "positive": "POSITIVE",
}


class SentimentProcessor(BaseProcessor):
    """
    HuggingFace sentiment classification.
    Ajoute sentiment_label + sentiment_score à l'EnrichedItem.
    """

    def process(self, item: EnrichedItem) -> EnrichedItem:
        result = _classify(item.content)
        if result:
            item.sentiment_label = result["label"]
            item.sentiment_score = round(result["score"], 4)
        return item


def _classify(text: str) -> Optional[dict]:
    try:
        pipe = _load_pipeline()
        # Tronquer manuellement si texte trop long
        output = pipe(text[:1000])[0]
        raw_label = output.get("label", "")
        label = _LABEL_MAP.get(raw_label, "NEUTRAL")
        return {"label": label, "score": output.get("score", 0.0)}
    except Exception as e:
        logger.warning("[NLP/Sentiment] Classification failed: %s", e)
        return None
