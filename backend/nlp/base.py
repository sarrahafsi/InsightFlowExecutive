"""
Base class for all NLP processors.
Each processor receives an EnrichedItem, enriches it, and returns it.
This allows building a modular, extensible pipeline.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EnrichedItem:
    """Unified data structure passed through the NLP pipeline."""

    # --- Original fields from DataItem ---
    id:           str
    source:       str
    author:       str
    timestamp:    str
    title:        str
    content:      str
    metadata:     dict = field(default_factory=dict)

    # --- NLP Layer 1 : HuggingFace results ---
    sentiment_label:  Optional[str]   = None   # POSITIVE | NEGATIVE | NEUTRAL
    sentiment_score:  Optional[float] = None
    emotion_label:    Optional[str]   = None   # anger | joy | frustration | ...
    emotion_score:    Optional[float] = None
    topic:            Optional[str]   = None   # project update | deadline | ...

    # --- NLP Layer 2 : LLM business classification ---
    business_label:       Optional[str]   = None  # BLOCKED | RISK | URGENT | ...
    business_confidence:  Optional[float] = None
    business_reason:      Optional[str]   = None


class BaseProcessor(ABC):
    """Abstract processor — each step in the pipeline implements this."""

    @abstractmethod
    def process(self, item: EnrichedItem) -> EnrichedItem:
        """Enrich the item and return it."""
        ...

    def __repr__(self) -> str:
        return self.__class__.__name__
