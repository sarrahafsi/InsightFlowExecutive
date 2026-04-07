"""
InsightFlow Executive — Data Preprocessing Pipeline
====================================================
Nettoyage + équilibrage + déduplication du dataset synthétique.
Produit un dataset propre prêt pour le fine-tuning.

Étapes :
  1. Nettoyage texte    — URLs, signatures, caractères spéciaux, espaces
  2. Filtrage qualité   — textes trop courts (< 5 mots) ou trop longs (> 300)
  3. Déduplication      — suppression des doublons exacts
  4. Équilibrage        — oversampling minorité OU undersampling majoritaire
  5. Split              — train / val / test (70/15/15)
  6. Export             — CSV prêts pour fine-tuning

Usage :
    python ml/preprocess.py                          # full dataset, both tasks
    python ml/preprocess.py --lang en --task sentiment
    python ml/preprocess.py --strategy undersample   # ou oversample (défaut)

Outputs :
    ml/dataset/clean_sentiment_train.csv
    ml/dataset/clean_sentiment_val.csv
    ml/dataset/clean_sentiment_test.csv
    ml/dataset/clean_emotion_train.csv
    ml/dataset/clean_emotion_val.csv
    ml/dataset/clean_emotion_test.csv
    ml/dataset/preprocessing_report.json
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import random
import re
from collections import Counter
from datetime import datetime

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")

SENTIMENT_LABELS = {"POSITIVE", "NEUTRAL", "NEGATIVE"}
EMOTION_LABELS   = {"frustration", "concern", "urgency", "neutral", "satisfaction"}

SEED = 42
random.seed(SEED)

# ─────────────────────────────────────────────────────────────────
#  TEXT CLEANING
# ─────────────────────────────────────────────────────────────────

# Patterns à supprimer
_URL_RE         = re.compile(r"https?://\S+|www\.\S+")
_EMAIL_RE       = re.compile(r"\S+@\S+\.\S+")
_ENCODED_RE     = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")   # base64 / tokens
_MULTI_SPACE_RE = re.compile(r"\s+")
_SPECIAL_RE     = re.compile(r"[^\w\s\.\,\!\?\-\'\"\:\;\(\)àâäéèêëîïôùûüçœæÀÂÄÉÈÊËÎÏÔÙÛÜÇŒÆ]")

# Patterns de signatures email
_SIGNATURE_PATTERNS = [
    r"(?i)(best regards?|kind regards?|cordialement|bien cordialement|"
    r"regards?|thanks?|merci|sincèrement|bonne journée|"
    r"sent from my (iphone|android|samsung)|"
    r"get outlook for|ce message a été envoyé depuis).*$",
]
_SIGNATURE_RE = re.compile("|".join(_SIGNATURE_PATTERNS), re.MULTILINE | re.DOTALL)

# Séparateurs de fil de discussion
_THREAD_SEP_RE = re.compile(
    r"(?i)(on .{5,60} wrote:|de :.{5,60}\nà :.{5,60}|"
    r"-----original message-----|_{10,}|-{10,}|>{2,})",
    re.MULTILINE,
)


def clean_text(text: str) -> str:
    """Nettoie un texte pour le fine-tuning."""
    if not text:
        return ""

    # Supprimer la partie après la signature
    text = _SIGNATURE_RE.sub("", text)

    # Supprimer les fils de discussion (garder seulement le premier message)
    text = _THREAD_SEP_RE.split(text)[0]

    # Supprimer URLs, emails, tokens encodés
    text = _URL_RE.sub(" ", text)
    text = _EMAIL_RE.sub(" ", text)
    text = _ENCODED_RE.sub(" ", text)

    # Supprimer caractères spéciaux inutiles
    text = _SPECIAL_RE.sub(" ", text)

    # Normaliser les espaces
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    return text


def word_count(text: str) -> int:
    return len(text.split())


# ─────────────────────────────────────────────────────────────────
#  LOADING + CLEANING
# ─────────────────────────────────────────────────────────────────

def load_and_clean(lang: str = "full") -> list[dict]:
    """Charge et nettoie le dataset complet."""
    file_map = {
        "en":   "insightflow_synthetic_en.csv",
        "fr":   "insightflow_synthetic_fr.csv",
        "full": "insightflow_synthetic_full.csv",
    }
    path = os.path.join(DATASET_DIR, file_map.get(lang, "insightflow_synthetic_full.csv"))

    with open(path, encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))

    print(f"[Preprocess] Loaded {len(raw_rows)} raw rows from {os.path.basename(path)}")

    cleaned = []
    stats = {
        "raw": len(raw_rows),
        "removed_empty": 0,
        "removed_too_short": 0,
        "removed_too_long": 0,
    }

    for row in raw_rows:
        content = row.get("content", "").strip()
        if not content:
            stats["removed_empty"] += 1
            continue

        cleaned_content = clean_text(content)
        wc = word_count(cleaned_content)

        if wc < 5:
            stats["removed_too_short"] += 1
            continue
        if wc > 300:
            # Tronquer à 300 mots plutôt que supprimer
            cleaned_content = " ".join(cleaned_content.split()[:300])

        row["content_clean"] = cleaned_content
        row["word_count"]    = wc
        cleaned.append(row)

    print(f"[Preprocess] After cleaning: {len(cleaned)} rows")
    print(f"             Removed empty    : {stats['removed_empty']}")
    print(f"             Removed too short: {stats['removed_too_short']}")
    print(f"             Removed too long : {stats['removed_too_long']}")

    return cleaned, stats


# ─────────────────────────────────────────────────────────────────
#  DEDUPLICATION
# ─────────────────────────────────────────────────────────────────

def deduplicate(rows: list[dict]) -> tuple[list[dict], int]:
    """Supprime les doublons basés sur les 150 premiers caractères du texte nettoyé."""
    seen = set()
    unique = []
    for row in rows:
        key = row.get("content_clean", "")[:150].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(row)

    removed = len(rows) - len(unique)
    print(f"[Preprocess] Deduplication: {removed} doublons supprimés → {len(unique)} rows uniques")
    return unique, removed


# ─────────────────────────────────────────────────────────────────
#  BALANCING
# ─────────────────────────────────────────────────────────────────

def balance_dataset(rows: list[dict], label_col: str,
                    valid_labels: set, strategy: str = "oversample") -> list[dict]:
    """
    Équilibre le dataset.
    strategy : 'oversample' (augmente les minorités)
               'undersample' (réduit les majorités)
               'none' (garde tel quel, utilise class weights)
    """
    by_label: dict[str, list] = {lbl: [] for lbl in valid_labels}
    for row in rows:
        lbl = row.get(label_col, "").strip()
        if lbl in valid_labels:
            by_label[lbl].append(row)

    counts = {k: len(v) for k, v in by_label.items()}
    print(f"\n[Balance] Distribution avant ({label_col}) :")
    for lbl, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"          {lbl:<16} {cnt:>5}")

    if strategy == "none":
        result = [r for rows_list in by_label.values() for r in rows_list]
        random.shuffle(result)
        return result

    if strategy == "undersample":
        target = min(counts.values())
        balanced = []
        for lbl, lbl_rows in by_label.items():
            balanced.extend(random.sample(lbl_rows, min(target, len(lbl_rows))))

    else:  # oversample
        target = max(counts.values())
        balanced = []
        for lbl, lbl_rows in by_label.items():
            if len(lbl_rows) >= target:
                balanced.extend(lbl_rows)
            else:
                # Dupliquer avec légère variation (shuffle interne)
                oversampled = lbl_rows.copy()
                while len(oversampled) < target:
                    oversampled.extend(random.sample(lbl_rows, min(len(lbl_rows), target - len(oversampled))))
                balanced.extend(oversampled[:target])

    random.shuffle(balanced)

    new_counts = Counter(r.get(label_col) for r in balanced)
    print(f"[Balance] Distribution après ({strategy}) :")
    for lbl in sorted(valid_labels):
        print(f"          {lbl:<16} {new_counts.get(lbl, 0):>5}")
    print(f"          TOTAL : {len(balanced)}")

    return balanced


# ─────────────────────────────────────────────────────────────────
#  TRAIN / VAL / TEST SPLIT
# ─────────────────────────────────────────────────────────────────

def split_train_val_test(rows: list[dict], label_col: str,
                         train_ratio: float = 0.70,
                         val_ratio:   float = 0.15) -> tuple[list, list, list]:
    """Split stratifié 70/15/15."""
    from collections import defaultdict
    by_label: dict[str, list] = defaultdict(list)
    for row in rows:
        lbl = row.get(label_col, "")
        by_label[lbl].append(row)

    train, val, test = [], [], []
    for lbl, lbl_rows in by_label.items():
        random.shuffle(lbl_rows)
        n = len(lbl_rows)
        n_train = int(n * train_ratio)
        n_val   = int(n * val_ratio)
        train.extend(lbl_rows[:n_train])
        val.extend(lbl_rows[n_train:n_train + n_val])
        test.extend(lbl_rows[n_train + n_val:])

    random.shuffle(train)
    random.shuffle(val)
    random.shuffle(test)
    return train, val, test


# ─────────────────────────────────────────────────────────────────
#  EXPORT
# ─────────────────────────────────────────────────────────────────

EXPORT_COLS = ["id", "source", "content_clean", "sentiment_label",
               "emotion_label", "business_label", "topic", "word_count"]


def export_split(rows: list[dict], path: str):
    """Exporte un split dans un CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Exported {len(rows):>5} rows → {os.path.basename(path)}")


# ─────────────────────────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────

def run_preprocessing(lang: str = "full", strategy: str = "oversample"):
    print(f"\n{'='*65}")
    print(f"  InsightFlow — Data Preprocessing Pipeline")
    print(f"  Lang: {lang} | Strategy: {strategy}")
    print(f"{'='*65}")

    report = {
        "lang": lang,
        "strategy": strategy,
        "processed_at": datetime.utcnow().isoformat(),
    }

    # ── 1. Charger + nettoyer ─────────────────────────────────
    rows, clean_stats = load_and_clean(lang)
    report["cleaning"] = clean_stats

    # ── 2. Dédupliquer ───────────────────────────────────────
    rows, n_dupes = deduplicate(rows)
    report["duplicates_removed"] = n_dupes

    # ── 3. SENTIMENT pipeline ─────────────────────────────────
    print(f"\n{'─'*40}")
    print(f"  SENTIMENT TASK")
    print(f"{'─'*40}")
    sent_rows = [r for r in rows if r.get("sentiment_label", "").strip() in SENTIMENT_LABELS]
    print(f"[Sentiment] {len(sent_rows)} rows avec sentiment_label valide")

    sent_balanced = balance_dataset(sent_rows, "sentiment_label", SENTIMENT_LABELS, strategy)
    s_train, s_val, s_test = split_train_val_test(sent_balanced, "sentiment_label")

    print(f"\n[Sentiment] Split 70/15/15 :")
    print(f"  Train : {len(s_train)} | Val : {len(s_val)} | Test : {len(s_test)}")

    export_split(s_train, os.path.join(DATASET_DIR, "clean_sentiment_train.csv"))
    export_split(s_val,   os.path.join(DATASET_DIR, "clean_sentiment_val.csv"))
    export_split(s_test,  os.path.join(DATASET_DIR, "clean_sentiment_test.csv"))

    report["sentiment"] = {
        "raw": len(sent_rows),
        "balanced": len(sent_balanced),
        "train": len(s_train),
        "val":   len(s_val),
        "test":  len(s_test),
        "distribution": dict(Counter(r["sentiment_label"] for r in sent_balanced)),
    }

    # ── 4. EMOTION pipeline ───────────────────────────────────
    print(f"\n{'─'*40}")
    print(f"  EMOTION TASK")
    print(f"{'─'*40}")
    emo_rows = [r for r in rows if r.get("emotion_label", "").strip() in EMOTION_LABELS]
    print(f"[Emotion] {len(emo_rows)} rows avec emotion_label valide")

    emo_balanced = balance_dataset(emo_rows, "emotion_label", EMOTION_LABELS, strategy)
    e_train, e_val, e_test = split_train_val_test(emo_balanced, "emotion_label")

    print(f"\n[Emotion] Split 70/15/15 :")
    print(f"  Train : {len(e_train)} | Val : {len(e_val)} | Test : {len(e_test)}")

    export_split(e_train, os.path.join(DATASET_DIR, "clean_emotion_train.csv"))
    export_split(e_val,   os.path.join(DATASET_DIR, "clean_emotion_val.csv"))
    export_split(e_test,  os.path.join(DATASET_DIR, "clean_emotion_test.csv"))

    report["emotion"] = {
        "raw": len(emo_rows),
        "balanced": len(emo_balanced),
        "train": len(e_train),
        "val":   len(e_val),
        "test":  len(e_test),
        "distribution": dict(Counter(r["emotion_label"] for r in emo_balanced)),
    }

    # ── 5. Rapport ────────────────────────────────────────────
    report_path = os.path.join(DATASET_DIR, "preprocessing_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*65}")
    print(f"  Preprocessing terminé ✓")
    print(f"  Rapport : {report_path}")
    print(f"{'='*65}")
    print(f"\n  Fichiers générés dans ml/dataset/ :")
    for fname in [
        "clean_sentiment_train.csv", "clean_sentiment_val.csv", "clean_sentiment_test.csv",
        "clean_emotion_train.csv",   "clean_emotion_val.csv",   "clean_emotion_test.csv",
    ]:
        fpath = os.path.join(DATASET_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                n = sum(1 for _ in f) - 1
            print(f"    {fname:<40} {n:>5} lignes")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang",     default="full",       choices=["en", "fr", "full"])
    parser.add_argument("--strategy", default="oversample", choices=["oversample", "undersample", "none"])
    args = parser.parse_args()
    run_preprocessing(lang=args.lang, strategy=args.strategy)
