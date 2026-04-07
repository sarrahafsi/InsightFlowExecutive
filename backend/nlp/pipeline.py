"""
NLPPipeline — orchestrates all NLP processors in sequence.
Designed for scalability: add/remove processors without touching other code.
"""
from __future__ import annotations
import logging
from typing import Optional

from connectors.schemas import DataItem
from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)


class NLPPipeline:
    """
    Modular NLP pipeline.

    Usage:
        pipeline = NLPPipeline(steps=[
            SentimentProcessor(),
            EmotionProcessor(),
            TopicProcessor(),
            BusinessClassifier(),
        ])
        enriched = pipeline.run(data_item)
    """

    def __init__(self, steps: list[BaseProcessor]):
        self.steps = steps
        logger.info(
            "[NLP] Pipeline initialized with %d steps: %s",
            len(steps),
            " → ".join(str(s) for s in steps),
        )

    def run(self, item: DataItem) -> Optional[EnrichedItem]:
        """Process a single DataItem through all pipeline steps."""
        text = (item.content or item.title or "").strip()
        if not text:
            return None

        enriched = EnrichedItem(
            id=item.id,
            source=item.source,
            author=item.author or "",
            timestamp=str(item.timestamp),
            title=item.title or "",
            content=text,
            metadata=item.metadata or {},
        )

        for step in self.steps:
            try:
                enriched = step.process(enriched)
            except Exception as e:
                logger.warning("[NLP] Step %s failed for item %s: %s", step, item.id, e)

        return enriched

    def run_batch(self, items: list[DataItem]) -> list[EnrichedItem]:
        """Process a list of DataItems."""
        results = []
        for item in items:
            enriched = self.run(item)
            if enriched:
                results.append(enriched)
        logger.info("[NLP] Processed %d/%d items.", len(results), len(items))
        return results
