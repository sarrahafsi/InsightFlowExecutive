"""
Transcription — Speech-to-Text pour messages vocaux (Slack, Teams)
====================================================================
Moteur : faster-whisper (CTranslate2), local, décodage audio natif (PyAV) —
pas besoin d'installer ffmpeg séparément sur la machine.

Le texte transcrit devient le `content` du DataItem avant qu'il n'entre
dans le pipeline NLP (sentiment/emotion/topics/business) — celui-ci ne
voit donc jamais l'audio, uniquement du texte, et n'a besoin d'aucune
modification.
"""
from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache

import httpx

from ._model_lock import MODEL_LOAD_LOCK

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    # Verrou global (cf. _model_lock.py) : plusieurs jobs paralleles peuvent
    # tous declencher ce premier chargement en meme temps.
    with MODEL_LOAD_LOCK:
        from faster_whisper import WhisperModel
        from core.config import settings

        logger.info(
            "[NLP/Transcription] Loading Whisper model: %s (device=%s)",
            settings.whisper_model_size, settings.whisper_device,
        )
        return WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type="int8",
        )


def transcribe_audio(audio_bytes: bytes) -> str | None:
    """Transcrit un buffer audio en texte. Retourne None si échec (jamais d'exception)."""
    if not audio_bytes:
        return None
    tmp_path = None
    try:
        model = _load_model()
        # delete=False: on Windows the file must be closed before faster-whisper
        # (a separate process/handle, via PyAV) can open it for reading.
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        segments, _info = model.transcribe(tmp_path, language=None)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text or None
    except Exception as e:
        logger.warning("[NLP/Transcription] Transcription failed: %s", e)
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


async def download_and_transcribe(url: str, headers: dict) -> str | None:
    """Télécharge un fichier audio puis le transcrit (inférence en thread pour ne pas bloquer l'event loop)."""
    import asyncio

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "[NLP/Transcription] Download failed (%s) for %s — body: %s",
                    resp.status_code, url, resp.text[:300],
                )
                return None
            audio_bytes = resp.content
    except Exception as e:
        logger.warning("[NLP/Transcription] Download error for %s: %s", url, e)
        return None

    return await asyncio.to_thread(transcribe_audio, audio_bytes)
