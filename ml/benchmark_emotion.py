"""
InsightFlow Executive — Emotion Model Benchmark
================================================
Évalue des modèles HuggingFace sur la détection d'émotions business.

Labels cibles (5 classes business) :
  frustration | concern | urgency | neutral | satisfaction

Stratégie : les modèles HuggingFace retournent des émotions brutes
(anger, joy, fear...) → mapping vers nos 5 labels business.

Modèles comparés :
  1. Keyword Baseline     — règles simples (baseline)
  2. j-hartmann           — emotion-english-distilroberta-base (7 classes)
  3. bhadresh-savani      — distilbert-base-uncased-emotion (6 classes)
  4. SamLowe GoEmotions   — roberta-base-go_emotions (28 classes)

Dataset : ml/dataset/insightflow_synthetic_full.csv
          (uniquement les rows avec emotion_label non vide)

Usage :
    python ml/benchmark_emotion.py
    python ml/benchmark_emotion.py --lang en
    python ml/benchmark_emotion.py --lang fr
    python ml/benchmark_emotion.py --samples 300
"""

from __future__ import annotations
import argparse
import csv
import os
import random
import time
import warnings
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import (
    accuracy_score, f1_score,
    classification_report, confusion_matrix,
)
from tabulate import tabulate

warnings.filterwarnings("ignore")

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
CHARTS_DIR  = os.path.join(os.path.dirname(__file__), "charts", "emotion")
os.makedirs(CHARTS_DIR, exist_ok=True)

EMOTION_LABELS = ["frustration", "concern", "urgency", "neutral", "satisfaction"]

COLORS = {
    "Keyword Baseline":          "#4C72B0",
    "j-hartmann (distilRoBERTa)": "#DD8452",
    "bhadresh (DistilBERT)":     "#55A868",
    "SamLowe GoEmotions":        "#C44E52",
}

# ─────────────────────────────────────────────────────────────────
#  MAPPINGS  raw HuggingFace label → business label
# ─────────────────────────────────────────────────────────────────

# j-hartmann/emotion-english-distilroberta-base
#   raw : anger | disgust | fear | joy | neutral | sadness | surprise
HARTMANN_MAP = {
    "anger":    "frustration",
    "disgust":  "frustration",
    "fear":     "concern",
    "sadness":  "concern",
    "joy":      "satisfaction",
    "surprise": "urgency",
    "neutral":  "neutral",
}

# bhadresh-savani/distilbert-base-uncased-emotion
#   raw : sadness | joy | love | anger | fear | surprise
BHADRESH_MAP = {
    "anger":   "frustration",
    "fear":    "concern",
    "sadness": "concern",
    "joy":     "satisfaction",
    "love":    "satisfaction",
    "surprise":"urgency",
    # neutral absent → default
}

# SamLowe/roberta-base-go_emotions  (28 classes)
GOEMOTIONS_MAP = {
    # frustration
    "anger":        "frustration",
    "annoyance":    "frustration",
    "disapproval":  "frustration",
    "disgust":      "frustration",
    "embarrassment":"frustration",
    # concern
    "fear":         "concern",
    "nervousness":  "concern",
    "sadness":      "concern",
    "grief":        "concern",
    "remorse":      "concern",
    "disappointment":"concern",
    # urgency
    "surprise":     "urgency",
    "confusion":    "urgency",
    "realization":  "urgency",
    # satisfaction
    "joy":          "satisfaction",
    "admiration":   "satisfaction",
    "amusement":    "satisfaction",
    "approval":     "satisfaction",
    "caring":       "satisfaction",
    "excitement":   "satisfaction",
    "gratitude":    "satisfaction",
    "love":         "satisfaction",
    "optimism":     "satisfaction",
    "pride":        "satisfaction",
    "relief":       "satisfaction",
    # neutral
    "neutral":      "neutral",
    "curiosity":    "neutral",
    "desire":       "neutral",
}


# ─────────────────────────────────────────────────────────────────
#  DATA
# ─────────────────────────────────────────────────────────────────

@dataclass
class ModelResult:
    name:        str
    accuracy:    float
    f1_macro:    float
    f1_per_class: dict
    speed_ms:    float
    predictions: list
    labels:      list = field(default_factory=list)


def load_dataset(lang: str = "full", n_samples: int = 500) -> tuple[list[str], list[str]]:
    """
    Charge les rows avec emotion_label valide depuis le CSV.
    lang : 'en' | 'fr' | 'full'
    """
    file_map = {
        "en":   "insightflow_synthetic_en.csv",
        "fr":   "insightflow_synthetic_fr.csv",
        "full": "insightflow_synthetic_full.csv",
    }
    path = os.path.join(DATASET_DIR, file_map.get(lang, "insightflow_synthetic_full.csv"))

    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            content = row.get("content", "").strip()
            label   = row.get("emotion_label", "").strip()
            if content and label in EMOTION_LABELS:
                texts.append(content)
                labels.append(label)

    print(f"[Dataset] {len(texts)} rows with valid emotion_label ({lang})")
    print(f"          Distribution: {dict(Counter(labels).most_common())}")

    random.shuffle(list(zip(texts, labels)))
    combined = list(zip(texts, labels))
    random.shuffle(combined)
    combined = combined[:n_samples]
    texts, labels = zip(*combined) if combined else ([], [])
    print(f"          Sample used  : {len(texts)}")
    return list(texts), list(labels)


# ─────────────────────────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────────────────────────

# Keyword baseline
_FRUSTRATION_KW = {
    "frustrated", "annoyed", "angry", "unacceptable", "blocked", "stuck",
    "urgent", "problem", "issue", "error", "fail", "failed", "wrong",
    "disappointed", "delay", "overdue", "frustration", "irritated",
    "bloqué", "bloquée", "problème", "erreur", "frustré", "frustrée",
    "inacceptable", "en retard", "difficile",
}
_CONCERN_KW = {
    "concern", "worried", "risk", "uncertain", "unclear", "not sure",
    "worried", "might", "could", "fear", "afraid", "worried", "doubt",
    "inquiet", "inquiète", "risque", "incertain", "préoccupé", "craindre",
}
_URGENCY_KW = {
    "urgent", "asap", "immediately", "critical", "emergency", "now",
    "deadline", "today", "tonight", "right away", "as soon as possible",
    "d'urgence", "immédiatement", "tout de suite", "maintenant", "critique",
}
_SATISFACTION_KW = {
    "great", "excellent", "success", "happy", "pleased", "congrats",
    "well done", "perfect", "good news", "achieved", "completed", "approved",
    "super", "excellent", "bravo", "félicitations", "réussi", "content",
    "satisfait", "bon travail",
}


def run_keyword_baseline(texts: list[str]) -> tuple[list[str], float]:
    start = time.time()
    preds = []
    for text in texts:
        lower = text.lower()
        scores = {
            "urgency":     sum(1 for w in _URGENCY_KW     if w in lower),
            "frustration": sum(1 for w in _FRUSTRATION_KW if w in lower),
            "concern":     sum(1 for w in _CONCERN_KW     if w in lower),
            "satisfaction":sum(1 for w in _SATISFACTION_KW if w in lower),
        }
        best = max(scores, key=scores.get)
        preds.append(best if scores[best] > 0 else "neutral")
    ms = (time.time() - start) * 1000 / len(texts)
    return preds, ms


def run_hf_emotion(model_id: str, label_map: dict, texts: list[str],
                   default: str = "neutral", batch_size: int = 32) -> tuple[list[str], float]:
    from transformers import pipeline
    print(f"  Loading {model_id}...")
    pipe = pipeline("text-classification", model=model_id,
                    truncation=True, max_length=512, device=-1)
    start = time.time()
    preds = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for out in pipe(batch):
            raw = out["label"].lower()
            preds.append(label_map.get(raw, default))
    ms = (time.time() - start) * 1000 / len(texts)
    return preds, ms


# ─────────────────────────────────────────────────────────────────
#  EVALUATION
# ─────────────────────────────────────────────────────────────────

def evaluate(name: str, preds: list, labels: list, speed_ms: float) -> ModelResult:
    rep = classification_report(
        labels, preds,
        labels=EMOTION_LABELS,
        output_dict=True,
        zero_division=0,
    )
    f1_per = {lbl: round(rep.get(lbl, {}).get("f1-score", 0) * 100, 2)
              for lbl in EMOTION_LABELS}
    return ModelResult(
        name=name,
        accuracy=round(accuracy_score(labels, preds) * 100, 2),
        f1_macro=round(f1_score(labels, preds, average="macro",
                                labels=EMOTION_LABELS, zero_division=0) * 100, 2),
        f1_per_class=f1_per,
        speed_ms=round(speed_ms, 2),
        predictions=preds,
        labels=labels,
    )


# ─────────────────────────────────────────────────────────────────
#  CHARTS
# ─────────────────────────────────────────────────────────────────

def generate_charts(results: list[ModelResult], dataset_labels: list[str], dataset_name: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import seaborn as sns
    except ImportError:
        print("[Charts] matplotlib/seaborn not installed — skipping charts.")
        return

    sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
    names  = [r.name for r in results]
    colors = [COLORS.get(n, "#999999") for n in names]

    # 1. Accuracy + F1-macro
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(names))
    w = 0.35
    b1 = ax.bar(x - w/2, [r.accuracy  for r in results], w, label="Accuracy",
                color=[c + "cc" for c in colors], edgecolor="white")
    b2 = ax.bar(x + w/2, [r.f1_macro for r in results], w, label="F1-macro",
                color=colors, edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 100)
    ax.set_title(f"Emotion Model Comparison — Accuracy & F1-macro\n{dataset_name}",
                 fontsize=14, fontweight="bold")
    ax.legend()
    for bar in list(b1) + list(b2):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "1_model_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close()

    # 2. Per-class F1
    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(len(names))
    n_cls = len(EMOTION_LABELS)
    width = 0.15
    emo_colors = {
        "frustration": "#E74C3C",
        "concern":     "#F39C12",
        "urgency":     "#9B59B6",
        "neutral":     "#95A5A6",
        "satisfaction":"#2ECC71",
    }
    for i, lbl in enumerate(EMOTION_LABELS):
        offset = (i - n_cls / 2 + 0.5) * width
        vals = [r.f1_per_class.get(lbl, 0) for r in results]
        bars = ax.bar(x + offset, vals, width, label=lbl,
                      color=emo_colors[lbl], alpha=0.85, edgecolor="white")
        for bar in bars:
            if bar.get_height() > 2:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                        f"{bar.get_height():.0f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.set_ylabel("F1-score (%)")
    ax.set_ylim(0, 100)
    ax.set_title(f"Per-class F1-score — {dataset_name}", fontsize=14, fontweight="bold")
    ax.legend(title="Emotion", fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "2_per_class_f1.png"), dpi=150, bbox_inches="tight")
    plt.close()

    # 3. Confusion matrices
    n_models = len(results)
    cols = min(2, n_models)
    rows_n = (n_models + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols, figsize=(8 * cols, 6 * rows_n))
    axes = np.array(axes).flatten()
    for i, r in enumerate(results):
        cm = confusion_matrix(r.labels, r.predictions, labels=EMOTION_LABELS)
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=EMOTION_LABELS, yticklabels=EMOTION_LABELS,
                    ax=axes[i], cbar=False)
        axes[i].set_title(f"{r.name}\nF1={r.f1_macro}%", fontsize=11, fontweight="bold")
        axes[i].set_xlabel("Predicted")
        axes[i].set_ylabel("True")
        axes[i].tick_params(axis="x", rotation=30)
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    fig.suptitle(f"Confusion Matrices — {dataset_name}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "3_confusion_matrices.png"), dpi=150, bbox_inches="tight")
    plt.close()

    # 4. Distribution dataset
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    counts = Counter(dataset_labels)
    lbl_ord = EMOTION_LABELS
    vals = [counts.get(l, 0) for l in lbl_ord]
    bar_colors = [emo_colors[l] for l in lbl_ord]
    axes[0].bar(lbl_ord, vals, color=bar_colors, edgecolor="white")
    for i, v in enumerate(vals):
        axes[0].text(i, v + 1, f"{v}\n({v/len(dataset_labels)*100:.1f}%)",
                     ha="center", fontsize=10)
    axes[0].set_title("Dataset Emotion Distribution", fontsize=13, fontweight="bold")
    axes[0].tick_params(axis="x", rotation=20)
    axes[1].pie(vals, labels=lbl_ord, colors=bar_colors, autopct="%1.1f%%",
                startangle=90, wedgeprops={"edgecolor": "white", "linewidth": 2})
    axes[1].set_title("Distribution (Pie)", fontsize=13, fontweight="bold")
    fig.suptitle(f"Dataset: {dataset_name} — {len(dataset_labels)} samples",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "4_distribution.png"), dpi=150, bbox_inches="tight")
    plt.close()

    # 5. Dashboard global
    fig = plt.figure(figsize=(20, 14))
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

    # Top-left : Accuracy + F1
    ax1 = fig.add_subplot(gs[0, 0])
    x = np.arange(len(names))
    ax1.bar(x - w/2, [r.accuracy  for r in results], w, label="Accuracy",  color="#4C72B0", alpha=0.8)
    ax1.bar(x + w/2, [r.f1_macro for r in results], w, label="F1-macro",  color="#DD8452", alpha=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels([n.split(" ")[0] for n in names], rotation=20, ha="right", fontsize=9)
    ax1.set_title("Accuracy & F1-macro", fontweight="bold")
    ax1.set_ylim(0, 100)
    ax1.legend(fontsize=8)

    # Top-center : Speed
    ax2 = fig.add_subplot(gs[0, 1])
    spd_colors = ["#2ECC71" if r.speed_ms < 5 else "#F39C12" if r.speed_ms < 100 else "#E74C3C"
                  for r in results]
    ax2.barh([n.split(" ")[0] for n in names], [r.speed_ms for r in results],
             color=spd_colors, edgecolor="white")
    ax2.set_xlabel("ms/sample")
    ax2.set_title("Inference Speed", fontweight="bold")

    # Top-right : Distribution pie
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.pie(vals, labels=lbl_ord, colors=bar_colors, autopct="%1.0f%%",
            startangle=90, wedgeprops={"edgecolor": "white", "linewidth": 2})
    ax3.set_title("Dataset Distribution", fontweight="bold")

    # Bottom : Confusion matrix du meilleur modèle
    winner = max(results, key=lambda r: r.f1_macro)
    ax4 = fig.add_subplot(gs[1, 0])
    cm = confusion_matrix(winner.labels, winner.predictions, labels=EMOTION_LABELS)
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=EMOTION_LABELS, yticklabels=EMOTION_LABELS,
                ax=ax4, cbar=False)
    ax4.set_title(f"Best: {winner.name.split('(')[0].strip()}\nConfusion Matrix", fontweight="bold")
    ax4.set_xlabel("Predicted")
    ax4.set_ylabel("True")
    ax4.tick_params(axis="x", rotation=30)

    # Bottom-center/right : Per-class F1
    ax5 = fig.add_subplot(gs[1, 1:])
    x = np.arange(len(names))
    for i, lbl in enumerate(EMOTION_LABELS):
        offset = (i - n_cls / 2 + 0.5) * width
        vals_f1 = [r.f1_per_class.get(lbl, 0) for r in results]
        ax5.bar(x + offset, vals_f1, width, label=lbl,
                color=emo_colors[lbl], alpha=0.85)
    ax5.set_xticks(x)
    ax5.set_xticklabels([n.split(" ")[0] for n in names], rotation=15, ha="right", fontsize=9)
    ax5.set_ylabel("F1-score (%)")
    ax5.set_ylim(0, 100)
    ax5.set_title("Per-class F1-score", fontweight="bold")
    ax5.legend(title="Emotion", fontsize=9)

    fig.suptitle(
        f"InsightFlow — Emotion Benchmark Dashboard\n{dataset_name} | {len(dataset_labels)} samples",
        fontsize=15, fontweight="bold",
    )
    plt.savefig(os.path.join(CHARTS_DIR, "0_benchmark_dashboard.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Charts] Saved to: {CHARTS_DIR}/")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def run_emotion_benchmark(lang: str = "full", n_samples: int = 500):
    texts, labels = load_dataset(lang=lang, n_samples=n_samples)
    if not texts:
        print("[Error] No data loaded.")
        return

    dataset_name = {
        "en":   "InsightFlow Synthetic (English)",
        "fr":   "InsightFlow Synthetic (French)",
        "full": "InsightFlow Synthetic (EN + FR)",
    }.get(lang, "InsightFlow Synthetic")

    results: list[ModelResult] = []

    # 1. Keyword Baseline
    print("\n[1/4] Keyword Baseline...")
    preds, ms = run_keyword_baseline(texts)
    results.append(evaluate("Keyword Baseline", preds, labels, ms))

    # 2. j-hartmann
    print("[2/4] j-hartmann/emotion-english-distilroberta-base...")
    preds, ms = run_hf_emotion(
        "j-hartmann/emotion-english-distilroberta-base",
        HARTMANN_MAP, texts,
    )
    results.append(evaluate("j-hartmann (distilRoBERTa)", preds, labels, ms))

    # 3. bhadresh-savani
    print("[3/4] bhadresh-savani/distilbert-base-uncased-emotion...")
    preds, ms = run_hf_emotion(
        "bhadresh-savani/distilbert-base-uncased-emotion",
        BHADRESH_MAP, texts,
    )
    results.append(evaluate("bhadresh (DistilBERT)", preds, labels, ms))

    # 4. SamLowe GoEmotions
    print("[4/4] SamLowe/roberta-base-go_emotions...")
    preds, ms = run_hf_emotion(
        "SamLowe/roberta-base-go_emotions",
        GOEMOTIONS_MAP, texts,
    )
    results.append(evaluate("SamLowe GoEmotions", preds, labels, ms))

    # ── Résultats ─────────────────────────────────────────────────
    print(f"\n{'='*75}")
    print(f"  InsightFlow Executive — Emotion Benchmark Results")
    print(f"  Dataset : {dataset_name} | Samples : {len(texts)}")
    print(f"{'='*75}")

    table = [
        [
            r.name,
            f"{r.accuracy}%",
            f"{r.f1_macro}%",
            f"{r.f1_per_class['frustration']}%",
            f"{r.f1_per_class['concern']}%",
            f"{r.f1_per_class['urgency']}%",
            f"{r.f1_per_class['neutral']}%",
            f"{r.f1_per_class['satisfaction']}%",
            f"{r.speed_ms} ms",
        ]
        for r in results
    ]
    print(tabulate(
        table,
        headers=["Model", "Accuracy", "F1-macro", "Frustration", "Concern",
                 "Urgency", "Neutral", "Satisfaction", "Speed"],
        tablefmt="rounded_outline",
    ))

    winner = max(results, key=lambda r: r.f1_macro)
    print(f"\n  Winner : {winner.name}")
    print(f"  F1-macro : {winner.f1_macro}% | Accuracy : {winner.accuracy}% | Speed : {winner.speed_ms}ms")
    print(f"{'='*75}")
    print(classification_report(winner.labels, winner.predictions,
                                 labels=EMOTION_LABELS, zero_division=0))

    print(f"\n[Charts] Generating charts → ml/charts/emotion/")
    generate_charts(results, labels, dataset_name)

    return results, winner


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang",    default="full", choices=["en", "fr", "full"])
    parser.add_argument("--samples", default=500,    type=int)
    args = parser.parse_args()

    run_emotion_benchmark(lang=args.lang, n_samples=args.samples)
