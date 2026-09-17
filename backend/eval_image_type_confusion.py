"""
Matrice de confusion — classification image_type (fusion LLM)
============================================================================
Compare la categorie predite par le pipeline (structured["image_type"],
sortie de la fusion LLM dans image_processor.py) a la vraie categorie
connue du dataset (finetune_dataset/manifest.jsonl, champ "category") —
sur des images du split "test", jamais vues a la construction du dataset
ni utilisees ailleurs dans ce projet.

Usage :
    python eval_image_type_confusion.py --per_category 8
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from intelligence.nlp.image_processor import process_image_async

DATASET_DIR = Path(__file__).parent / "finetune_dataset"
CATEGORIES = ["error", "ticket", "chat", "dashboard", "chart", "document", "workflow", "table", "email"]


def load_test_sample(per_category: int, seed: int = 42) -> list[dict]:
    rows = []
    with open(DATASET_DIR / "manifest.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["split"] == "test":
                rows.append(row)

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    rng = random.Random(seed)
    sample = []
    for cat in CATEGORIES:
        pool = by_cat.get(cat, [])
        rng.shuffle(pool)
        sample.extend(pool[:per_category])
    return sample


async def run_eval(per_category: int, out_dir: Path):
    sample = load_test_sample(per_category)
    print(f"[INFO] {len(sample)} images echantillonnees ({per_category}/categorie x {len(CATEGORIES)} categories)")

    details = []
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for i, row in enumerate(sample, 1):
        image_path = DATASET_DIR / row["file"]
        true_cat = row["category"]
        result = await process_image_async(image_path)
        predicted = (result.get("structured") or {}).get("image_type", "other") or "other"
        predicted = predicted.strip().lower()

        matrix[true_cat][predicted] += 1
        details.append({
            "file": row["file"], "true_category": true_cat, "predicted_image_type": predicted,
            "correct": true_cat == predicted,
        })
        print(f"  [{i}/{len(sample)}] {row['file']:35s} vrai={true_cat:10s} predit={predicted:10s} "
              f"{'OK' if true_cat == predicted else 'X'}")

    return matrix, details


def print_matrix(matrix: dict[str, dict[str, int]], out_dir: Path):
    predicted_cols = sorted(set(CATEGORIES) | {p for row in matrix.values() for p in row} | {"other"})

    row_label = "vrai / predit"
    header = f"{row_label:<14}" + "".join(f"{c[:8]:>10}" for c in predicted_cols)
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    total_correct, total = 0, 0
    per_class_stats = []
    for true_cat in CATEGORIES:
        row = matrix.get(true_cat, {})
        row_total = sum(row.values())
        line = f"{true_cat:<14}" + "".join(f"{row.get(c, 0):>10}" for c in predicted_cols)
        print(line)
        correct = row.get(true_cat, 0)
        total_correct += correct
        total += row_total
        recall = correct / row_total if row_total else 0.0
        per_class_stats.append((true_cat, correct, row_total, recall))

    print("=" * len(header))
    accuracy = total_correct / total if total else 0.0
    print(f"\nAccuracy globale : {total_correct}/{total} = {accuracy*100:.1f}%\n")

    print(f"{'categorie':<14}{'rappel (recall)':>18}")
    for cat, correct, row_total, recall in per_class_stats:
        print(f"{cat:<14}{correct}/{row_total:<5} = {recall*100:>5.1f}%")

    # CSV export
    with open(out_dir / "confusion_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["vrai \\ predit"] + predicted_cols)
        for true_cat in CATEGORIES:
            row = matrix.get(true_cat, {})
            writer.writerow([true_cat] + [row.get(c, 0) for c in predicted_cols])

    return accuracy


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--per_category", type=int, default=8)
    parser.add_argument("--out_dir", type=str, default="eval_image_type")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    matrix, details = asyncio.run(run_eval(args.per_category, out_dir))
    accuracy = print_matrix(matrix, out_dir)

    with open(out_dir / "details.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "true_category", "predicted_image_type", "correct"])
        writer.writeheader()
        writer.writerows(details)

    print(f"\n[OK] resultats dans {out_dir}/ (confusion_matrix.csv, details.csv)")
