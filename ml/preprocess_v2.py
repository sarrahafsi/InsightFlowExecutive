"""
InsightFlow — Preprocessing v2 (fix fuite de données)
======================================================
Bug corrigé vs preprocess.py : l'oversampling (balance_dataset) tournait
AVANT le split train/val/test, donc des copies dupliquées du même texte
pouvaient atterrir à la fois en train et en test (mémorisation, pas
généralisation — score gonflé artificiellement, cf. session du 03/09/2026).

Ici : split D'ABORD (sur les données dédupliquées, non équilibrées) →
val/test restent 100% propres, jamais dupliqués → puis oversampling
UNIQUEMENT sur la partition train, pour l'apprentissage.

Usage (Colab recommandé — CPU seul seul ~5-10h, GPU ~10-20 min) :
    python ml/preprocess_v2.py
    python ml/finetune.py --task sentiment --model xlm --lang full
    python ml/finetune.py --task emotion --lang full
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from preprocess import (
    DATASET_DIR, SENTIMENT_LABELS, EMOTION_LABELS,
    load_and_clean, deduplicate, balance_dataset, split_train_val_test, export_split,
)


def run_preprocessing_v2(lang: str = "full", strategy: str = "oversample"):
    print(f"\n{'='*65}")
    print(f"  InsightFlow — Preprocessing v2 (split AVANT oversampling)")
    print(f"  Lang: {lang} | Strategy train only: {strategy}")
    print(f"{'='*65}")

    # ── 1. Charger + nettoyer + dédupliquer (identique à v1) ──────
    rows, _ = load_and_clean(lang)
    rows, n_dupes = deduplicate(rows)
    print(f"[Preprocess] {len(rows)} rows après nettoyage + dédup ({n_dupes} doublons supprimés)")

    for task, label_col, valid_labels in [
        ("sentiment", "sentiment_label", SENTIMENT_LABELS),
        ("emotion",   "emotion_label",   EMOTION_LABELS),
    ]:
        print(f"\n{'─'*40}\n  {task.upper()} TASK\n{'─'*40}")
        task_rows = [r for r in rows if r.get(label_col, "").strip() in valid_labels]
        print(f"[{task}] {len(task_rows)} rows avec {label_col} valide")

        # ── 2. Split D'ABORD, sur données NON équilibrées ──────────
        train, val, test = split_train_val_test(task_rows, label_col)
        print(f"[{task}] Split 70/15/15 (avant balance) : train={len(train)} val={len(val)} test={len(test)}")

        # ── 3. Oversample UNIQUEMENT le train — val/test restent propres ──
        train_balanced = balance_dataset(train, label_col, valid_labels, strategy)

        print(f"[{task}] Après oversampling train seul : train={len(train_balanced)} val={len(val)} test={len(test)}")
        print(f"[{task}] val/test = 0 duplicata garanti (jamais passés dans balance_dataset)")

        export_split(train_balanced, os.path.join(DATASET_DIR, f"clean_{task}_train.csv"))
        export_split(val,            os.path.join(DATASET_DIR, f"clean_{task}_val.csv"))
        export_split(test,           os.path.join(DATASET_DIR, f"clean_{task}_test.csv"))

    print(f"\n{'='*65}\n  Preprocessing v2 terminé — clean_*.csv régénérés (fuite corrigée)\n{'='*65}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="full", choices=["en", "fr", "full"])
    parser.add_argument("--strategy", default="oversample", choices=["oversample", "undersample", "none"])
    args = parser.parse_args()
    run_preprocessing_v2(lang=args.lang, strategy=args.strategy)
