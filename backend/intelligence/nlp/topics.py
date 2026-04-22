"""
Topic Processor — HuggingFace Zero-Shot Classification
Extrait le sujet principal d'un message.

Modèle : cross-encoder/nli-MiniLM2-L6-H768  (léger, rapide)
Approche : zero-shot → pas de fine-tuning nécessaire

Topics business définis par le domaine exécutif :
  project update | deadline | budget | technical issue |
  client relations | team management | deployment | planning | other
"""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import Optional

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)

TOPIC_MODEL = "cross-encoder/nli-MiniLM2-L6-H768"

BUSINESS_TOPICS = [
    "project update",
    "deadline",
    "budget",
    "technical issue",
    "client relations",
    "team management",
    "deployment",
    "planning",
    "other",
]


@lru_cache(maxsize=1)
def _load_pipeline():
    from transformers import pipeline
    logger.info("[NLP/Topic] Loading model: %s", TOPIC_MODEL)
    return pipeline(
        "zero-shot-classification",
        model=TOPIC_MODEL,
    )


class TopicProcessor(BaseProcessor):
    """
    Zero-shot topic extraction.
    Ajoute topic à l'EnrichedItem.
    """

    def process(self, item: EnrichedItem) -> EnrichedItem:
        result = _classify(item.content)
        if result:
            item.topic = result
        return item


def _classify(text: str) -> Optional[str]:
    try:
        pipe = _load_pipeline()
        output = pipe(text[:500], candidate_labels=BUSINESS_TOPICS)
        # Premier label = topic avec le score le plus élevé
        return output["labels"][0]
    except Exception as e:
        logger.warning("[NLP/Topic] Classification failed: %s", e)
        return None
