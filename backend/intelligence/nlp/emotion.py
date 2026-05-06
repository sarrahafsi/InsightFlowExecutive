"""
Emotion Processor — 3-Level Pipeline
=====================================
Niveau 1 : distilRoBERTa fine-tuné (insightflow-emotion-v1)
Niveau 2 : Temperature Scaling — calibration des scores (Guo et al. 2017)
Niveau 3 : Ollama LLM arbitre — si score calibré < seuil

Labels business : frustration | concern | urgency | neutral | satisfaction
Langues supportées : FR + EN (XLM-RoBERTa multilingue)
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Optional

import numpy as np

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)

_BACKEND_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_MODEL  = os.path.join(_BACKEND_DIR, "..", "ml", "models", "insightflow-emotion-xlm-v1")
# Fallback dev uniquement — XLM-RoBERTa multilingue pré-entraîné sur émotions
_REMOTE_MODEL = "MilaNLProc/xlm-emo-t"
_TEMP_FILE    = os.path.join(_LOCAL_MODEL, "temperature.json")

EMOTION_MODEL = _LOCAL_MODEL if os.path.isdir(_LOCAL_MODEL) else _REMOTE_MODEL
MAX_LENGTH    = 512

LABELS = ["frustration", "concern", "urgency", "neutral", "satisfaction"]

# Seuil de confiance calibrée — en dessous → Ollama prend le relais
CONFIDENCE_THRESHOLD = 0.38

# Mapping remote fallback (MilaNLProc/xlm-emo-t) → labels business
# Utilisé uniquement si le modèle local fine-tuné n'existe pas encore
# xlm-emo-t labels : anger | fear | joy | sadness
_EMOTION_MAP_FALLBACK = {
    "anger":   "frustration",
    "fear":    "concern",
    "joy":     "satisfaction",
    "sadness": "concern",   # sadness → concern (label business le plus proche)
}
_FINE_TUNED_LABELS = set(LABELS)


# ── Niveau 1 : Modèle ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_pipeline():
    from transformers import pipeline
    source = "local" if os.path.isdir(_LOCAL_MODEL) else "HuggingFace"
    logger.info("[NLP/Emotion] Loading model (%s): %s", source, EMOTION_MODEL)
    return pipeline(
        "text-classification",
        model=EMOTION_MODEL,
        truncation=True,
        max_length=MAX_LENGTH,
        top_k=None,
    )


# ── Niveau 2 : Temperature Scaling ───────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_temperature() -> float:
    """Charge T depuis temperature.json si disponible, sinon T=1.0 (pas de calibration)."""
    if os.path.isfile(_TEMP_FILE):
        try:
            with open(_TEMP_FILE) as f:
                data = json.load(f)
            T = float(data.get("temperature", 1.0))
            logger.info("[NLP/Emotion] Temperature loaded: T=%.4f (ECE: %.4f → %.4f)",
                        T, data.get("ece_before", 0), data.get("ece_after", 0))
            return T
        except Exception as e:
            logger.warning("[NLP/Emotion] Could not load temperature.json: %s", e)
    logger.info("[NLP/Emotion] No calibration found — using T=1.0")
    return 1.0


def _softmax(scores: list[float]) -> np.ndarray:
    arr = np.array(scores)
    e   = np.exp(arr - arr.max())
    return e / e.sum()


def _calibrate(raw_scores: dict[str, float], T: float) -> dict[str, float]:
    """Applique Temperature Scaling : logits / T → softmax."""
    logits = np.log(np.clip(
        np.array([raw_scores.get(l, 1e-7) for l in LABELS]), 1e-7, 1.0
    ))
    calibrated = _softmax((logits / T).tolist())
    return {l: float(calibrated[i]) for i, l in enumerate(LABELS)}


# ── Niveau 3 : Ollama LLM arbitre ────────────────────────────────────────────

def _ollama_emotion(text: str, sentiment: str, candidates: dict[str, float]) -> Optional[str]:
    """
    Appelle Ollama pour arbitrer quand le modèle n'est pas confiant.
    Retourne le label business ou None si Ollama est indisponible.
    """
    try:
        import httpx
        from core.config import settings

        prompt = f"""You are an expert in professional communication analysis for C-level executives.

Analyze the TONE, SUBTEXT, and IMPLICIT MEANING of this message.
Choose EXACTLY ONE emotion from: frustration, concern, urgency, neutral, satisfaction

Message: "{text[:400]}"
Overall sentiment: {sentiment}

Definitions and examples:
- frustration: irritation, disappointment, things not working as expected, repeated problems, "I don't understand why...", "this is the 3rd time..."
- concern: worry about a future risk, uncertainty, "I'm not sure if...", "this might be a problem", something to watch
- urgency: time pressure, imminent deadline, need for immediate action, "we need to act now", "by tomorrow"
- neutral: purely informational, no emotional charge, meeting reminders, status updates with no risk
- satisfaction: positive outcome, achievement, good news, progress, "it worked", "the client is happy"

IMPORTANT RULES:
- Read between the lines — professional emails rarely state emotions explicitly
- Only choose "neutral" if the message is purely factual with ZERO emotional charge
- A message saying "I don't understand how we got here" is frustration, not neutral
- A message about scalability doubts is concern, not neutral
- A message with an implicit deadline is urgency, not neutral

Reply with ONLY the single word (frustration/concern/urgency/neutral/satisfaction):"""

        resp = httpx.post(
            f"{settings.ollama_base_url.rstrip('/v1')}/api/generate",
            json={
                "model":   settings.ollama_model,
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.0, "num_predict": 10},
            },
            timeout=15.0,
        )
        if resp.status_code == 200:
            answer = resp.json().get("response", "").strip().lower()
            for label in LABELS:
                if label in answer:
                    logger.debug("[NLP/Emotion] Ollama arbitre → %s (was ambiguous)", label)
                    return label
    except Exception as e:
        logger.debug("[NLP/Emotion] Ollama unavailable: %s", e)
    return None


# ── Pipeline complet ──────────────────────────────────────────────────────────

class EmotionProcessor(BaseProcessor):
    def process(self, item: EnrichedItem) -> EnrichedItem:
        result = _classify(item.content, sentiment_label=item.sentiment_label or "")
        if result:
            item.emotion_label = result["label"]
            item.emotion_score = round(result["score"], 4)
        return item


def _classify(text: str, sentiment_label: str = "") -> Optional[dict]:
    try:
        pipe = _load_pipeline()
        T    = _load_temperature()

        # ── Niveau 1 : inférence brute ────────────────────────
        outputs    = pipe(text[:1000])[0]  # liste de {label, score}
        raw_scores = {item["label"].lower(): item["score"] for item in outputs}

        # Mapper labels fallback → business si nécessaire
        mapped_scores: dict[str, float] = {}
        for raw_label, score in raw_scores.items():
            if raw_label in _FINE_TUNED_LABELS:
                mapped_scores[raw_label] = score
            else:
                biz = _EMOTION_MAP_FALLBACK.get(raw_label, "neutral")
                mapped_scores[biz] = mapped_scores.get(biz, 0.0) + score

        # ── Niveau 2 : calibration ────────────────────────────
        calibrated = _calibrate(mapped_scores, T)
        best_label = max(calibrated, key=calibrated.get)
        best_score = calibrated[best_label]

        logger.debug(
            "[NLP/Emotion] L1=%s(%.2f) → calibrated=%s(%.2f) T=%.2f",
            max(mapped_scores, key=mapped_scores.get),
            max(mapped_scores.values()),
            best_label, best_score, T,
        )

        # ── Niveau 3 : Ollama si score < seuil ───────────────
        if best_score < CONFIDENCE_THRESHOLD:
            ollama_label = _ollama_emotion(text, sentiment_label, calibrated)
            if ollama_label:
                return {"label": ollama_label, "score": best_score}

        return {"label": best_label, "score": round(best_score, 4)}

    except Exception as e:
        logger.warning("[NLP/Emotion] Classification failed: %s", e)
        return None
