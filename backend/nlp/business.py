"""
Business Classifier — LLM Intelligence Layer (Level 2)
Classifie l'impact business d'un message pour le CEO.

Backend : Ollama (local, gratuit)
Endpoint : http://localhost:11434/v1  (compatible OpenAI API)
Modèle par défaut : llama3.2  (configurable via OLLAMA_MODEL dans .env)

Déclenché UNIQUEMENT si :
  - sentiment_label == NEGATIVE
  - OU emotion_label in [frustration, concern, urgency]

Labels business :
  Progress | Neutral Update | Concern | Risk | Blocked | Overload | Conflict | Urgent
"""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2")

BUSINESS_LABELS = [
    "Progress",
    "Neutral Update",
    "Concern",
    "Risk",
    "Blocked",
    "Overload",
    "Conflict",
    "Urgent",
]

_TRIGGER_SENTIMENTS = {"NEGATIVE"}
_TRIGGER_EMOTIONS   = {"frustration", "concern", "urgency"}

SYSTEM_PROMPT = """You are an AI assistant specialized in organizational intelligence for C-level executives.
Your task is to classify business communications by their BUSINESS IMPACT, not emotional tone.

Classify the message into EXACTLY ONE of these categories:
- Progress: successful advancement, completion, good news
- Neutral Update: informational, no risk, routine update
- Concern: potential issue, uncertainty, something to watch
- Risk: clear problem threatening delivery or outcome
- Blocked: work cannot continue, waiting on dependency
- Overload: team stress, excessive workload, burnout signals
- Conflict: disagreement, collaboration friction
- Urgent: requires immediate executive attention

IMPORTANT:
- Consider the author, source, and timestamp as context
- Return ONLY valid JSON, nothing else, no explanation outside JSON
- confidence must be a float between 0.0 and 1.0"""

USER_TEMPLATE = """Classify this business communication:

Source: {source}
Author: {author}
Timestamp: {timestamp}
Sentiment detected: {sentiment}
Emotion detected: {emotion}
Behavioral signals: {behavioral_context}

Message:
{content}

Return ONLY this JSON (no extra text):
{{"label": "<one of the 8 categories>", "confidence": <float 0.0-1.0>, "reason": "<one sentence>"}}"""


class BusinessClassifier(BaseProcessor):
    """
    Ollama-powered business classification.
    Triggered only for negative/concerning messages to reduce inference time.
    """

    def __init__(self, force: bool = False):
        """
        force=True  : classifie TOUS les messages.
        force=False : classifie uniquement les messages négatifs/préoccupants.
        """
        self.force = force
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=OLLAMA_BASE_URL,
                api_key="ollama",          # Ollama n'a pas besoin de clé réelle
            )
            logger.info(
                "[NLP/Business] Ollama client initialized — model: %s | url: %s",
                OLLAMA_MODEL, OLLAMA_BASE_URL,
            )
        return self._client

    def _should_classify(self, item: EnrichedItem) -> bool:
        if self.force:
            return True
        return (
            item.sentiment_label in _TRIGGER_SENTIMENTS
            or item.emotion_label in _TRIGGER_EMOTIONS
        )

    def process(self, item: EnrichedItem) -> EnrichedItem:
        if not self._should_classify(item):
            # Pas de signal négatif → label automatique basé sur le sentiment
            item.business_label      = "Progress" if item.sentiment_label == "POSITIVE" else "Neutral Update"
            item.business_confidence = 0.85
            item.business_reason     = "Auto-classified: no negative signal detected."
            return item

        result = _call_ollama(self._get_client(), item)
        if result:
            item.business_label      = result.get("label", "Neutral Update")
            item.business_confidence = float(result.get("confidence", 0.5))
            item.business_reason     = result.get("reason", "")
        else:
            # Fallback si Ollama ne répond pas
            item.business_label      = "Concern"
            item.business_confidence = 0.4
            item.business_reason     = "Classification failed — marked as Concern by default."
        return item


def _call_ollama(client, item: EnrichedItem) -> Optional[dict]:
    try:
        from nlp.behavioral import behavioral_context_summary
        behavioral_ctx = behavioral_context_summary(item.metadata)

        prompt = USER_TEMPLATE.format(
            source=item.source,
            author=item.author,
            timestamp=item.timestamp,
            sentiment=item.sentiment_label or "unknown",
            emotion=item.emotion_label or "unknown",
            behavioral_context=behavioral_ctx,
            content=item.content[:800],
        )
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            max_tokens=150,
        )
        raw = response.choices[0].message.content.strip()

        # Extraire le JSON même si Ollama ajoute du texte autour
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])

        logger.warning("[NLP/Business] No JSON found in response: %s", raw[:200])
        return None

    except json.JSONDecodeError as e:
        logger.warning("[NLP/Business] JSON parse error: %s", e)
        return None
    except Exception as e:
        logger.warning("[NLP/Business] Ollama call failed: %s", e)
        return None
