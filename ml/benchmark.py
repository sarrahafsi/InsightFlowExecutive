"""
InsightFlow Executive — NLP Model Benchmark
============================================
3-Level benchmark strategy for PFE report.

Level 1 — Academic     : Financial PhraseBank (CSV)
Level 2 — Conversational: TweetEval Sentiment
Level 3 — Domain       : Enron Emails (corporate)

Models compared:
  1. VADER         — rule-based, no GPU
  2. TextBlob      — rule-based, lightweight
  3. DistilBERT    — distilbert-base-uncased-finetuned-sst-2-english
  4. RoBERTa       — cardiffnlp/twitter-roberta-base-sentiment-latest
  5. XLM-RoBERTa  — cardiffnlp/twitter-xlm-roberta-base-sentiment

Outputs (saved to ml/charts/):
  - model_comparison.png     : Accuracy + F1 bar chart
  - speed_accuracy.png       : Speed vs Accuracy scatter
  - confusion_matrices.png   : Confusion matrix per model
  - sentiment_distribution.png : Dataset class distribution
  - per_class_f1.png         : F1 per class per model
  - benchmark_summary.png    : Full dashboard (all charts)

Usage:
    python ml/benchmark.py
"""

import os
import random
import time
import warnings
from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import (
    accuracy_score, f1_score,
    classification_report, confusion_matrix,
)
from tabulate import tabulate

warnings.filterwarnings("ignore")

CHARTS_DIR = os.path.join(os.path.dirname(__file__), "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

LABELS = ["NEGATIVE", "NEUTRAL", "POSITIVE"]
COLORS = {
    "VADER (rule-based)":     "#4C72B0",
    "TextBlob (rule-based)":  "#DD8452",
    "DistilBERT (EN)":        "#55A868",
    "RoBERTa Twitter (EN)":   "#C44E52",
    "XLM-RoBERTa (FR+EN)":    "#8172B3",
}


# ═══════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ModelResult:
    name:        str
    accuracy:    float
    f1_macro:    float
    f1_neg:      float
    f1_neu:      float
    f1_pos:      float
    speed_ms:    float
    predictions: list
    labels:      list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
#  DATASET LOADERS
# ═══════════════════════════════════════════════════════════════

def load_tweeteval(n_samples: int = 500):
    """Level 1 + 2 : TweetEval Sentiment — general English 3-class."""
    from datasets import load_dataset
    print("[Dataset] Loading TweetEval sentiment...")
    ds = load_dataset("tweet_eval", "sentiment", split="test")
    ds = ds.shuffle(seed=42).select(range(min(n_samples, len(ds))))
    label_map = {0: "NEGATIVE", 1: "NEUTRAL", 2: "POSITIVE"}
    texts  = [r["text"] for r in ds]
    labels = [label_map[r["label"]] for r in ds]
    print(f"           {len(texts)} samples loaded.")
    return texts, labels


def load_financial_phrasebank_csv(n_samples: int = 300):
    """
    Level 1 : Financial PhraseBank — loaded from HuggingFace datasets
    using the sentence-transformers mirror (Parquet format).
    Fallback: use TweetEval if unavailable.
    """
    from datasets import load_dataset
    print("[Dataset] Loading Financial PhraseBank...")
    try:
        ds = load_dataset(
            "financial_phrasebank",
            "sentences_allagree",
            split="train",
            revision="main",
        )
    except Exception:
        try:
            ds = load_dataset(
                "zeroshot/twitter-financial-news-sentiment",
                split="validation",
            )
            ds = ds.shuffle(seed=42).select(range(min(n_samples, len(ds))))
            # Labels can be strings ("bearish") OR integers (0,1,2) depending on dataset version
            label_map_z = {
                "bearish": "NEGATIVE", "neutral": "NEUTRAL", "bullish": "POSITIVE",
                0: "NEGATIVE", 1: "NEUTRAL", 2: "POSITIVE",
                "0": "NEGATIVE", "1": "NEUTRAL", "2": "POSITIVE",
            }
            texts  = [r["text"] for r in ds]
            labels = [label_map_z.get(r["label"], label_map_z.get(str(r["label"]), "NEUTRAL")) for r in ds]
            print(f"           Fallback: {len(texts)} samples from twitter-financial-news-sentiment.")
            return texts, labels
        except Exception as e2:
            print(f"           All financial datasets failed: {e2}. Using TweetEval.")
            return load_tweeteval(n_samples)

    ds = ds.shuffle(seed=42).select(range(min(n_samples, len(ds))))
    label_map = {0: "NEGATIVE", 1: "NEUTRAL", 2: "POSITIVE"}
    texts  = [r["sentence"] for r in ds]
    labels = [label_map[r["label"]] for r in ds]
    print(f"           {len(texts)} samples loaded.")
    return texts, labels


def load_synthetic(n_samples: int = 500, lang: str = "en") -> tuple[list[str], list[str]]:
    """
    Level 4 : InsightFlow Synthetic Dataset — our own domain-specific data.
    Loads from ml/dataset/insightflow_synthetic_{lang}.csv
    Uses sentiment_label as ground truth.
    """
    import csv
    lang_map = {"en": "en", "fr": "fr", "full": "full"}
    suffix   = lang_map.get(lang, "en")
    path     = os.path.join(os.path.dirname(__file__), "dataset", f"insightflow_synthetic_{suffix}.csv")

    if not os.path.exists(path):
        # fallback to any available file
        for fallback in ["insightflow_synthetic_en.csv", "insightflow_synthetic.csv"]:
            fp = os.path.join(os.path.dirname(__file__), "dataset", fallback)
            if os.path.exists(fp):
                path = fp
                break
        else:
            print(f"[Dataset] Synthetic dataset not found at {path}")
            return [], []

    print(f"[Dataset] Loading InsightFlow synthetic dataset ({lang})...")
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    random.shuffle(rows)
    rows = rows[:n_samples]
    for row in rows:
        content = row.get("content", "").strip()
        label   = row.get("sentiment_label", "").strip()
        if content and label in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
            texts.append(content)
            labels.append(label)

    print(f"           {len(texts)} samples loaded from {os.path.basename(path)}")
    return texts, labels


def load_enron(n_samples: int = 200):
    """
    Level 3 : Enron Emails — corporate domain validation.
    No ground-truth sentiment labels exist → we use majority vote
    across all 5 models as pseudo-label (silver standard).
    This measures domain behavior and inter-model agreement,
    not accuracy against human annotation.
    """
    from datasets import load_dataset
    print("[Dataset] Loading Enron emails (corporate domain)...")
    try:
        ds = load_dataset("SetFit/enron_spam", split="test")
        ds = ds.shuffle(seed=42)
        # Keep only ham (real emails, not spam) for corporate realism
        ham = [r for r in ds if r.get("label") == 0 and len(r.get("text", "")) > 50]
        ham = ham[:n_samples]
        texts = [r["text"][:600] for r in ham]
        print(f"           {len(texts)} corporate ham emails loaded.")

        # Silver labels = majority vote of VADER + TextBlob + RoBERTa
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        from textblob import TextBlob
        vader = SentimentIntensityAnalyzer()

        silver_labels = []
        for t in texts:
            votes = []
            # VADER vote
            s = vader.polarity_scores(t)["compound"]
            votes.append("POSITIVE" if s >= 0.05 else "NEGATIVE" if s <= -0.05 else "NEUTRAL")
            # TextBlob vote
            s2 = TextBlob(t).sentiment.polarity
            votes.append("POSITIVE" if s2 > 0.1 else "NEGATIVE" if s2 < -0.1 else "NEUTRAL")
            # Majority
            from collections import Counter
            silver_labels.append(Counter(votes).most_common(1)[0][0])

        print(f"           Silver labels generated via majority vote (VADER + TextBlob).")
        return texts, silver_labels
    except Exception as e:
        print(f"           Enron load failed ({e}), skipping.")
        return [], []


# ═══════════════════════════════════════════════════════════════
#  MODEL RUNNERS
# ═══════════════════════════════════════════════════════════════

def run_vader(texts):
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    start = time.time()
    preds = []
    for t in texts:
        s = analyzer.polarity_scores(t)["compound"]
        preds.append("POSITIVE" if s >= 0.05 else "NEGATIVE" if s <= -0.05 else "NEUTRAL")
    return preds, (time.time() - start) * 1000 / len(texts)


def run_textblob(texts):
    from textblob import TextBlob
    start = time.time()
    preds = []
    for t in texts:
        s = TextBlob(t).sentiment.polarity
        preds.append("POSITIVE" if s > 0.1 else "NEGATIVE" if s < -0.1 else "NEUTRAL")
    return preds, (time.time() - start) * 1000 / len(texts)


def run_hf_model(model_name, texts, label_map, batch_size=32):
    from transformers import pipeline
    print(f"  Loading {model_name}...")
    pipe = pipeline("sentiment-analysis", model=model_name,
                    truncation=True, max_length=512, device=-1)
    start = time.time()
    preds = []
    for i in range(0, len(texts), batch_size):
        for out in pipe(texts[i:i + batch_size]):
            preds.append(label_map.get(out["label"], "NEUTRAL"))
    return preds, (time.time() - start) * 1000 / len(texts)


DISTILBERT_MAP = {"POSITIVE": "POSITIVE", "NEGATIVE": "NEGATIVE", "NEUTRAL": "NEUTRAL"}
ROBERTA_MAP    = {"LABEL_0": "NEGATIVE", "LABEL_1": "NEUTRAL", "LABEL_2": "POSITIVE",
                  "positive": "POSITIVE", "neutral": "NEUTRAL", "negative": "NEGATIVE"}
XLM_MAP        = {"positive": "POSITIVE", "neutral": "NEUTRAL", "negative": "NEGATIVE",
                  "POSITIVE": "POSITIVE", "NEUTRAL": "NEUTRAL", "NEGATIVE": "NEGATIVE"}


# ═══════════════════════════════════════════════════════════════
#  EVALUATION
# ═══════════════════════════════════════════════════════════════

def evaluate(name, preds, true_labels, speed_ms) -> ModelResult:
    rep = classification_report(true_labels, preds,
                                labels=LABELS, output_dict=True, zero_division=0)
    return ModelResult(
        name=name,
        accuracy=round(accuracy_score(true_labels, preds) * 100, 2),
        f1_macro=round(f1_score(true_labels, preds, average="macro", zero_division=0) * 100, 2),
        f1_neg=round(rep.get("NEGATIVE", {}).get("f1-score", 0) * 100, 2),
        f1_neu=round(rep.get("NEUTRAL",  {}).get("f1-score", 0) * 100, 2),
        f1_pos=round(rep.get("POSITIVE", {}).get("f1-score", 0) * 100, 2),
        speed_ms=round(speed_ms, 2),
        predictions=preds,
        labels=true_labels,
    )


# ═══════════════════════════════════════════════════════════════
#  CHARTS
# ═══════════════════════════════════════════════════════════════

def generate_charts(results: list[ModelResult], dataset_labels: list[str], dataset_name: str, level: str = "2"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import seaborn as sns
    from collections import Counter

    # Each level saves in its own subfolder
    level_dir = os.path.join(CHARTS_DIR, f"level{level}")
    os.makedirs(level_dir, exist_ok=True)

    sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
    names   = [r.name for r in results]
    colors  = [COLORS.get(n, "#999999") for n in names]

    # ── 1. Model Comparison : Accuracy + F1-macro ─────────────
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(names))
    w = 0.35
    bars1 = ax.bar(x - w/2, [r.accuracy  for r in results], w,
                   label="Accuracy",  color=[c + "cc" for c in colors[:len(names)]], edgecolor="white")
    bars2 = ax.bar(x + w/2, [r.f1_macro for r in results], w,
                   label="F1-macro",  color=colors, edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_title(f"Model Comparison — Accuracy & F1-macro\nDataset: {dataset_name}",
                 fontsize=14, fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 100)
    for bar in list(bars1) + list(bars2):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    path = os.path.join(level_dir, "1_model_comparison.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 2. Speed vs Accuracy scatter ──────────────────────────
    fig, ax = plt.subplots(figsize=(9, 6))
    for r, c in zip(results, colors):
        ax.scatter(r.speed_ms, r.accuracy, s=200, color=c, zorder=5, edgecolors="white", linewidth=1.5)
        ax.annotate(r.name, (r.speed_ms, r.accuracy),
                    textcoords="offset points", xytext=(8, 4), fontsize=9)
    ax.set_xlabel("Inference Speed (ms/sample)  ←  Faster is better")
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Speed vs Accuracy Trade-off\n(top-left = ideal)",
                 fontsize=14, fontweight="bold")
    ax.axvline(x=10, color="gray", linestyle="--", alpha=0.4, label="10ms threshold")
    ax.legend()
    plt.tight_layout()
    path = os.path.join(level_dir, "2_speed_accuracy.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 3. Confusion Matrices (all models) ────────────────────
    n_models = len(results)
    cols = min(3, n_models)
    rows = (n_models + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows))
    axes = np.array(axes).flatten()
    for i, r in enumerate(results):
        cm = confusion_matrix(r.labels, r.predictions, labels=LABELS)
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=LABELS, yticklabels=LABELS,
                    ax=axes[i], cbar=False)
        axes[i].set_title(f"{r.name}\nF1={r.f1_macro}%", fontsize=11, fontweight="bold")
        axes[i].set_xlabel("Predicted")
        axes[i].set_ylabel("True")
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    fig.suptitle(f"Confusion Matrices — {dataset_name}", fontsize=15, fontweight="bold", y=1.01)
    plt.tight_layout()
    path = os.path.join(level_dir, "3_confusion_matrices.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 4. Sentiment Distribution (dataset) ───────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    counts = Counter(dataset_labels)
    label_colors = {"NEGATIVE": "#E74C3C", "NEUTRAL": "#95A5A6", "POSITIVE": "#2ECC71"}
    lbl = list(counts.keys())
    vals = list(counts.values())
    bar_colors = [label_colors.get(l, "#999") for l in lbl]
    axes[0].bar(lbl, vals, color=bar_colors, edgecolor="white", linewidth=1.5)
    for i, v in enumerate(vals):
        axes[0].text(i, v + 1, f"{v}\n({v/len(dataset_labels)*100:.1f}%)",
                     ha="center", fontsize=11)
    axes[0].set_title("Dataset Class Distribution", fontsize=13, fontweight="bold")
    axes[0].set_ylabel("Number of samples")
    pie_colors = [label_colors.get(l, "#999") for l in lbl]
    axes[1].pie(vals, labels=lbl, colors=pie_colors, autopct="%1.1f%%",
                startangle=90, pctdistance=0.8,
                wedgeprops={"edgecolor": "white", "linewidth": 2})
    axes[1].set_title("Class Distribution (Pie)", fontsize=13, fontweight="bold")
    fig.suptitle(f"Dataset: {dataset_name} — {len(dataset_labels)} samples",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(level_dir, "4_sentiment_distribution.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 5. Per-class F1 grouped bar chart ─────────────────────
    fig, ax = plt.subplots(figsize=(13, 6))
    x = np.arange(len(names))
    w = 0.25
    class_colors = {"NEGATIVE": "#E74C3C", "NEUTRAL": "#95A5A6", "POSITIVE": "#2ECC71"}
    f1_data = {
        "NEGATIVE": [r.f1_neg for r in results],
        "NEUTRAL":  [r.f1_neu for r in results],
        "POSITIVE": [r.f1_pos for r in results],
    }
    offsets = [-w, 0, w]
    for (cls, vals), offset in zip(f1_data.items(), offsets):
        bars = ax.bar(x + offset, vals, w, label=cls,
                      color=class_colors[cls], edgecolor="white", alpha=0.85)
        for bar in bars:
            if bar.get_height() > 2:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                        f"{bar.get_height():.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.set_ylabel("F1-score (%)")
    ax.set_ylim(0, 100)
    ax.set_title(f"Per-class F1-score — {dataset_name}",
                 fontsize=14, fontweight="bold")
    ax.legend(title="Sentiment Class")
    plt.tight_layout()
    path = os.path.join(level_dir, "5_per_class_f1.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 6. Summary Dashboard (all in one) ─────────────────────
    fig = plt.figure(figsize=(20, 14))
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Top-left : Accuracy + F1
    ax1 = fig.add_subplot(gs[0, 0])
    x = np.arange(len(names))
    w = 0.35
    ax1.bar(x - w/2, [r.accuracy  for r in results], w, label="Accuracy",  color="#4C72B0", alpha=0.8)
    ax1.bar(x + w/2, [r.f1_macro for r in results], w, label="F1-macro",  color="#DD8452", alpha=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels([n.split(" ")[0] for n in names], rotation=20, ha="right", fontsize=9)
    ax1.set_title("Accuracy & F1-macro", fontweight="bold")
    ax1.set_ylim(0, 100)
    ax1.legend(fontsize=8)

    # Top-center : Speed
    ax2 = fig.add_subplot(gs[0, 1])
    spd_colors = ["#2ECC71" if r.speed_ms < 5 else "#F39C12" if r.speed_ms < 50 else "#E74C3C"
                  for r in results]
    ax2.barh([n.split(" ")[0] for n in names], [r.speed_ms for r in results],
             color=spd_colors, edgecolor="white")
    ax2.set_xlabel("ms/sample")
    ax2.set_title("Inference Speed", fontweight="bold")

    # Top-right : Distribution pie
    ax3 = fig.add_subplot(gs[0, 2])
    counts = Counter(dataset_labels)
    pie_c  = [label_colors.get(l, "#999") for l in counts.keys()]
    ax3.pie(list(counts.values()), labels=list(counts.keys()),
            colors=pie_c, autopct="%1.0f%%", startangle=90,
            wedgeprops={"edgecolor": "white", "linewidth": 2})
    ax3.set_title("Dataset Distribution", fontweight="bold")

    # Bottom : Confusion matrix of winner
    winner = max(results, key=lambda r: r.f1_macro)
    ax4 = fig.add_subplot(gs[1, 0])
    cm = confusion_matrix(winner.labels, winner.predictions, labels=LABELS)
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=LABELS, yticklabels=LABELS, ax=ax4, cbar=False)
    ax4.set_title(f"Best Model: {winner.name.split('(')[0]}\nConfusion Matrix",
                  fontweight="bold")
    ax4.set_xlabel("Predicted")
    ax4.set_ylabel("True")

    # Bottom-center : Per-class F1
    ax5 = fig.add_subplot(gs[1, 1:])
    x = np.arange(len(names))
    for (cls, vals), offset in zip(f1_data.items(), offsets):
        ax5.bar(x + offset, vals, w, label=cls, color=class_colors[cls], alpha=0.85)
    ax5.set_xticks(x)
    ax5.set_xticklabels([n.split(" ")[0] for n in names], rotation=15, ha="right", fontsize=9)
    ax5.set_ylabel("F1-score (%)")
    ax5.set_ylim(0, 100)
    ax5.set_title("Per-class F1-score", fontweight="bold")
    ax5.legend(title="Class", fontsize=9)

    fig.suptitle(
        f"InsightFlow Executive — NLP Benchmark Dashboard\nDataset: {dataset_name} | {len(dataset_labels)} samples",
        fontsize=16, fontweight="bold", y=1.01,
    )
    path = os.path.join(level_dir, "0_benchmark_dashboard.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════
#  MAIN BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════

def run_benchmark(n_samples: int = 500, dataset: str = "tweeteval", level: str = "2"):
    """
    dataset options: "tweeteval" | "financial" | "enron"
    level         : "1" | "2" | "3"  (used for chart subfolder)
    """
    if dataset == "financial":
        texts, labels = load_financial_phrasebank_csv(n_samples)
        dataset_name = "Financial PhraseBank"
    elif dataset == "enron":
        texts, labels = load_enron(n_samples)
        dataset_name = "Enron Emails (Corporate)"
        if not texts:
            return
    elif dataset == "synthetic_en":
        texts, labels = load_synthetic(n_samples, lang="en")
        dataset_name = "InsightFlow Synthetic (English)"
        if not texts:
            return
    elif dataset == "synthetic_fr":
        texts, labels = load_synthetic(n_samples, lang="fr")
        dataset_name = "InsightFlow Synthetic (French)"
        if not texts:
            return
    elif dataset == "synthetic_full":
        texts, labels = load_synthetic(n_samples, lang="full")
        dataset_name = "InsightFlow Synthetic (EN + FR)"
        if not texts:
            return
    else:
        texts, labels = load_tweeteval(n_samples)
        dataset_name = "TweetEval Sentiment"

    results: list[ModelResult] = []

    print(f"\n[1/5] VADER...")
    preds, ms = run_vader(texts)
    results.append(evaluate("VADER (rule-based)", preds, labels, ms))

    print(f"[2/5] TextBlob...")
    preds, ms = run_textblob(texts)
    results.append(evaluate("TextBlob (rule-based)", preds, labels, ms))

    print(f"[3/5] DistilBERT...")
    preds, ms = run_hf_model("distilbert-base-uncased-finetuned-sst-2-english",
                              texts, DISTILBERT_MAP)
    results.append(evaluate("DistilBERT (EN)", preds, labels, ms))

    print(f"[4/5] RoBERTa...")
    preds, ms = run_hf_model("cardiffnlp/twitter-roberta-base-sentiment-latest",
                              texts, ROBERTA_MAP)
    results.append(evaluate("RoBERTa Twitter (EN)", preds, labels, ms))

    print(f"[5/5] XLM-RoBERTa...")
    preds, ms = run_hf_model("cardiffnlp/twitter-xlm-roberta-base-sentiment",
                              texts, XLM_MAP)
    results.append(evaluate("XLM-RoBERTa (FR+EN)", preds, labels, ms))

    # ── Results table ──────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  InsightFlow Executive — Benchmark Results")
    print(f"  Dataset : {dataset_name} | Samples : {len(texts)}")
    print(f"{'='*70}")
    table = [[r.name, f"{r.accuracy}%", f"{r.f1_macro}%",
              f"{r.f1_neg}%", f"{r.f1_neu}%", f"{r.f1_pos}%",
              f"{r.speed_ms} ms"] for r in results]
    print(tabulate(table,
        headers=["Model", "Accuracy", "F1-macro", "F1-NEG", "F1-NEU", "F1-POS", "Speed"],
        tablefmt="rounded_outline"))

    winner = max(results, key=lambda r: r.f1_macro)
    print(f"\n  Winner : {winner.name}")
    print(f"  F1-macro : {winner.f1_macro}% | Accuracy : {winner.accuracy}% | Speed : {winner.speed_ms}ms")
    print(f"{'='*70}")
    print(classification_report(winner.labels, winner.predictions, labels=LABELS, zero_division=0))

    # ── Generate charts ────────────────────────────────────────
    print(f"\n[Charts] Generating report charts → ml/charts/")
    try:
        generate_charts(results, labels, dataset_name, level=level)
        print(f"[Charts] All charts saved to: {CHARTS_DIR}/level{level}/")
    except ImportError:
        print("[Charts] matplotlib/seaborn not installed. Run: pip install matplotlib seaborn")

    return results, winner


def run_domain_validation(n_samples: int = 200):
    """
    Level 3 — Domain Validation on Enron corporate emails.
    Shows how models behave on real enterprise communication text.
    Uses silver labels (majority vote) as pseudo ground-truth.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    from collections import Counter

    texts, silver_labels = load_enron(n_samples)
    if not texts:
        return

    print(f"\n{'='*70}")
    print(f"  Level 3 — Domain Validation : Enron Corporate Emails")
    print(f"  {len(texts)} ham emails | Silver labels via majority vote")
    print(f"{'='*70}")

    # Run transformer models only (skip rule-based — already evaluated)
    models = {
        "RoBERTa Twitter (EN)":  ("cardiffnlp/twitter-roberta-base-sentiment-latest", ROBERTA_MAP),
        "XLM-RoBERTa (FR+EN)":   ("cardiffnlp/twitter-xlm-roberta-base-sentiment", XLM_MAP),
        "DistilBERT (EN)":        ("distilbert-base-uncased-finetuned-sst-2-english", DISTILBERT_MAP),
    }

    all_preds = {}
    results   = []
    for name, (model_id, label_map) in models.items():
        print(f"\n  Running {name}...")
        preds, ms = run_hf_model(model_id, texts, label_map)
        all_preds[name] = preds
        results.append(evaluate(name, preds, silver_labels, ms))

    # Print results
    table = [[r.name, f"{r.accuracy}%", f"{r.f1_macro}%", f"{r.speed_ms}ms"]
             for r in results]
    print("\n" + tabulate(table,
        headers=["Model", "Accuracy*", "F1-macro*", "Speed"],
        tablefmt="rounded_outline"))
    print("  * vs silver labels (majority vote) — not human annotation\n")

    # ── Inter-model agreement ─────────────────────────────────
    print("  Inter-model agreement (% same prediction):")
    model_names = list(all_preds.keys())
    for i in range(len(model_names)):
        for j in range(i + 1, len(model_names)):
            n1, n2 = model_names[i], model_names[j]
            agree = sum(p1 == p2 for p1, p2 in zip(all_preds[n1], all_preds[n2]))
            print(f"    {n1.split('(')[0].strip()} ↔ {n2.split('(')[0].strip()}: {agree/len(texts)*100:.1f}%")

    # ── Full charts (same as level 1 & 2) ────────────────────
    print(f"\n[Charts] Generating Level 3 charts → ml/charts/level3/")
    try:
        generate_charts(results, silver_labels, "Enron Corporate Emails", level="3")

        # Extra : distribution per model (specific to domain validation)
        sns.set_theme(style="whitegrid", font_scale=1.1)
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        label_colors = {"NEGATIVE": "#E74C3C", "NEUTRAL": "#95A5A6", "POSITIVE": "#2ECC71"}
        for ax, (name, preds) in zip(axes, all_preds.items()):
            counts = Counter(preds)
            lbls = ["NEGATIVE", "NEUTRAL", "POSITIVE"]
            vals = [counts.get(l, 0) for l in lbls]
            bars = ax.bar(lbls, vals, color=[label_colors[l] for l in lbls], edgecolor="white")
            for bar in bars:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                        f"{bar.get_height()}\n({bar.get_height()/len(texts)*100:.0f}%)",
                        ha="center", va="bottom", fontsize=10)
            ax.set_title(name, fontweight="bold", fontsize=11)
            ax.set_ylabel("Count")
            ax.set_ylim(0, len(texts))
        fig.suptitle("Level 3 — Model Distribution on Enron Corporate Emails",
                     fontsize=14, fontweight="bold")
        plt.tight_layout()
        level3_dir = os.path.join(CHARTS_DIR, "level3")
        path = os.path.join(level3_dir, "7_domain_distribution_per_model.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")
    except ImportError:
        print("[Charts] matplotlib/seaborn not installed.")
    print(f"{'='*70}")


if __name__ == "__main__":
    import sys
    level = sys.argv[1] if len(sys.argv) > 1 else "2"

    if level == "1":
        print("\n>>> Level 1 — Academic Benchmark (Financial PhraseBank)")
        run_benchmark(n_samples=300, dataset="financial", level="1")
    elif level == "3":
        print("\n>>> Level 3 — Domain Validation (Enron Corporate Emails)")
        run_domain_validation(n_samples=200)
    elif level == "4en":
        print("\n>>> Level 4 — InsightFlow Synthetic Dataset (English)")
        run_benchmark(n_samples=500, dataset="synthetic_en", level="4en")
    elif level == "4fr":
        print("\n>>> Level 4 — InsightFlow Synthetic Dataset (French)")
        run_benchmark(n_samples=500, dataset="synthetic_fr", level="4fr")
    elif level == "4full":
        print("\n>>> Level 4 — InsightFlow Synthetic Dataset (EN + FR)")
        run_benchmark(n_samples=1000, dataset="synthetic_full", level="4full")
    else:
        print("\n>>> Level 2 — Conversational Benchmark (TweetEval)")
        run_benchmark(n_samples=500, dataset="tweeteval", level="2")
