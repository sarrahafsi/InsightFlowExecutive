"""
Sentiment Processor — HuggingFace Level
Détecte le sentiment général : POSITIVE / NEGATIVE / NEUTRAL

Modèle par défaut : cardiffnlp/twitter-roberta-base-sentiment-latest
Remplacé par le modèle gagnant du benchmark (voir ml/benchmark/).
"""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import Optional

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)

# Modèle sélectionné après benchmark :
# XLM-RoBERTa multilingue (FR+EN) — choix justifié pour emails mixtes français/anglais
# Benchmark : RoBERTa-EN=73.54% F1 (EN only) vs XLM-RoBERTa=67.21% (FR+EN)
# → XLM-RoBERTa retenu pour robustesse multilingue sur données réelles
SENTIMENT_MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
MAX_LENGTH = 512


@lru_cache(maxsize=1)
def _load_pipeline():
    """Lazy-load du modèle — chargé une seule fois en mémoire."""
    from transformers import pipeline
    logger.info("[NLP/Sentiment] Loading model: %s", SENTIMENT_MODEL)
    return pipeline(
        "sentiment-analysis",
        model=SENTIMENT_MODEL,
        truncation=True,
        max_length=MAX_LENGTH,
    )


# Mapping labels selon le modèle cardiffnlp
_LABEL_MAP = {
    "LABEL_0": "NEGATIVE",
    "LABEL_1": "NEUTRAL",
    "LABEL_2": "POSITIVE",
    # Compatibilité autres modèles
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
