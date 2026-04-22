"""
InsightFlow MLOps — Model Monitoring & Drift Detection
=======================================================
Détecte la dégradation du modèle en production sans attendre une soutenance.

Trois types de dérive détectés :
  1. Performance drift   — F1 du champion sur les corrections récentes < baseline
  2. Distribution drift  — la distribution des labels prédit a changé (KL divergence)
  3. Confidence drift    — la confiance moyenne du modèle a baissé

Usage direct :
    python monitoring.py --task sentiment
    python monitoring.py --task all --window-days 30

Utilisé aussi par le backend via import direct :
    from ml.monitoring import run_monitoring_report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from scipy.stats import entropy as kl_divergence, chisquare

# ── Chemins ────────────────────────────────────────────────────────────
ML_DIR      = Path(__file__).parent
MODELS_DIR  = ML_DIR / "models"
REPORTS_DIR = ML_DIR / "training_reports"
MONITOR_DIR = ML_DIR / "monitoring_reports"
MONITOR_DIR.mkdir(exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/insightflow"
)

# Seuils d'alerte
PERF_DRIFT_THRESHOLD  = 0.10   # F1 drop > 10% → alerte
DIST_DRIFT_THRESHOLD  = 0.15   # KL divergence > 0.15 → alerte
CONF_DRIFT_THRESHOLD  = 0.10   # Confidence drop > 10% → alerte
MIN_SAMPLES_MONITOR   = 10     # Minimum de corrections pour évaluer

SENTIMENT_LABELS = {"POSITIVE": 0, "NEUTRAL": 1, "NEGATIVE": 2}
EMOTION_LABELS   = {
    "satisfaction": 0, "neutral": 1,
    "concern": 2, "urgency": 3, "frustration": 4,
}


# ══════════════════════════════════════════════════════════════════════
# 1. CHARGEMENT DU MODÈLE CHAMPION (MLflow registry)
# ══════════════════════════════════════════════════════════════════════

def _load_champion_path(task: str) -> str | None:
    """Retourne le chemin local du modèle champion via l'alias MLflow."""
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow_dir = ML_DIR / "mlruns"
        mlflow.set_tracking_uri(f"file://{mlflow_dir}")
        client = MlflowClient()

        mv = client.get_model_version_by_alias(f"insightflow-{task}", "champion")
        path = mv.source.replace("file://", "")
        print(f"[Monitor] Champion chargé depuis MLflow : v{mv.version} → {path}")
        return path
    except Exception:
        pass

    # Fallback : dossier "latest" sur disque
    for candidate in [
        MODELS_DIR / f"insightflow-{task}-latest",
        MODELS_DIR / f"insightflow-{task}-v1",
        MODELS_DIR / f"insightflow-{task}-xlm-v1" if task == "sentiment"
        else MODELS_DIR / f"insightflow-{task}-v1",
    ]:
        if candidate.exists():
            print(f"[Monitor] Fallback modèle local : {candidate}")
            return str(candidate)

    print(f"[Monitor] Aucun modèle trouvé pour {task}")
    return None


# ══════════════════════════════════════════════════════════════════════
# 2. DONNÉES DE RÉFÉRENCE (baseline du dernier training)
# ══════════════════════════════════════════════════════════════════════

def _load_baseline(task: str) -> dict | None:
    """
    Charge les métriques du dernier run réussi depuis les rapports JSON.
    C'est notre référence pour comparer la performance actuelle.
    """
    reports = sorted(REPORTS_DIR.glob(f"cl-{task}-*.json"), reverse=True)
    if not reports:
        print(f"[Monitor] Aucun rapport d'entraînement trouvé pour {task}")
        return None
    with open(reports[0]) as f:
        report = json.load(f)
    print(f"[Monitor] Baseline : {reports[0].name} — F1={report.get('eval_f1', 'N/A')}")
    return report


# ══════════════════════════════════════════════════════════════════════
# 3. CORRECTIONS RÉCENTES (fenêtre de monitoring)
# ══════════════════════════════════════════════════════════════════════

def _fetch_recent_corrections(task: str, window_days: int) -> pd.DataFrame:
    """
    Récupère les corrections humaines récentes (utilisées ou non en training).
    Ces données servent à estimer la performance courante du modèle.
    """
    col_map = {
        "sentiment": ("corrected_sentiment", "original_sentiment"),
        "emotion":   ("corrected_emotion",   "original_emotion"),
    }
    if task not in col_map:
        return pd.DataFrame()

    corrected_col, original_col = col_map[task]
    since = datetime.utcnow() - timedelta(days=window_days)

    try:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT id,
                   text_snapshot       AS text,
                   {corrected_col}     AS true_label,
                   {original_col}      AS predicted_label,
                   corrected_at
            FROM human_corrections
            WHERE {corrected_col} IS NOT NULL
              AND text_snapshot IS NOT NULL
              AND LENGTH(text_snapshot) > 20
              AND corrected_at >= %s
            ORDER BY corrected_at DESC
        """, (since,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        df = pd.DataFrame(rows)
        print(f"[Monitor] {len(df)} corrections récentes (window={window_days}j, task={task})")
        return df
    except Exception as e:
        print(f"[Monitor] Erreur DB : {e}")
        return pd.DataFrame()


def _fetch_recent_predictions(task: str, window_days: int) -> pd.DataFrame:
    """
    Récupère les prédictions NLP récentes sur les messages (depuis messages_raw).
    Utilisé pour détecter le drift de distribution.
    """
    col_map = {
        "sentiment": ("sentiment_label", "sentiment_score"),
        "emotion":   ("emotion_label",   "emotion_score"),
    }
    if task not in col_map:
        return pd.DataFrame()

    label_col, score_col = col_map[task]
    since = datetime.utcnow() - timedelta(days=window_days)

    try:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT {label_col} AS label,
                   {score_col} AS confidence,
                   timestamp
            FROM messages_raw
            WHERE {label_col} IS NOT NULL
              AND timestamp >= %s
            ORDER BY timestamp DESC
            LIMIT 2000
        """, (since,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        df = pd.DataFrame(rows)
        print(f"[Monitor] {len(df)} prédictions récentes pour distribution drift ({task})")
        return df
    except Exception as e:
        print(f"[Monitor] Erreur DB predictions : {e}")
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════
# 4. PERFORMANCE DRIFT — F1 sur corrections récentes
# ══════════════════════════════════════════════════════════════════════

def detect_performance_drift(task: str, corrections_df: pd.DataFrame,
                              model_path: str) -> dict:
    """
    Évalue le champion sur les corrections récentes (ground truth = label corrigé).
    Compare avec le F1 baseline du dernier training.
    """
    result = {
        "check": "performance_drift",
        "status": "ok",
        "details": {},
    }

    if corrections_df.empty or len(corrections_df) < MIN_SAMPLES_MONITOR:
        result["status"]  = "skipped"
        result["reason"]  = f"Pas assez de corrections ({len(corrections_df)}/{MIN_SAMPLES_MONITOR})"
        return result

    label_map = SENTIMENT_LABELS if task == "sentiment" else EMOTION_LABELS
    valid = corrections_df[corrections_df["true_label"].isin(label_map)].copy()
    if len(valid) < MIN_SAMPLES_MONITOR:
        result["status"] = "skipped"
        result["reason"] = f"Labels valides insuffisants ({len(valid)})"
        return result

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        from sklearn.metrics import f1_score, accuracy_score

        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model     = AutoModelForSequenceClassification.from_pretrained(model_path)
        model.eval()

        texts  = list(valid["text"])
        labels = [label_map[l] for l in valid["true_label"]]

        encodings = tokenizer(texts, truncation=True, padding=True,
                              max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**encodings).logits
        preds = torch.argmax(logits, dim=1).numpy()

        current_f1  = float(f1_score(labels, preds, average="macro", zero_division=0))
        current_acc = float(accuracy_score(labels, preds))

        result["details"] = {
            "current_f1":   round(current_f1,  4),
            "current_acc":  round(current_acc, 4),
            "n_samples":    len(valid),
        }

        # Charger le F1 baseline du dernier training
        baseline = _load_baseline(task)
        if baseline:
            baseline_f1 = baseline.get("eval_f1", 0.0)
            f1_drop     = baseline_f1 - current_f1
            result["details"]["baseline_f1"] = round(baseline_f1, 4)
            result["details"]["f1_drop"]     = round(f1_drop, 4)

            if f1_drop > PERF_DRIFT_THRESHOLD:
                result["status"]  = "alert"
                result["message"] = (
                    f"Performance drift détecté : F1 a chuté de {f1_drop:.2%} "
                    f"(baseline={baseline_f1:.4f} → actuel={current_f1:.4f})"
                )
            else:
                result["message"] = f"Performance stable (F1={current_f1:.4f}, Δ={f1_drop:+.4f})"
        else:
            result["message"] = f"F1 courant={current_f1:.4f} (pas de baseline pour comparer)"

    except Exception as e:
        result["status"]  = "error"
        result["reason"]  = str(e)

    return result


# ══════════════════════════════════════════════════════════════════════
# 5. DISTRIBUTION DRIFT — KL divergence sur les prédictions récentes
# ══════════════════════════════════════════════════════════════════════

def detect_distribution_drift(task: str, predictions_df: pd.DataFrame,
                               baseline: dict | None) -> dict:
    """
    Compare la distribution des labels prédits récemment avec la distribution
    d'entraînement (baseline). Utilise la divergence KL.
    Une divergence élevée = les messages ont changé de nature.
    """
    result = {
        "check": "distribution_drift",
        "status": "ok",
        "details": {},
    }

    if predictions_df.empty or len(predictions_df) < MIN_SAMPLES_MONITOR:
        result["status"] = "skipped"
        result["reason"] = f"Pas assez de prédictions ({len(predictions_df)})"
        return result

    # Distribution actuelle (normalisée)
    current_dist = predictions_df["label"].value_counts(normalize=True).to_dict()
    result["details"]["current_distribution"] = {k: round(v, 3) for k, v in current_dist.items()}

    if baseline and "label_distribution" in baseline:
        # Distribution de référence (depuis le dernier training)
        train_dist_raw = baseline["label_distribution"]
        train_total    = sum(train_dist_raw.values())
        train_dist     = {k: v / train_total for k, v in train_dist_raw.items()}
        result["details"]["baseline_distribution"] = {k: round(v, 3) for k, v in train_dist.items()}

        # Aligner les labels (mêmes clés)
        all_labels = sorted(set(current_dist) | set(train_dist))
        eps = 1e-9  # éviter log(0)
        p = np.array([current_dist.get(l, 0) + eps for l in all_labels])
        q = np.array([train_dist.get(l, 0)   + eps for l in all_labels])

        # Normaliser
        p = p / p.sum()
        q = q / q.sum()

        kl = float(kl_divergence(p, q))
        result["details"]["kl_divergence"] = round(kl, 4)
        result["details"]["labels_compared"] = all_labels

        if kl > DIST_DRIFT_THRESHOLD:
            result["status"]  = "alert"
            result["message"] = (
                f"Distribution drift détecté : KL={kl:.4f} "
                f"(seuil={DIST_DRIFT_THRESHOLD}) — les communications ont changé de nature"
            )
        else:
            result["message"] = f"Distribution stable (KL={kl:.4f})"
    else:
        result["status"]  = "skipped"
        result["reason"]  = "Pas de baseline de distribution disponible"

    return result


# ══════════════════════════════════════════════════════════════════════
# 6. CONFIDENCE DRIFT — baisse de la confiance moyenne
# ══════════════════════════════════════════════════════════════════════

def detect_confidence_drift(task: str, predictions_df: pd.DataFrame,
                             baseline: dict | None) -> dict:
    """
    Si la confiance moyenne du modèle sur les messages récents a baissé,
    le modèle commence à hésiter → signe de drift.
    """
    result = {
        "check": "confidence_drift",
        "status": "ok",
        "details": {},
    }

    if predictions_df.empty or "confidence" not in predictions_df.columns:
        result["status"] = "skipped"
        result["reason"] = "Pas de scores de confiance disponibles"
        return result

    valid = predictions_df["confidence"].dropna()
    if len(valid) < MIN_SAMPLES_MONITOR:
        result["status"] = "skipped"
        result["reason"] = f"Pas assez de scores ({len(valid)})"
        return result

    current_conf = float(valid.mean())
    result["details"]["current_avg_confidence"] = round(current_conf, 4)
    result["details"]["n_samples"]              = len(valid)

    # Baseline : on n'a pas de confiance stockée dans le rapport, donc on utilise
    # une heuristique : pour un bon modèle fine-tuné, conf >= 0.80
    EXPECTED_MIN_CONF = 0.70
    if current_conf < EXPECTED_MIN_CONF:
        result["status"]  = "alert"
        result["message"] = (
            f"Confidence drift : confiance moyenne={current_conf:.2%} "
            f"(attendu >={EXPECTED_MIN_CONF:.0%}) — le modèle hésite"
        )
    else:
        result["message"] = f"Confiance stable ({current_conf:.2%})"

    return result


# ══════════════════════════════════════════════════════════════════════
# 7. RAPPORT COMPLET
# ══════════════════════════════════════════════════════════════════════

def run_monitoring_report(task: str, window_days: int = 30) -> dict:
    """
    Lance tous les checks de monitoring pour une tâche.
    Retourne un rapport structuré avec le statut global et les détails.

    Statuts possibles : "healthy" | "warning" | "alert" | "error"
    """
    report = {
        "task":           task,
        "window_days":    window_days,
        "generated_at":   datetime.utcnow().isoformat(),
        "overall_status": "healthy",
        "checks":         [],
        "recommendation": None,
    }

    print(f"\n{'='*55}")
    print(f"[Monitor] Rapport pour task={task}, window={window_days}j")
    print(f"{'='*55}")

    # ── Charger le modèle champion ──
    model_path = _load_champion_path(task)
    report["model_path"] = model_path or "non trouvé"

    if not model_path:
        report["overall_status"] = "warning"
        report["recommendation"] = "Aucun modèle champion trouvé. Lancer un premier fine-tuning."
        return report

    # ── Charger la baseline ──
    baseline = _load_baseline(task)

    # ── Données récentes ──
    corrections_df = _fetch_recent_corrections(task, window_days)
    predictions_df = _fetch_recent_predictions(task, window_days)

    # ── Exécuter les checks ──
    checks = [
        detect_performance_drift(task, corrections_df, model_path),
        detect_distribution_drift(task, predictions_df, baseline),
        detect_confidence_drift(task, predictions_df, baseline),
    ]
    report["checks"] = checks

    # ── Statut global ──
    alert_count   = sum(1 for c in checks if c["status"] == "alert")
    error_count   = sum(1 for c in checks if c["status"] == "error")
    skipped_count = sum(1 for c in checks if c["status"] == "skipped")

    if error_count > 0:
        report["overall_status"] = "error"
    elif alert_count >= 2:
        report["overall_status"] = "alert"
        report["recommendation"] = (
            f"{alert_count} drift(s) détecté(s). "
            "Recommandation : lancer un fine-tuning si ≥20 corrections disponibles."
        )
    elif alert_count == 1:
        report["overall_status"] = "warning"
        report["recommendation"] = "Drift léger détecté. Surveiller l'évolution."
    elif skipped_count == len(checks):
        report["overall_status"] = "insufficient_data"
        report["recommendation"] = "Pas assez de données récentes. Continuer à utiliser le système."
    else:
        report["overall_status"] = "healthy"
        report["recommendation"] = "Modèle en bonne santé. Prochain check recommandé dans 7 jours."

    # ── Sauvegarder le rapport ──
    ts          = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    report_path = MONITOR_DIR / f"monitor-{task}-{ts}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n[Monitor] Statut global : {report['overall_status'].upper()}")
    print(f"[Monitor] Recommandation : {report['recommendation']}")
    print(f"[Monitor] Rapport sauvegardé : {report_path}")

    return report


def run_all_monitoring(window_days: int = 30) -> dict:
    """Lance le monitoring pour toutes les tâches et retourne un résumé global."""
    tasks   = ["sentiment", "emotion"]
    reports = {}
    for task in tasks:
        try:
            reports[task] = run_monitoring_report(task, window_days)
        except Exception as e:
            reports[task] = {
                "task":           task,
                "overall_status": "error",
                "error":          str(e),
                "generated_at":   datetime.utcnow().isoformat(),
            }

    # Statut global : le pire des deux
    status_order = ["error", "alert", "warning", "insufficient_data", "healthy"]
    worst = max(
        (r.get("overall_status", "healthy") for r in reports.values()),
        key=lambda s: status_order.index(s) if s in status_order else 99,
        default="healthy",
    )

    return {
        "global_status": worst,
        "tasks":         reports,
        "generated_at":  datetime.utcnow().isoformat(),
    }


def get_last_monitoring_report(task: str) -> dict | None:
    """Charge le dernier rapport de monitoring pour une tâche."""
    reports = sorted(MONITOR_DIR.glob(f"monitor-{task}-*.json"), reverse=True)
    if not reports:
        return None
    try:
        with open(reports[0]) as f:
            return json.load(f)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightFlow Model Monitoring")
    parser.add_argument("--task", choices=["sentiment", "emotion", "all"], default="all")
    parser.add_argument("--window-days", type=int, default=30,
                        help="Fenêtre de monitoring en jours (défaut: 30)")
    args = parser.parse_args()

    if args.task == "all":
        result = run_all_monitoring(args.window_days)
        print(f"\n{'='*55}")
        print(f"STATUT GLOBAL : {result['global_status'].upper()}")
        print(f"{'='*55}")
    else:
        result = run_monitoring_report(args.task, args.window_days)

    sys.exit(0 if result.get("overall_status") not in ("alert", "error") else 1)
