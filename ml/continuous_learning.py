"""
InsightFlow Executive — MLOps Pipeline (Continuous Learning)
=============================================================
Pipeline complet avec :
  1. Extraction + validation des corrections humaines (PostgreSQL)
  2. Construction du dataset avec Experience Replay
  3. Fine-tuning incrémental (HuggingFace Trainer)
  4. Tracking MLflow — paramètres, métriques, artefacts
  5. Champion/Challenger — le nouveau modèle est déployé UNIQUEMENT
     s'il surpasse le modèle en production sur le même val set
  6. Model Registry MLflow — staging → production
  7. Marquage des corrections utilisées + rapport JSON

Usage :
    python continuous_learning.py --task sentiment --min-samples 20
    python continuous_learning.py --task all --min-samples 20 --epochs 3
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

import mlflow
import mlflow.pytorch
from mlflow.tracking import MlflowClient

# ── Chemins ────────────────────────────────────────────────────────
ML_DIR      = Path(__file__).parent
MODELS_DIR  = ML_DIR / "models"
DATASET_DIR = ML_DIR / "dataset"
REPORTS_DIR = ML_DIR / "training_reports"
MLFLOW_DIR  = ML_DIR / "mlruns"
REPORTS_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

SENTIMENT_MODEL_BASE = str(MODELS_DIR / "insightflow-sentiment-xlm-v1")
EMOTION_MODEL_BASE   = str(MODELS_DIR / "insightflow-emotion-v1")

SENTIMENT_REMOTE = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
EMOTION_REMOTE   = "j-hartmann/emotion-english-distilroberta-base"

# ── MLflow config ───────────────────────────────────────────────────
MLFLOW_TRACKING_URI      = os.getenv("MLFLOW_TRACKING_URI", f"file://{MLFLOW_DIR}")
MLFLOW_EXPERIMENT_PREFIX = "insightflow"

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

# ── Config PostgreSQL ───────────────────────────────────────────────
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/insightflow"
)

# ── Labels valides ──────────────────────────────────────────────────
SENTIMENT_LABELS = {"POSITIVE": 0, "NEUTRAL": 1, "NEGATIVE": 2}
EMOTION_LABELS   = {
    "satisfaction": 0, "neutral": 1,
    "concern": 2, "urgency": 3, "frustration": 4,
}
BUSINESS_LABELS = [
    "Progress", "Neutral Update", "Concern",
    "Risk", "Blocked", "Overload", "Conflict", "Urgent",
]

# Seuil minimum sérieux pour fine-tuner
MIN_SAMPLES_DEFAULT = 20


# ══════════════════════════════════════════════════════════════════════
# 1. EXTRACTION DES CORRECTIONS DEPUIS POSTGRESQL
# ══════════════════════════════════════════════════════════════════════

def fetch_corrections(task: str, label_filter: list[str] | None = None) -> pd.DataFrame:
    """
    Récupère les corrections humaines non encore utilisées.
    label_filter: si fourni, ne garde que les corrections vers ces labels spécifiques
                  (targeted fine-tuning — e.g. ['frustration', 'urgency']).
    """
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    col_map = {
        "sentiment": ("corrected_sentiment", "original_sentiment"),
        "emotion":   ("corrected_emotion",   "original_emotion"),
        "business":  ("corrected_business",  "original_business"),
    }
    corrected_col, original_col = col_map[task]

    if label_filter:
        placeholders = ",".join(["%s"] * len(label_filter))
        cur.execute(f"""
            SELECT id, text_snapshot AS text,
                   {corrected_col} AS label,
                   {original_col}  AS original_label
            FROM human_corrections
            WHERE used_in_training = FALSE
              AND {corrected_col} IS NOT NULL
              AND ({corrected_col} IN ({placeholders}) OR {original_col} IN ({placeholders}))
              AND text_snapshot IS NOT NULL
              AND LENGTH(text_snapshot) > 20
            ORDER BY corrected_at ASC
        """, label_filter + label_filter)
        print(f"[MLOps] Targeted fetch — labels: {label_filter}")
    else:
        cur.execute(f"""
            SELECT id, text_snapshot AS text,
                   {corrected_col} AS label,
                   {original_col}  AS original_label
            FROM human_corrections
            WHERE used_in_training = FALSE
              AND {corrected_col} IS NOT NULL
              AND text_snapshot IS NOT NULL
              AND LENGTH(text_snapshot) > 20
            ORDER BY corrected_at ASC
        """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    df = pd.DataFrame(rows)
    print(f"[MLOps] {len(df)} corrections trouvées (task={task}, filter={label_filter})")
    return df


def mark_corrections_used(correction_ids: list, run_id: str):
    """Marque les corrections comme utilisées dans un run."""
    if not correction_ids:
        return
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        UPDATE human_corrections
        SET used_in_training = TRUE, training_run_id = %s
        WHERE id = ANY(%s)
    """, (run_id, correction_ids))
    conn.commit()
    cur.close()
    conn.close()
    print(f"[MLOps] {len(correction_ids)} corrections marquées used_in_training=TRUE")


def count_pending_corrections() -> dict:
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE corrected_sentiment IS NOT NULL AND NOT used_in_training) AS sentiment,
            COUNT(*) FILTER (WHERE corrected_emotion   IS NOT NULL AND NOT used_in_training) AS emotion,
            COUNT(*) FILTER (WHERE corrected_business  IS NOT NULL AND NOT used_in_training) AS business,
            COUNT(*) FILTER (WHERE NOT used_in_training)                                    AS total,
            MAX(corrected_at) AS last_correction
        FROM human_corrections
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


# ══════════════════════════════════════════════════════════════════════
# 2. CONSTRUCTION DU DATASET (Experience Replay)
# ══════════════════════════════════════════════════════════════════════

def build_training_dataset(corrections_df: pd.DataFrame, task: str,
                            replay_ratio: float = 0.3) -> pd.DataFrame:
    """
    Stratégie Experience Replay pour éviter le catastrophic forgetting.
    Mélange nouvelles corrections + échantillon de l'ancien dataset.
    """
    task_label_map = {
        "sentiment": SENTIMENT_LABELS,
        "emotion":   EMOTION_LABELS,
        "business":  {l: i for i, l in enumerate(BUSINESS_LABELS)},
    }
    valid_labels = task_label_map[task]

    corrections_df = corrections_df[corrections_df["label"].isin(valid_labels)].copy()
    corrections_df["label_id"] = corrections_df["label"].map(valid_labels)
    corrections_df["source"]   = "human_correction"

    new_df = corrections_df[["text", "label", "label_id", "source"]].copy()
    print(f"[MLOps] {len(new_df)} corrections valides pour {task}")

    replay_df = _load_replay_data(task, valid_labels, int(len(new_df) * replay_ratio))
    if replay_df is not None and len(replay_df) > 0:
        combined = pd.concat([new_df, replay_df], ignore_index=True)
        print(f"[MLOps] Dataset : {len(new_df)} corrections + {len(replay_df)} replay = {len(combined)} total")
    else:
        combined = new_df

    return combined.sample(frac=1, random_state=42).reset_index(drop=True)


def _load_replay_data(task: str, valid_labels: dict, n_samples: int) -> pd.DataFrame | None:
    candidates = {
        "sentiment": [DATASET_DIR / "clean_sentiment_train.csv",
                      DATASET_DIR / "insightflow_synthetic_full.csv"],
        "emotion":   [DATASET_DIR / "clean_emotion_train.csv",
                      DATASET_DIR / "insightflow_synthetic_full.csv"],
    }
    label_cols = {"sentiment": "sentiment_label", "emotion": "emotion_label"}

    for path in candidates.get(task, []):
        if path.exists():
            df = pd.read_csv(path)
            label_col = label_cols[task]
            if "text" in df.columns and label_col in df.columns:
                df = df[df[label_col].isin(valid_labels)].copy()
                df = df.rename(columns={label_col: "label"})
                df["label_id"] = df["label"].map(valid_labels)
                df["source"]   = "original_dataset"
                df = df[["text", "label", "label_id", "source"]].dropna()
                sampled = df.groupby("label", group_keys=False).apply(
                    lambda x: x.sample(
                        min(len(x), max(1, n_samples // df["label"].nunique())),
                        random_state=42,
                    )
                )
                print(f"[MLOps] Experience Replay : {len(sampled)} lignes depuis {path.name}")
                return sampled
    return None


# ══════════════════════════════════════════════════════════════════════
# 3. FINE-TUNING + MLFLOW TRACKING
# ══════════════════════════════════════════════════════════════════════

def finetune_model(dataset: pd.DataFrame, task: str,
                   run_id: str, epochs: int = 3) -> dict:
    """
    Fine-tuning avec tracking MLflow complet.
    Retourne les métriques d'évaluation du nouveau modèle (challenger).
    """
    from transformers import (
        AutoTokenizer, AutoModelForSequenceClassification,
        TrainingArguments, Trainer, EarlyStoppingCallback,
    )
    from torch.utils.data import Dataset as TorchDataset
    import torch
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score, accuracy_score

    # ── Config selon la tâche ──
    if task == "sentiment":
        model_path = SENTIMENT_MODEL_BASE if Path(SENTIMENT_MODEL_BASE).exists() else SENTIMENT_REMOTE
        num_labels = len(SENTIMENT_LABELS)
        id2label   = {v: k for k, v in SENTIMENT_LABELS.items()}
        label2id   = SENTIMENT_LABELS
    elif task == "emotion":
        model_path = EMOTION_MODEL_BASE if Path(EMOTION_MODEL_BASE).exists() else EMOTION_REMOTE
        num_labels = len(EMOTION_LABELS)
        id2label   = {v: k for k, v in EMOTION_LABELS.items()}
        label2id   = EMOTION_LABELS
    else:
        raise ValueError(f"Task inconnue: {task}")

    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if len(dataset) < 4:
        raise ValueError(f"Dataset trop petit ({len(dataset)} lignes, minimum 4)")

    train_df, val_df = train_test_split(
        dataset, test_size=0.2, random_state=42,
        stratify=dataset["label_id"] if dataset["label_id"].nunique() > 1 else None,
    )
    print(f"[MLOps] Split → Train: {len(train_df)}, Val: {len(val_df)}")

    class CorrectionDataset(TorchDataset):
        def __init__(self, df):
            self.encodings = tokenizer(
                list(df["text"]), truncation=True, padding=True, max_length=256
            )
            self.labels = list(df["label_id"].astype(int))
        def __len__(self): return len(self.labels)
        def __getitem__(self, idx):
            item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
            item["labels"] = torch.tensor(self.labels[idx])
            return item

    train_ds = CorrectionDataset(train_df)
    val_ds   = CorrectionDataset(val_df)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_path, num_labels=num_labels,
        id2label=id2label, label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    out_dir  = MODELS_DIR / f"insightflow-{task}-{run_id}"
    use_fp16 = torch.cuda.is_available()

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        learning_rate=1e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        fp16=use_fp16,
        logging_steps=5,
        report_to="none",
    )

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=1)
        return {
            "accuracy": float(accuracy_score(labels, preds)),
            "f1":       float(f1_score(labels, preds, average="macro", zero_division=0)),
        }

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    print(f"[MLOps] Fine-tuning démarré ({task}, {epochs} epochs)...")
    train_result = trainer.train()
    eval_result  = trainer.evaluate()

    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    metrics = {
        "task":              task,
        "run_id":            run_id,
        "model_path":        str(out_dir),
        "train_samples":     len(train_df),
        "val_samples":       len(val_df),
        "train_loss":        round(train_result.training_loss, 4),
        "eval_accuracy":     round(eval_result.get("eval_accuracy", 0), 4),
        "eval_f1":           round(eval_result.get("eval_f1", 0), 4),
        "trained_at":        datetime.utcnow().isoformat(),
        "base_model":        model_path,
        "label_distribution": dataset["label"].value_counts().to_dict(),
    }
    return metrics, val_df, tokenizer, model


# ══════════════════════════════════════════════════════════════════════
# 4. CHAMPION / CHALLENGER
# ══════════════════════════════════════════════════════════════════════

def evaluate_champion(task: str, val_df: pd.DataFrame,
                       tokenizer, label_map: dict) -> float:
    """
    Évalue le modèle actuellement en production (champion) sur le même val set.
    Retourne son F1. Si aucun modèle en production → retourne 0.0.
    Utilise l'alias "champion" (MLflow 3.x — les stages sont supprimés).
    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from sklearn.metrics import f1_score

    client = MlflowClient()
    model_name = f"insightflow-{task}"

    try:
        # MLflow 3.x : on utilise les aliases à la place des stages
        prod_version = client.get_model_version_by_alias(model_name, "champion")
        prod_path    = prod_version.source.replace("file://", "")
        print(f"[MLOps] Champion : {model_name} v{prod_version.version} ({prod_path})")

        champ_tokenizer = AutoTokenizer.from_pretrained(prod_path)
        champ_model     = AutoModelForSequenceClassification.from_pretrained(prod_path)
        champ_model.eval()

        texts  = list(val_df["text"])
        labels = list(val_df["label_id"].astype(int))

        encodings = champ_tokenizer(texts, truncation=True, padding=True,
                                     max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = champ_model(**encodings).logits
        preds = torch.argmax(logits, dim=1).numpy()

        f1 = float(f1_score(labels, preds, average="macro", zero_division=0))
        print(f"[MLOps] Champion F1 sur val set : {f1:.4f}")
        return f1

    except Exception as e:
        # Alias "champion" inexistant = premier run, le challenger devient champion par défaut
        print(f"[MLOps] Aucun champion existant ({e}) → challenger déployé par défaut")
        return 0.0


# ══════════════════════════════════════════════════════════════════════
# 5. MLFLOW TRACKING + MODEL REGISTRY
# ══════════════════════════════════════════════════════════════════════

def track_and_register(metrics: dict, task: str, run_id: str,
                        epochs: int, champion_f1: float,
                        challenger_f1: float, out_dir: Path,
                        promoted: bool) -> str:
    """
    Logue le run dans MLflow et enregistre le modèle dans le registry.
    Retourne le mlflow_run_id.
    """
    experiment_name = f"{MLFLOW_EXPERIMENT_PREFIX}-{task}"
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_id) as run:
        # ── Paramètres ──
        mlflow.log_params({
            "task":          task,
            "epochs":        epochs,
            "train_samples": metrics["train_samples"],
            "val_samples":   metrics["val_samples"],
            "base_model":    metrics["base_model"],
            "replay_ratio":  0.3,
            "min_samples":   MIN_SAMPLES_DEFAULT,
        })

        # ── Métriques ──
        mlflow.log_metrics({
            "train_loss":    metrics["train_loss"],
            "eval_accuracy": metrics["eval_accuracy"],
            "eval_f1":       challenger_f1,
            "champion_f1":   champion_f1,
            "f1_delta":      round(challenger_f1 - champion_f1, 4),
        })

        # ── Tags ──
        mlflow.set_tags({
            "promoted_to_production": str(promoted),
            "run_id_internal":        run_id,
            "trained_at":             metrics["trained_at"],
        })

        # ── Artefact — rapport JSON ──
        report_path = REPORTS_DIR / f"{run_id}.json"
        mlflow.log_artifact(str(report_path))

        # ── Artefact — modèle (dossier complet) ──
        mlflow.log_artifacts(str(out_dir), artifact_path="model")

        client = MlflowClient()
        model_name = f"insightflow-{task}"

        # Créer le registered model s'il n'existe pas
        try:
            client.create_registered_model(model_name)
        except Exception:
            pass  # déjà existant

        # Créer la version dans le registry
        mv = client.create_model_version(
            name=model_name,
            source=str(out_dir),
            run_id=run.info.run_id,
            description=f"F1={challenger_f1:.4f} | Champion F1={champion_f1:.4f} | {metrics['trained_at']}",
        )

        # MLflow 3.x : on utilise les aliases à la place des stages
        if promoted:
            # Supprimer l'alias "champion" existant avant d'en créer un nouveau
            try:
                client.delete_registered_model_alias(model_name, "champion")
            except Exception:
                pass  # pas encore d'alias "champion"

            # Le nouveau challenger devient champion
            client.set_registered_model_alias(model_name, "champion", mv.version)
            # Garder aussi l'alias "latest" pour faciliter le chargement
            try:
                client.delete_registered_model_alias(model_name, "latest")
            except Exception:
                pass
            client.set_registered_model_alias(model_name, "latest", mv.version)

            print(f"[MLOps] Alias 'champion' → {model_name} v{mv.version}")
        else:
            # Challenger moins bon : alias "challenger" pour référence
            try:
                client.delete_registered_model_alias(model_name, "challenger")
            except Exception:
                pass
            client.set_registered_model_alias(model_name, "challenger", mv.version)
            print(f"[MLOps] Alias 'challenger' → {model_name} v{mv.version} (inférieur au champion)")

        return run.info.run_id


# ══════════════════════════════════════════════════════════════════════
# 6. PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def run_continuous_learning(task: str, min_samples: int, epochs: int,
                            label_filter: list[str] | None = None) -> dict:
    """
    Orchestration complète du pipeline MLOps.

    Étapes :
      1. Extraction des corrections PostgreSQL
      2. Construction dataset (Experience Replay)
      3. Fine-tuning + métriques challenger
      4. Évaluation champion (modèle en production)
      5. Champion/Challenger — déploiement si challenger > champion
      6. MLflow tracking + Model Registry
      7. Marquage corrections + rapport JSON
    """
    run_id = f"cl-{task}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    print(f"\n{'='*60}")
    print(f"[MLOps] Run ID : {run_id}")
    print(f"[MLOps] Tâche  : {task}")
    print(f"[MLOps] MLflow : {MLFLOW_TRACKING_URI}")
    print(f"{'='*60}\n")

    if label_filter:
        print(f"[MLOps] Targeted mode — label_filter: {label_filter}")

    # ── 1. Vérifier les corrections ──
    corrections_df = fetch_corrections(task, label_filter=label_filter)
    if len(corrections_df) < min_samples:
        msg = f"Pas assez de corrections ({len(corrections_df)}/{min_samples} requis)"
        print(f"[MLOps] SKIP — {msg}")
        return {"status": "skipped", "reason": msg, "task": task,
                "corrections_available": len(corrections_df)}

    # ── 2. Dataset ──
    dataset = build_training_dataset(corrections_df, task)
    if len(dataset) < 4:
        return {"status": "skipped", "reason": "Dataset trop petit après filtrage", "task": task}

    # ── 3. Fine-tuning (challenger) ──
    correction_ids = corrections_df["id"].tolist()
    metrics, val_df, tokenizer, challenger_model = finetune_model(
        dataset, task, run_id, epochs=epochs
    )
    challenger_f1 = metrics["eval_f1"]
    out_dir = Path(metrics["model_path"])

    # ── 4. Évaluer le champion (modèle en production) ──
    label_map = SENTIMENT_LABELS if task == "sentiment" else EMOTION_LABELS
    champion_f1 = evaluate_champion(task, val_df, tokenizer, label_map)

    # ── 5. Décision Champion/Challenger ──
    # Le challenger est promu si son F1 >= champion F1
    # (>= car s'il n'y a pas de champion, champion_f1=0.0 donc toujours promu)
    promoted = challenger_f1 >= champion_f1
    decision = "PROMU en Production" if promoted else f"REJETÉ (challenger={challenger_f1:.4f} < champion={champion_f1:.4f})"
    print(f"\n[MLOps] Champion/Challenger : {decision}")

    # ── Mettre à jour le symlink "latest" si promu ──
    if promoted:
        latest_link = MODELS_DIR / f"insightflow-{task}-latest"
        if latest_link.exists() or latest_link.is_symlink():
            try: latest_link.unlink()
            except Exception: pass
        try:
            latest_link.symlink_to(out_dir.name)
        except Exception as e:
            print(f"[MLOps] Symlink Windows ignoré : {e}")

    metrics["champion_f1"]  = champion_f1
    metrics["challenger_f1"] = challenger_f1
    metrics["promoted"]     = promoted
    metrics["decision"]     = decision
    metrics["status"]       = "success"
    metrics["mlflow_uri"]   = MLFLOW_TRACKING_URI

    # ── 6. Rapport JSON ──
    report_path = REPORTS_DIR / f"{run_id}.json"
    with open(report_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # ── 7. MLflow tracking + registry ──
    mlflow_run_id = track_and_register(
        metrics, task, run_id, epochs,
        champion_f1, challenger_f1, out_dir, promoted
    )
    metrics["mlflow_run_id"] = mlflow_run_id

    # ── 8. Marquer corrections utilisées (seulement si promu) ──
    if promoted:
        mark_corrections_used(correction_ids, run_id)
    else:
        print(f"[MLOps] Corrections NON marquées (modèle rejeté) — disponibles au prochain run")

    print(f"\n[MLOps] Rapport : {report_path}")
    print(f"[MLOps] MLflow  : mlflow ui --backend-store-uri {MLFLOW_TRACKING_URI}")
    return metrics


def get_last_training_report() -> dict | None:
    reports = sorted(REPORTS_DIR.glob("cl-*.json"), reverse=True)
    if not reports:
        return None
    with open(reports[0]) as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════
# 7. CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightFlow MLOps Pipeline")
    parser.add_argument("--task", choices=["sentiment", "emotion", "business", "all"],
                        default="sentiment")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES_DEFAULT,
                        help=f"Nombre minimum de corrections (défaut: {MIN_SAMPLES_DEFAULT})")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--label-filter", type=str, default=None,
                        help="Comma-separated labels for targeted fine-tuning (e.g. 'frustration,urgency')")
    args = parser.parse_args()

    label_filter = [l.strip() for l in args.label_filter.split(",")] if args.label_filter else None
    tasks = ["sentiment", "emotion"] if args.task == "all" else [args.task]
    results = []

    for t in tasks:
        result = run_continuous_learning(t, args.min_samples, args.epochs, label_filter=label_filter)
        results.append(result)
        status = result.get("status")
        if status == "success":
            print(f"\n[MLOps] {t} → F1={result.get('eval_f1')} | "
                  f"Champion={result.get('champion_f1')} | "
                  f"{'PROMU' if result.get('promoted') else 'STAGING'}")
        else:
            print(f"\n[MLOps] {t} → {status} : {result.get('reason', '')}")

    print(f"\n{'='*60}")
    print(f"[MLOps] Pipeline terminé.")
    print(f"[MLOps] Voir les expériences : mlflow ui --backend-store-uri file://{MLFLOW_DIR}")
    sys.exit(0)
