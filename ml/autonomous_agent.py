"""
InsightFlow — Autonomous Learning Agent
========================================
Replaces the hardcoded threshold logic in ml_scheduler.py with
intelligent, context-aware decision making.

Loop: Perceive → Reason → Plan → Act → Log

Usage:
    python autonomous_agent.py              # live run
    python autonomous_agent.py --dry-run    # analyze without acting
    python autonomous_agent.py --dry-run --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

ML_DIR      = Path(__file__).parent
REPORTS_DIR = ML_DIR / "training_reports"
MONITOR_DIR = ML_DIR / "monitoring_reports"
AGENT_DIR   = ML_DIR / "agent_logs"
AGENT_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/insightflow")

_OLLAMA_BASE      = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/v1")
OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "llama3.2")
AZURE_KEY         = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_DEPLOYMENT  = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
OPENAI_KEY        = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL      = os.getenv("OPENAI_MODEL", "gpt-4o")


# ══════════════════════════════════════════════════════════════════════
# AGENT
# ══════════════════════════════════════════════════════════════════════

class AutonomousLearningAgent:
    """
    Perceives correction patterns, reasons about root causes via LLM,
    and selects the optimal retraining strategy — no hardcoded thresholds.
    """

    # ── 1. Perception ────────────────────────────────────────────────────

    def _analyze_corrections(self) -> dict:
        """Query PostgreSQL for correction patterns and confusion analysis."""
        try:
            conn = psycopg2.connect(DB_URL)
            cur  = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE corrected_sentiment IS NOT NULL AND NOT used_in_training) AS sentiment_count,
                    COUNT(*) FILTER (WHERE corrected_emotion   IS NOT NULL AND NOT used_in_training) AS emotion_count,
                    COUNT(*) FILTER (WHERE corrected_business  IS NOT NULL AND NOT used_in_training) AS business_count,
                    COUNT(*) FILTER (WHERE NOT used_in_training)                                    AS total_pending
                FROM human_corrections
            """)
            counts = dict(cur.fetchone())

            cur.execute("""
                SELECT original_emotion, corrected_emotion, COUNT(*) AS count
                FROM human_corrections
                WHERE corrected_emotion IS NOT NULL AND NOT used_in_training
                  AND original_emotion IS NOT NULL
                  AND original_emotion != corrected_emotion
                GROUP BY original_emotion, corrected_emotion
                ORDER BY count DESC LIMIT 10
            """)
            emotion_confusions = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT original_sentiment, corrected_sentiment, COUNT(*) AS count
                FROM human_corrections
                WHERE corrected_sentiment IS NOT NULL AND NOT used_in_training
                  AND original_sentiment IS NOT NULL
                  AND original_sentiment != corrected_sentiment
                GROUP BY original_sentiment, corrected_sentiment
                ORDER BY count DESC LIMIT 10
            """)
            sentiment_confusions = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE corrected_at >= NOW() - INTERVAL '3 days' AND NOT used_in_training)  AS recent_3d,
                    COUNT(*) FILTER (WHERE corrected_at >= NOW() - INTERVAL '7 days' AND NOT used_in_training)  AS recent_7d,
                    MIN(corrected_at) FILTER (WHERE NOT used_in_training) AS oldest_pending,
                    MAX(corrected_at) FILTER (WHERE NOT used_in_training) AS newest_pending
                FROM human_corrections
            """)
            timing = {k: str(v) if v else None for k, v in dict(cur.fetchone()).items()}

            cur.close()
            conn.close()

            ec = counts.get("emotion_count", 0)
            sc = counts.get("sentiment_count", 0)

            dominant_emotion    = emotion_confusions[0]    if emotion_confusions    else None
            dominant_sentiment  = sentiment_confusions[0]  if sentiment_confusions  else None

            # Systematic = same confusion pattern >= 60% of that task's corrections
            emotion_systematic   = (dominant_emotion["count"]   / ec  >= 0.60) if dominant_emotion   and ec  > 0 else False
            sentiment_systematic = (dominant_sentiment["count"] / sc  >= 0.60) if dominant_sentiment and sc > 0 else False

            return {
                "counts":                     counts,
                "emotion_confusions":         emotion_confusions[:3],
                "sentiment_confusions":       sentiment_confusions[:3],
                "dominant_emotion":           dominant_emotion,
                "dominant_sentiment":         dominant_sentiment,
                "emotion_systematic":         emotion_systematic,
                "sentiment_systematic":       sentiment_systematic,
                "timing":                     timing,
            }
        except Exception as e:
            print(f"[Agent] DB error: {e}")
            return {"error": str(e), "counts": {"sentiment_count": 0, "emotion_count": 0, "total_pending": 0}}

    def _get_last_training_metrics(self) -> dict:
        """Load metrics from most recent training reports."""
        metrics: dict = {}
        for task in ("sentiment", "emotion"):
            files = sorted(REPORTS_DIR.glob(f"cl-{task}-*.json"), reverse=True)
            if files:
                try:
                    with open(files[0]) as f:
                        d = json.load(f)
                    metrics[task] = {
                        "eval_f1":      d.get("eval_f1"),
                        "champion_f1":  d.get("champion_f1"),
                        "promoted":     d.get("promoted"),
                        "trained_at":   d.get("trained_at"),
                        "run_id":       d.get("run_id"),
                    }
                except Exception:
                    pass
        return metrics

    def _get_monitoring_status(self) -> dict:
        """Load most recent drift monitoring reports."""
        statuses: dict = {}
        for task in ("sentiment", "emotion"):
            files = sorted(MONITOR_DIR.glob(f"{task}-*.json"), reverse=True)
            if files:
                try:
                    with open(files[0]) as f:
                        d = json.load(f)
                    statuses[task] = {
                        "overall_status":  d.get("overall_status"),
                        "recommendation":  d.get("recommendation"),
                        "generated_at":    d.get("generated_at"),
                    }
                except Exception:
                    pass
        return statuses

    # ── 2. Reasoning ─────────────────────────────────────────────────────

    def _reason_with_llm(self, context: dict) -> dict:
        """Use LLM to reason about root cause and decide optimal strategy."""

        system = (
            "You are an autonomous MLOps agent for an executive AI dashboard.\n"
            "Analyze NLP model correction patterns and choose the optimal retraining strategy.\n\n"
            "Available strategies:\n"
            "  targeted_emotion    — fine-tune emotion model on specific confusing label pair only\n"
            "  targeted_sentiment  — fine-tune sentiment model on specific confusing label pair only\n"
            "  full_emotion        — retrain full emotion model on all corrections\n"
            "  full_sentiment      — retrain full sentiment model on all corrections\n"
            "  full_both           — retrain both models\n"
            "  wait                — insufficient signal, collect more corrections first\n\n"
            "Respond ONLY with valid JSON, no markdown, no extra text."
        )

        user = (
            f"Current system state:\n{json.dumps(context, indent=2, default=str)}\n\n"
            "Respond with:\n"
            "{\n"
            '  "root_cause": "one sentence why corrections are accumulating",\n'
            '  "strategy": "one of the strategies above",\n'
            '  "label_filter": "comma-separated labels if targeted (e.g. frustration,urgency) or null",\n'
            '  "reasoning": "2-3 sentences of step-by-step reasoning",\n'
            '  "confidence": "high|medium|low",\n'
            '  "urgency": "immediate|tonight|can_wait",\n'
            '  "estimated_improvement": "brief expected gain"\n'
            "}"
        )

        raw = self._call_llm(system, user)

        try:
            text = raw.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            parsed = json.loads(text)
            parsed["llm_used"] = True
            return parsed
        except Exception:
            print("[Agent] LLM response not parseable — using rule-based fallback")
            return self._rule_based_fallback(context)

    def _call_llm(self, system: str, user: str) -> str:
        """Call LLM with fallback chain: Azure → OpenAI → Ollama."""
        if AZURE_KEY and AZURE_ENDPOINT:
            try:
                from openai import AzureOpenAI
                client = AzureOpenAI(
                    api_key=AZURE_KEY,
                    azure_endpoint=AZURE_ENDPOINT,
                    api_version=AZURE_API_VERSION,
                )
                resp = client.chat.completions.create(
                    model=AZURE_DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                print(f"[Agent] Azure failed ({e}), trying OpenAI...")

        if OPENAI_KEY:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_KEY)
                resp = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                print(f"[Agent] OpenAI failed ({e}), trying Ollama...")

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{_OLLAMA_BASE}/api/generate",
                    json={
                        "model":   OLLAMA_MODEL,
                        "prompt":  f"{system}\n\n{user}",
                        "stream":  False,
                        "options": {"temperature": 0.1, "num_predict": 500},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except Exception as e:
            print(f"[Agent] Ollama failed ({e}), using rule-based fallback")
            return ""

    def _rule_based_fallback(self, context: dict) -> dict:
        """Deterministic fallback when no LLM is available."""
        corr   = context.get("corrections", {})
        counts = corr.get("counts", {})
        drift  = context.get("drift", {})

        ec = counts.get("emotion_count", 0)
        sc = counts.get("sentiment_count", 0)
        emotion_drift    = drift.get("emotion",    {}).get("overall_status") in ("alert", "warning")
        sentiment_drift  = drift.get("sentiment",  {}).get("overall_status") in ("alert", "warning")

        if corr.get("emotion_systematic") and ec >= 5:
            dom = corr.get("dominant_emotion", {})
            lf  = f"{dom.get('original_emotion')},{dom.get('corrected_emotion')}" if dom else None
            return {
                "root_cause":             f"Systematic emotion confusion ({ec} corrections, same pattern)",
                "strategy":               "targeted_emotion",
                "label_filter":           lf,
                "reasoning":              "High concentration of same-type emotion corrections — targeted fine-tuning is more efficient than full retrain.",
                "confidence":             "high",
                "urgency":                "tonight" if ec >= 20 else "can_wait",
                "estimated_improvement":  "+2–5% F1 on confusing labels",
                "llm_used":               False,
            }

        if corr.get("sentiment_systematic") and sc >= 5:
            dom = corr.get("dominant_sentiment", {})
            lf  = f"{dom.get('original_sentiment')},{dom.get('corrected_sentiment')}" if dom else None
            return {
                "root_cause":             f"Systematic sentiment confusion ({sc} corrections, same pattern)",
                "strategy":               "targeted_sentiment",
                "label_filter":           lf,
                "reasoning":              "Concentrated sentiment corrections indicate domain shift for a specific sentiment class.",
                "confidence":             "high",
                "urgency":                "tonight" if sc >= 20 else "can_wait",
                "estimated_improvement":  "+2–4% F1 on confusing labels",
                "llm_used":               False,
            }

        if (ec >= 20 or emotion_drift) and ec >= 5:
            return {
                "root_cause":             "Sufficient emotion corrections or drift detected",
                "strategy":               "full_emotion",
                "label_filter":           None,
                "reasoning":              "Corrections distributed across labels — general retrain warranted.",
                "confidence":             "medium",
                "urgency":                "tonight",
                "estimated_improvement":  "+1–3% overall F1",
                "llm_used":               False,
            }

        if (sc >= 20 or sentiment_drift) and sc >= 5:
            return {
                "root_cause":             "Sufficient sentiment corrections or drift detected",
                "strategy":               "full_sentiment",
                "label_filter":           None,
                "reasoning":              "Corrections distributed across labels — general retrain warranted.",
                "confidence":             "medium",
                "urgency":                "tonight",
                "estimated_improvement":  "+1–3% overall F1",
                "llm_used":               False,
            }

        return {
            "root_cause":             f"Insufficient corrections ({counts.get('total_pending', 0)} pending)",
            "strategy":               "wait",
            "label_filter":           None,
            "reasoning":              "Not enough signal to identify a systematic problem. Collecting more corrections.",
            "confidence":             "high",
            "urgency":                "can_wait",
            "estimated_improvement":  "N/A",
            "llm_used":               False,
        }

    # ── 3. Execution ─────────────────────────────────────────────────────

    def _execute_decision(self, decision: dict, min_samples: int, epochs: int,
                          dry_run: bool) -> dict:
        """Run the fine-tuning subprocess according to the chosen strategy."""
        strategy = decision.get("strategy", "wait")
        urgency  = decision.get("urgency", "can_wait")

        if strategy == "wait" or urgency == "can_wait":
            return {"executed": False, "reason": "strategy=wait or urgency=can_wait"}

        script = ML_DIR / "continuous_learning.py"
        if not script.exists():
            return {"executed": False, "reason": f"continuous_learning.py not found at {script}"}

        if dry_run:
            return {"executed": False, "reason": "dry_run — no action taken",
                    "would_have_run": strategy,
                    "label_filter":   decision.get("label_filter")}

        task_map = {
            "targeted_emotion":   "emotion",
            "targeted_sentiment": "sentiment",
            "full_emotion":       "emotion",
            "full_sentiment":     "sentiment",
            "full_both":          "all",
        }
        task = task_map.get(strategy)
        if not task:
            return {"executed": False, "reason": f"Unknown strategy: {strategy}"}

        cmd = [
            sys.executable, str(script),
            "--task",        task,
            "--min-samples", str(min_samples),
            "--epochs",      str(epochs),
        ]
        label_filter = decision.get("label_filter")
        if label_filter and strategy.startswith("targeted"):
            cmd += ["--label-filter", label_filter]

        print(f"[Agent] Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=7200, cwd=str(ML_DIR),
                env={**os.environ, "DATABASE_URL": DB_URL},
            )
            return {
                "executed":     True,
                "task":         task,
                "label_filter": label_filter,
                "returncode":   result.returncode,
                "status":       "success" if result.returncode == 0 else "failed",
                "stdout_tail":  result.stdout[-400:] if result.stdout else "",
                "stderr_tail":  result.stderr[-200:] if result.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired:
            return {"executed": True, "task": task, "status": "timeout"}
        except Exception as e:
            return {"executed": True, "task": task, "status": "error", "reason": str(e)}

    # ── 4. Logging ────────────────────────────────────────────────────────

    def _save_log(self, entry: dict) -> Path:
        ts   = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        uid  = uuid.uuid4().hex[:4]
        path = AGENT_DIR / f"agent-{ts}-{uid}.json"
        with open(path, "w") as f:
            json.dump(entry, f, indent=2, default=str)
        print(f"[Agent] Log → {path.name}")
        return path

    def get_recent_logs(self, n: int = 20) -> list[dict]:
        files = sorted(AGENT_DIR.glob("agent-*.json"), reverse=True)[:n]
        result = []
        for f in files:
            try:
                with open(f) as fp:
                    result.append(json.load(fp))
            except Exception:
                pass
        return result

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self, min_samples: int = 5, epochs: int = 3, dry_run: bool = False) -> dict:
        """
        Full agent loop:
          1. Perceive   — read corrections, drift, training metrics
          2. Reason     — LLM diagnoses root cause, chooses strategy
          3. Act        — run fine-tuning subprocess (unless dry_run)
          4. Log        — save full decision trace to agent_logs/
        """
        started = datetime.utcnow()
        print(f"\n{'='*60}")
        print(f"[Agent] InsightFlow Autonomous Learning Agent")
        print(f"[Agent] {started.strftime('%Y-%m-%d %H:%M UTC')}  mode={'DRY-RUN' if dry_run else 'LIVE'}")
        print(f"{'='*60}\n")

        # Perceive
        print("[Agent] Step 1 — Perceiving...")
        corrections     = self._analyze_corrections()
        training_metrics = self._get_last_training_metrics()
        drift_status    = self._get_monitoring_status()

        tp = corrections.get("counts", {}).get("total_pending", 0)
        ec = corrections.get("counts", {}).get("emotion_count", 0)
        sc = corrections.get("counts", {}).get("sentiment_count", 0)
        print(f"[Agent] Pending corrections — total={tp}, emotion={ec}, sentiment={sc}")
        print(f"[Agent] Systematic — emotion={corrections.get('emotion_systematic')}, sentiment={corrections.get('sentiment_systematic')}")

        context = {
            "corrections":      corrections,
            "training_metrics": training_metrics,
            "drift":            drift_status,
        }

        # Reason
        print("\n[Agent] Step 2 — Reasoning...")
        decision = self._reason_with_llm(context)
        print(f"[Agent] Strategy  : {decision.get('strategy')}")
        print(f"[Agent] Urgency   : {decision.get('urgency')}")
        print(f"[Agent] Root cause: {decision.get('root_cause')}")
        print(f"[Agent] Reasoning : {decision.get('reasoning')}")
        print(f"[Agent] LLM used  : {decision.get('llm_used', False)}")

        # Act
        print("\n[Agent] Step 3 — Acting...")
        execution = self._execute_decision(decision, min_samples, epochs, dry_run)
        print(f"[Agent] Executed={execution.get('executed')}  status={execution.get('status', 'N/A')}")

        # Log
        log = {
            "agent_run_id": f"agent-{started.strftime('%Y%m%d-%H%M%S')}",
            "timestamp":    started.isoformat(),
            "dry_run":      dry_run,
            "perception": {
                "total_pending":          tp,
                "emotion_count":          ec,
                "sentiment_count":        sc,
                "emotion_systematic":     corrections.get("emotion_systematic"),
                "sentiment_systematic":   corrections.get("sentiment_systematic"),
                "dominant_emotion":       corrections.get("dominant_emotion"),
                "dominant_sentiment":     corrections.get("dominant_sentiment"),
                "drift_emotion":          drift_status.get("emotion", {}).get("overall_status"),
                "drift_sentiment":        drift_status.get("sentiment", {}).get("overall_status"),
            },
            "decision":  decision,
            "execution": execution,
            "duration_seconds": (datetime.utcnow() - started).total_seconds(),
        }
        self._save_log(log)

        print(f"\n[Agent] Done in {log['duration_seconds']:.1f}s")
        return log


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightFlow Autonomous Learning Agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyze and reason without executing fine-tuning")
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--epochs",      type=int, default=3)
    args = parser.parse_args()

    agent  = AutonomousLearningAgent()
    result = agent.run(min_samples=args.min_samples, epochs=args.epochs, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print(f"[Agent] Final decision : {result['decision'].get('strategy')}")
    print(f"[Agent] Executed       : {result['execution'].get('executed')}")
    if result["execution"].get("executed"):
        print(f"[Agent] Status         : {result['execution'].get('status')}")
    print(f"{'='*60}")
    sys.exit(0)
