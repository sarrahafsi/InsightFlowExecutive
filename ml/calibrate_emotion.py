"""
Temperature Scaling Calibration — InsightFlow Emotion Model
============================================================
Guo et al. 2017 : "On Calibration of Modern Neural Networks"

Trouve le paramètre T qui minimise le ECE (Expected Calibration Error)
sur le jeu de validation (20% du dataset).

Usage :
    python ml/calibrate_emotion.py

Output :
    ml/models/insightflow-emotion-v1/temperature.json
    → {"temperature": 1.63, "ece_before": 0.18, "ece_after": 0.04}
"""
from __future__ import annotations

import json
import os
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET     = os.path.join(BASE_DIR, "dataset", "insightflow_synthetic_full.csv")
MODEL_DIR   = os.path.join(BASE_DIR, "models", "insightflow-emotion-v1")
OUTPUT_FILE = os.path.join(MODEL_DIR, "temperature.json")

LABELS = ["frustration", "concern", "urgency", "neutral", "satisfaction"]


def softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """ECE — mesure l'écart entre confiance et précision réelle."""
    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    correct      = (predictions == labels).astype(float)

    ece = 0.0
    for i in range(n_bins):
        low, high = i / n_bins, (i + 1) / n_bins
        mask = (confidences > low) & (confidences <= high)
        if mask.sum() == 0:
            continue
        bin_conf = confidences[mask].mean()
        bin_acc  = correct[mask].mean()
        ece += mask.sum() * abs(bin_conf - bin_acc)

    return ece / len(labels)


def apply_temperature(logits: np.ndarray, T: float) -> np.ndarray:
    return softmax(logits / T)


def main():
    print("=" * 60)
    print("InsightFlow — Emotion Model Calibration")
    print("=" * 60)

    # ── 1. Charger le dataset ──────────────────────────────────
    print("\n[1/5] Chargement du dataset...")
    df = pd.read_csv(DATASET)
    df = df[df["emotion_label"].isin(LABELS)].dropna(subset=["content", "emotion_label"])
    print(f"    {len(df)} exemples valides")
    print(f"    Distribution : {df['emotion_label'].value_counts().to_dict()}")

    # ── 2. Split validation (20%) ──────────────────────────────
    _, val_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df["emotion_label"])
    print(f"\n[2/5] Split validation : {len(val_df)} exemples")

    # ── 3. Obtenir les logits du modèle sur le jeu de validation
    print("\n[3/5] Inférence du modèle (peut prendre quelques minutes)...")
    from transformers import pipeline as hf_pipeline

    pipe = hf_pipeline(
        "text-classification",
        model=MODEL_DIR,
        truncation=True,
        max_length=512,
        return_all_scores=True,   # ← on veut tous les scores pour les logits
    )

    le = LabelEncoder().fit(LABELS)
    all_probs  = []
    all_labels = []

    texts  = val_df["content"].tolist()
    y_true = val_df["emotion_label"].tolist()

    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch   = texts[i:i + batch_size]
        outputs = pipe(batch, truncation=True, max_length=512)
        for out, label in zip(outputs, y_true[i:i + batch_size]):
            # out = [{"label": "frustration", "score": 0.6}, ...]
            score_dict = {item["label"].lower(): item["score"] for item in out}
            probs = np.array([score_dict.get(l, 0.0) for l in LABELS])
            all_probs.append(probs)
            all_labels.append(label)

        if (i // batch_size) % 5 == 0:
            print(f"    {min(i + batch_size, len(texts))}/{len(texts)} exemples traités...")

    probs_array  = np.array(all_probs)
    labels_array = le.transform(all_labels)

    # ── 4. Calculer ECE avant calibration ─────────────────────
    ece_before = expected_calibration_error(probs_array, labels_array)
    print(f"\n[4/5] ECE avant calibration : {ece_before:.4f}")

    # Convertir probs en logits (inverse softmax approximation)
    # log(p) donne des logits proportionnels
    logits = np.log(np.clip(probs_array, 1e-7, 1.0))

    # ── 5. Optimiser T ────────────────────────────────────────
    print("\n[5/5] Optimisation de la température T...")

    def nll_loss(T: float) -> float:
        """Negative Log Likelihood après temperature scaling."""
        calibrated = apply_temperature(logits, T)
        calibrated = np.clip(calibrated, 1e-7, 1.0)
        nll = -np.log(calibrated[np.arange(len(labels_array)), labels_array]).mean()
        return nll

    result = minimize_scalar(nll_loss, bounds=(0.1, 5.0), method="bounded")
    T_opt  = result.x

    calibrated_probs = apply_temperature(logits, T_opt)
    ece_after = expected_calibration_error(calibrated_probs, labels_array)

    print(f"\n{'=' * 40}")
    print(f"  Température optimale T = {T_opt:.4f}")
    print(f"  ECE avant  : {ece_before:.4f}  ({ece_before*100:.1f}% d'erreur de calibration)")
    print(f"  ECE après  : {ece_after:.4f}  ({ece_after*100:.1f}% d'erreur de calibration)")
    print(f"  Amélioration : {((ece_before - ece_after) / ece_before * 100):.1f}%")
    print(f"{'=' * 40}")

    # ── Sauvegarder ───────────────────────────────────────────
    output = {
        "temperature":  round(float(T_opt), 4),
        "ece_before":   round(float(ece_before), 4),
        "ece_after":    round(float(ece_after), 4),
        "improvement":  round((ece_before - ece_after) / ece_before * 100, 1),
        "val_size":     len(val_df),
        "labels":       LABELS,
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Sauvegardé dans : {OUTPUT_FILE}")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
