"""
InsightFlow Executive — Exploratory Data Analysis (EDA)
=======================================================
Analyse complète du dataset synthétique avant fine-tuning.

Analyses produites :
  1. Vue d'ensemble          — taille, langues, sources
  2. Distribution des classes — sentiment, émotion, business
  3. Longueur des textes      — distribution par classe
  4. Qualité des données      — manquants, doublons, trop courts
  5. Corrélations             — sentiment × émotion × business
  6. Mots fréquents           — top keywords par classe
  7. Distribution temporelle  — messages par heure/jour
  8. Dashboard global         — tout en un

Usage :
    python ml/eda.py
    python ml/eda.py --lang en
    python ml/eda.py --lang fr
"""

from __future__ import annotations
import argparse
import csv
import os
import re
from collections import Counter, defaultdict

import numpy as np

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
CHARTS_DIR  = os.path.join(os.path.dirname(__file__), "charts", "eda")
os.makedirs(CHARTS_DIR, exist_ok=True)

SENTIMENT_LABELS = ["POSITIVE", "NEUTRAL", "NEGATIVE"]
EMOTION_LABELS   = ["frustration", "concern", "urgency", "neutral", "satisfaction"]
BUSINESS_LABELS  = ["Progress", "Neutral Update", "Concern", "Risk",
                    "Blocked", "Overload", "Conflict", "Urgent"]

SENTIMENT_COLORS = {"POSITIVE": "#2ECC71", "NEUTRAL": "#95A5A6", "NEGATIVE": "#E74C3C"}
EMOTION_COLORS   = {
    "frustration": "#E74C3C", "concern": "#F39C12",
    "urgency": "#9B59B6", "neutral": "#95A5A6", "satisfaction": "#2ECC71",
}
BUSINESS_COLORS  = {
    "Progress": "#2ECC71", "Neutral Update": "#95A5A6",
    "Concern": "#F39C12",  "Risk": "#E67E22",
    "Blocked": "#E74C3C",  "Overload": "#C0392B",
    "Conflict": "#8E44AD", "Urgent": "#922B21",
}
SOURCE_COLORS = {
    "gmail": "#EA4335", "slack": "#4A154B", "jira": "#0052CC",
    "teams": "#6264A7", "crm": "#00B4F0",
}


# ─────────────────────────────────────────────────────────────────
#  DATA LOADING
# ─────────────────────────────────────────────────────────────────

def load_dataset(lang: str = "full") -> list[dict]:
    file_map = {
        "en":   "insightflow_synthetic_en.csv",
        "fr":   "insightflow_synthetic_fr.csv",
        "full": "insightflow_synthetic_full.csv",
    }
    path = os.path.join(DATASET_DIR, file_map.get(lang, "insightflow_synthetic_full.csv"))
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"[EDA] Loaded {len(rows)} rows from {os.path.basename(path)}")
    return rows


def text_length(text: str) -> int:
    return len(text.split())


# ─────────────────────────────────────────────────────────────────
#  EDA FUNCTIONS
# ─────────────────────────────────────────────────────────────────

def print_overview(rows: list[dict], lang: str):
    print(f"\n{'='*65}")
    print(f"  InsightFlow EDA — Dataset Overview ({lang.upper()})")
    print(f"{'='*65}")
    print(f"  Total rows       : {len(rows)}")

    # Missing values
    for col in ["content", "sentiment_label", "emotion_label", "business_label", "topic"]:
        missing = sum(1 for r in rows if not r.get(col, "").strip())
        pct = missing / len(rows) * 100
        print(f"  Missing {col:<20}: {missing:>5} ({pct:.1f}%)")

    # Duplicates
    contents = [r.get("content", "").strip()[:200] for r in rows]
    dupes = len(contents) - len(set(contents))
    print(f"  Duplicate content: {dupes:>5} ({dupes/len(rows)*100:.1f}%)")

    # Text length stats
    lengths = [text_length(r.get("content", "")) for r in rows if r.get("content", "").strip()]
    print(f"\n  Text length (words):")
    print(f"    Min    : {min(lengths)}")
    print(f"    Max    : {max(lengths)}")
    print(f"    Mean   : {np.mean(lengths):.1f}")
    print(f"    Median : {np.median(lengths):.1f}")
    too_short = sum(1 for l in lengths if l < 5)
    print(f"    < 5 words (à supprimer) : {too_short}")

    # Source distribution
    sources = Counter(r.get("source", "unknown") for r in rows)
    print(f"\n  Source distribution:")
    for src, cnt in sources.most_common():
        print(f"    {src:<12} {cnt:>5} ({cnt/len(rows)*100:.1f}%)")

    # Item type
    types = Counter(r.get("item_type", "unknown") for r in rows)
    print(f"\n  Item type:")
    for t, cnt in types.most_common():
        print(f"    {t:<12} {cnt:>5} ({cnt/len(rows)*100:.1f}%)")

    print(f"{'='*65}")


def analyze_labels(rows: list[dict]) -> dict:
    """Retourne les distributions de labels."""
    sentiment = Counter(r["sentiment_label"] for r in rows
                        if r.get("sentiment_label") in SENTIMENT_LABELS)
    emotion   = Counter(r["emotion_label"] for r in rows
                        if r.get("emotion_label") in EMOTION_LABELS)
    business  = Counter(r["business_label"] for r in rows
                        if r.get("business_label") in BUSINESS_LABELS)
    topic     = Counter(r.get("topic", "") for r in rows if r.get("topic", "").strip())
    source    = Counter(r.get("source", "") for r in rows if r.get("source", "").strip())

    print(f"\n  Sentiment distribution:")
    total = sum(sentiment.values())
    for lbl in SENTIMENT_LABELS:
        cnt = sentiment.get(lbl, 0)
        bar = "█" * int(cnt / total * 40)
        print(f"    {lbl:<10} {cnt:>5} ({cnt/total*100:.1f}%) {bar}")

    print(f"\n  Emotion distribution:")
    total_e = sum(emotion.values())
    if total_e:
        for lbl in EMOTION_LABELS:
            cnt = emotion.get(lbl, 0)
            bar = "█" * int(cnt / total_e * 40)
            print(f"    {lbl:<14} {cnt:>5} ({cnt/total_e*100:.1f}%) {bar}")

    imbalance_ratio = max(sentiment.values()) / max(min(sentiment.values()), 1)
    print(f"\n  Imbalance ratio (sentiment) : {imbalance_ratio:.1f}x")
    if imbalance_ratio > 2:
        print(f"  ⚠ Dataset déséquilibré — rééquilibrage recommandé")

    return {"sentiment": sentiment, "emotion": emotion,
            "business": business, "topic": topic, "source": source}


def analyze_text_quality(rows: list[dict]) -> dict:
    """Analyse la qualité du texte."""
    lengths_by_sentiment = defaultdict(list)
    lengths_by_emotion   = defaultdict(list)

    for row in rows:
        content = row.get("content", "").strip()
        if not content:
            continue
        length = text_length(content)
        sent   = row.get("sentiment_label", "")
        emo    = row.get("emotion_label", "")
        if sent in SENTIMENT_LABELS:
            lengths_by_sentiment[sent].append(length)
        if emo in EMOTION_LABELS:
            lengths_by_emotion[emo].append(length)

    print(f"\n  Longueur moyenne par sentiment :")
    for lbl in SENTIMENT_LABELS:
        vals = lengths_by_sentiment.get(lbl, [0])
        print(f"    {lbl:<10} : {np.mean(vals):.0f} mots (median: {np.median(vals):.0f})")

    print(f"\n  Longueur moyenne par émotion :")
    for lbl in EMOTION_LABELS:
        vals = lengths_by_emotion.get(lbl, [0])
        print(f"    {lbl:<14} : {np.mean(vals):.0f} mots (median: {np.median(vals):.0f})")

    return {"by_sentiment": lengths_by_sentiment, "by_emotion": lengths_by_emotion}


def analyze_keywords(rows: list[dict]) -> dict:
    """Top keywords par classe de sentiment."""
    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "is", "it", "this", "that", "be", "are",
        "was", "were", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "not", "no",
        "from", "by", "as", "we", "you", "i", "my", "your", "our",
        "their", "its", "re", "hi", "hello", "thanks", "thank", "please",
        "let", "know", "get", "just", "also", "been", "about", "up",
        "out", "if", "so", "all", "more", "team", "would", "been",
        "le", "la", "les", "de", "du", "un", "une", "des", "en", "et",
        "est", "je", "nous", "vous", "ils", "que", "qui", "dans", "sur",
    }
    keywords_by_class = {}
    for lbl in SENTIMENT_LABELS:
        texts = [r.get("content", "") for r in rows
                 if r.get("sentiment_label") == lbl]
        words = []
        for t in texts:
            tokens = re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", t.lower())
            words.extend(w for w in tokens if w not in STOPWORDS)
        top = Counter(words).most_common(10)
        keywords_by_class[lbl] = top
        print(f"\n  Top mots — {lbl}:")
        for word, cnt in top[:8]:
            print(f"    {word:<20} {cnt}")

    return keywords_by_class


def analyze_correlations(rows: list[dict]):
    """Corrélation sentiment × émotion."""
    print(f"\n  Corrélation Sentiment × Émotion :")
    print(f"  {'':>14}", end="")
    for emo in EMOTION_LABELS:
        print(f"  {emo[:8]:>8}", end="")
    print()

    for sent in SENTIMENT_LABELS:
        print(f"  {sent:<14}", end="")
        sent_rows = [r for r in rows if r.get("sentiment_label") == sent]
        total = max(len(sent_rows), 1)
        for emo in EMOTION_LABELS:
            cnt = sum(1 for r in sent_rows if r.get("emotion_label") == emo)
            pct = cnt / total * 100
            print(f"  {pct:>7.1f}%", end="")
        print()


# ─────────────────────────────────────────────────────────────────
#  CHARTS
# ─────────────────────────────────────────────────────────────────

def generate_charts(rows: list[dict], distributions: dict, lengths: dict, lang: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import seaborn as sns
    except ImportError:
        print("[Charts] matplotlib/seaborn non installé — skip.")
        return

    sns.set_theme(style="whitegrid", font_scale=1.05)

    # 1. Distribution des classes sentiment
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Sentiment
    sent = distributions["sentiment"]
    lbls = [l for l in SENTIMENT_LABELS if l in sent]
    vals = [sent[l] for l in lbls]
    clrs = [SENTIMENT_COLORS[l] for l in lbls]
    axes[0].bar(lbls, vals, color=clrs, edgecolor="white", linewidth=1.5)
    for i, v in enumerate(vals):
        axes[0].text(i, v + 5, f"{v}\n({v/sum(vals)*100:.1f}%)", ha="center", fontsize=10)
    axes[0].set_title("Sentiment Distribution", fontweight="bold", fontsize=13)
    axes[0].set_ylabel("Count")

    # Émotion
    emo = distributions["emotion"]
    if emo:
        e_lbls = [l for l in EMOTION_LABELS if l in emo]
        e_vals = [emo[l] for l in e_lbls]
        e_clrs = [EMOTION_COLORS[l] for l in e_lbls]
        axes[1].bar(e_lbls, e_vals, color=e_clrs, edgecolor="white", linewidth=1.5)
        for i, v in enumerate(e_vals):
            axes[1].text(i, v + 2, f"{v}\n({v/sum(e_vals)*100:.1f}%)", ha="center", fontsize=9)
        axes[1].set_title("Emotion Distribution", fontweight="bold", fontsize=13)
        axes[1].tick_params(axis="x", rotation=20)

    # Source
    src = distributions["source"]
    s_lbls = [l for l in src.keys()][:6]
    s_vals = [src[l] for l in s_lbls]
    s_clrs = [SOURCE_COLORS.get(l, "#748cab") for l in s_lbls]
    axes[2].bar(s_lbls, s_vals, color=s_clrs, edgecolor="white", linewidth=1.5)
    for i, v in enumerate(s_vals):
        axes[2].text(i, v + 2, str(v), ha="center", fontsize=10)
    axes[2].set_title("Source Distribution", fontweight="bold", fontsize=13)

    fig.suptitle(f"InsightFlow Dataset — Class Distributions ({lang.upper()})",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "1_class_distributions.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: 1_class_distributions.png")

    # 2. Text length distribution par sentiment
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for lbl in SENTIMENT_LABELS:
        vals = lengths["by_sentiment"].get(lbl, [])
        if vals:
            axes[0].hist(vals, bins=30, alpha=0.6, label=lbl,
                         color=SENTIMENT_COLORS[lbl], edgecolor="white")
    axes[0].set_xlabel("Longueur (mots)")
    axes[0].set_ylabel("Count")
    axes[0].set_title("Longueur des textes par sentiment", fontweight="bold")
    axes[0].legend()
    axes[0].axvline(x=5, color="red", linestyle="--", alpha=0.5, label="min=5")

    for lbl in EMOTION_LABELS:
        vals = lengths["by_emotion"].get(lbl, [])
        if vals:
            axes[1].hist(vals, bins=30, alpha=0.6, label=lbl,
                         color=EMOTION_COLORS[lbl], edgecolor="white")
    axes[1].set_xlabel("Longueur (mots)")
    axes[1].set_title("Longueur des textes par émotion", fontweight="bold")
    axes[1].legend(fontsize=9)

    fig.suptitle("Distribution des longueurs de texte", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "2_text_lengths.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: 2_text_lengths.png")

    # 3. Matrice de corrélation sentiment × émotion
    sent_rows_all = [r for r in rows if r.get("sentiment_label") in SENTIMENT_LABELS
                     and r.get("emotion_label") in EMOTION_LABELS]
    if sent_rows_all:
        matrix = np.zeros((len(SENTIMENT_LABELS), len(EMOTION_LABELS)))
        for r in sent_rows_all:
            si = SENTIMENT_LABELS.index(r["sentiment_label"])
            ei = EMOTION_LABELS.index(r["emotion_label"])
            matrix[si][ei] += 1
        # Normaliser par ligne
        row_sums = matrix.sum(axis=1, keepdims=True)
        matrix_pct = np.divide(matrix, row_sums, where=row_sums > 0) * 100

        fig, ax = plt.subplots(figsize=(10, 5))
        sns.heatmap(matrix_pct, annot=True, fmt=".1f", cmap="YlOrRd",
                    xticklabels=EMOTION_LABELS, yticklabels=SENTIMENT_LABELS,
                    ax=ax, cbar_kws={"label": "%"})
        ax.set_title("Corrélation Sentiment × Émotion (%)", fontweight="bold", fontsize=13)
        ax.set_xlabel("Émotion")
        ax.set_ylabel("Sentiment")
        plt.tight_layout()
        plt.savefig(os.path.join(CHARTS_DIR, "3_sentiment_emotion_correlation.png"),
                    dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: 3_sentiment_emotion_correlation.png")

    # 4. Business label distribution
    biz = distributions["business"]
    if biz:
        b_lbls = [l for l in BUSINESS_LABELS if l in biz]
        b_vals = [biz[l] for l in b_lbls]
        b_clrs = [BUSINESS_COLORS[l] for l in b_lbls]
        fig, ax = plt.subplots(figsize=(12, 5))
        bars = ax.bar(b_lbls, b_vals, color=b_clrs, edgecolor="white", linewidth=1.5)
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                    f"{bar.get_height()}", ha="center", fontsize=10)
        ax.set_title("Business Label Distribution", fontweight="bold", fontsize=13)
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=20)
        plt.tight_layout()
        plt.savefig(os.path.join(CHARTS_DIR, "4_business_distribution.png"),
                    dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: 4_business_distribution.png")

    # 5. Dashboard global
    fig = plt.figure(figsize=(20, 16))
    gs  = gridspec.GridSpec(3, 3, figure=fig, hspace=0.5, wspace=0.4)

    # Row 1 : distributions
    ax1 = fig.add_subplot(gs[0, 0])
    sent = distributions["sentiment"]
    lbls = [l for l in SENTIMENT_LABELS if l in sent]
    vals = [sent[l] for l in lbls]
    ax1.pie(vals, labels=lbls, colors=[SENTIMENT_COLORS[l] for l in lbls],
            autopct="%1.1f%%", startangle=90, wedgeprops={"edgecolor": "white"})
    ax1.set_title("Sentiment", fontweight="bold")

    ax2 = fig.add_subplot(gs[0, 1])
    emo = distributions["emotion"]
    if emo:
        e_lbls = [l for l in EMOTION_LABELS if l in emo]
        e_vals = [emo[l] for l in e_lbls]
        ax2.pie(e_vals, labels=e_lbls, colors=[EMOTION_COLORS[l] for l in e_lbls],
                autopct="%1.0f%%", startangle=90, wedgeprops={"edgecolor": "white"})
    ax2.set_title("Émotion", fontweight="bold")

    ax3 = fig.add_subplot(gs[0, 2])
    src = distributions["source"]
    s_lbls = list(src.keys())[:6]
    s_vals = [src[l] for l in s_lbls]
    ax3.pie(s_vals, labels=s_lbls, colors=[SOURCE_COLORS.get(l, "#748cab") for l in s_lbls],
            autopct="%1.0f%%", startangle=90, wedgeprops={"edgecolor": "white"})
    ax3.set_title("Source", fontweight="bold")

    # Row 2 : longueurs
    ax4 = fig.add_subplot(gs[1, :2])
    all_lengths = [text_length(r.get("content", "")) for r in rows if r.get("content")]
    ax4.hist(all_lengths, bins=50, color="#3e5c76", edgecolor="white", alpha=0.8)
    ax4.axvline(x=5, color="red", linestyle="--", label="min seuil (5 mots)")
    ax4.axvline(x=np.mean(all_lengths), color="orange", linestyle="--",
                label=f"moyenne ({np.mean(all_lengths):.0f})")
    ax4.set_xlabel("Longueur (mots)")
    ax4.set_ylabel("Count")
    ax4.set_title("Distribution des longueurs de texte", fontweight="bold")
    ax4.legend()

    # Row 2 right: business
    ax5 = fig.add_subplot(gs[1, 2])
    biz = distributions["business"]
    if biz:
        b_lbls = [l for l in BUSINESS_LABELS if l in biz][:6]
        b_vals = [biz[l] for l in b_lbls]
        ax5.barh(b_lbls, b_vals, color=[BUSINESS_COLORS[l] for l in b_lbls], edgecolor="white")
        ax5.set_title("Business Labels", fontweight="bold")

    # Row 3: heatmap corrélation
    ax6 = fig.add_subplot(gs[2, :])
    if sent_rows_all:
        sns.heatmap(matrix_pct, annot=True, fmt=".1f", cmap="YlOrRd",
                    xticklabels=EMOTION_LABELS, yticklabels=SENTIMENT_LABELS,
                    ax=ax6, cbar_kws={"label": "%"})
        ax6.set_title("Corrélation Sentiment × Émotion (%)", fontweight="bold")

    fig.suptitle(
        f"InsightFlow Executive — EDA Dashboard\nDataset: {lang.upper()} | {len(rows)} samples",
        fontsize=16, fontweight="bold",
    )
    plt.savefig(os.path.join(CHARTS_DIR, "0_eda_dashboard.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: 0_eda_dashboard.png")
    print(f"[Charts] All saved to: {CHARTS_DIR}/")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def run_eda(lang: str = "full"):
    rows = load_dataset(lang)
    print_overview(rows, lang)
    distributions = analyze_labels(rows)
    lengths       = analyze_text_quality(rows)
    keywords      = analyze_keywords(rows)
    analyze_correlations(rows)

    print(f"\n[Charts] Generating EDA charts → ml/charts/eda/")
    generate_charts(rows, distributions, lengths, lang)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="full", choices=["en", "fr", "full"])
    args = parser.parse_args()
    run_eda(lang=args.lang)
