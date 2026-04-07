"""
Behavioral Signals Processor — Organizational Intelligence Layer
================================================================
Extracts behavioral and temporal signals from message metadata.
No AI model needed — pure Python analytics.

Signals computed:
  Temporal  : hour_sent, is_weekend, is_after_hours
  Thread    : response_delay_min, thread_depth
  Author    : daily_volume
  Composite : burnout_score

Why this matters:
  "Meeting rescheduled" at 2am on Sunday + 3-day response delay
  = Burnout signal that text alone cannot detect.

These signals enrich the business classifier prompt,
enabling Ollama to make context-aware decisions.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from .base import BaseProcessor, EnrichedItem

logger = logging.getLogger(__name__)


class BehavioralProcessor(BaseProcessor):
    """
    Computes behavioral signals from message metadata.

    Requires EnrichedItem.metadata to contain:
      - 'thread_messages' : list[dict] with 'timestamp' keys (optional)
      - 'author_daily_count': int (optional, injected by ETL)
    """

    def process(self, item: EnrichedItem) -> EnrichedItem:
        ts = _parse_timestamp(item.timestamp)
        if not ts:
            return item

        # ── Temporal signals ──────────────────────────────────
        item.metadata["hour_sent"]      = ts.hour
        item.metadata["is_weekend"]     = ts.weekday() >= 5
        item.metadata["is_after_hours"] = ts.hour < 8 or ts.hour > 20

        # ── Thread signals ────────────────────────────────────
        thread_msgs = item.metadata.get("thread_messages", [])
        if thread_msgs:
            item.metadata["thread_depth"]       = len(thread_msgs)
            item.metadata["response_delay_min"] = _compute_response_delay(ts, thread_msgs)
        else:
            item.metadata["thread_depth"]       = 1
            item.metadata["response_delay_min"] = None

        # ── Author volume ─────────────────────────────────────
        item.metadata["daily_volume"] = item.metadata.get("author_daily_count", 1)

        # ── Burnout score (composite 0.0–1.0) ────────────────
        item.metadata["burnout_score"] = _compute_burnout_score(item.metadata)

        return item


def _parse_timestamp(ts) -> Optional[datetime]:
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(ts[:19], fmt[:len(fmt)])
            except ValueError:
                continue
    return None


def _compute_response_delay(current_ts: datetime, thread_msgs: list[dict]) -> Optional[int]:
    """Returns minutes since the previous message in the thread."""
    timestamps = []
    for msg in thread_msgs:
        t = _parse_timestamp(msg.get("timestamp", ""))
        if t and t < current_ts:
            timestamps.append(t)
    if not timestamps:
        return None
    prev = max(timestamps)
    return int((current_ts - prev).total_seconds() / 60)


def _compute_burnout_score(meta: dict) -> float:
    """
    Composite burnout score — 0.0 (healthy) to 1.0 (high risk).

    Factors:
      - After hours message       : +0.30
      - Weekend message           : +0.25
      - Night message (0h-5h)     : +0.35 (strongest signal)
      - Response delay > 2 days   : +0.20
      - Daily volume > 30 msgs    : +0.20
      - Thread depth > 15         : +0.10
    """
    score = 0.0
    hour         = meta.get("hour_sent", 12)
    is_weekend   = meta.get("is_weekend", False)
    is_ah        = meta.get("is_after_hours", False)
    delay        = meta.get("response_delay_min") or 0
    volume       = meta.get("daily_volume", 1)
    thread_depth = meta.get("thread_depth", 1)

    # Night message (strongest burnout signal)
    if 0 <= hour <= 5:
        score += 0.35
    elif is_ah:
        score += 0.30

    if is_weekend:
        score += 0.25

    if delay > 2880:      # > 2 days
        score += 0.20
    elif delay > 1440:    # > 1 day
        score += 0.10

    if volume > 30:
        score += 0.20
    elif volume > 20:
        score += 0.10

    if thread_depth > 15:
        score += 0.10

    return round(min(score, 1.0), 3)


# ── Utility : enrich Ollama prompt with behavioral context ────

def behavioral_context_summary(metadata: dict) -> str:
    """
    Returns a human-readable summary of behavioral signals
    to inject into the Ollama business classifier prompt.
    """
    signals = []
    hour    = metadata.get("hour_sent")
    weekend = metadata.get("is_weekend", False)
    delay   = metadata.get("response_delay_min")
    volume  = metadata.get("daily_volume", 1)
    burnout = metadata.get("burnout_score", 0.0)

    if hour is not None:
        if 0 <= hour <= 5:
            signals.append(f"⚠ Sent at {hour:02d}:xx (night — strong burnout signal)")
        elif hour > 20 or hour < 8:
            signals.append(f"Sent outside business hours ({hour:02d}:xx)")

    if weekend:
        signals.append("Sent on weekend")

    if delay is not None:
        if delay > 2880:
            signals.append(f"Response delay: {delay//1440} days (team may be blocked)")
        elif delay > 480:
            signals.append(f"Response delay: {delay//60}h (slow response)")

    if volume > 30:
        signals.append(f"Author sent {volume} messages today (overload signal)")

    if burnout >= 0.6:
        signals.append(f"Burnout score: {burnout} (HIGH RISK)")
    elif burnout >= 0.3:
        signals.append(f"Burnout score: {burnout} (moderate)")

    if not signals:
        return "No behavioral anomalies detected."
    return " | ".join(signals)
