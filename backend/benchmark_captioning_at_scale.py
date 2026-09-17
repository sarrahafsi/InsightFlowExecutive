"""
Benchmark captioning a plus grande echelle — reutilise Phase 0
============================================================================
Meme protocole que benchmark_captioning.py (memes 3 modeles, memes
metriques BLEU/ROUGE-L/METEOR/CLIP) mais sur un echantillon stratifie de
finetune_dataset/ (2499 images, 9 categories, references generees par
notre propre generateur) au lieu des 45 images Phase 0 (references
ecrites a la main).

Complementaire a Phase 0, pas un remplacement : echantillon plus grand
mais references non-humaines, meme style visuel partout (HTML/CSS). Voir
docstring pour les limites methodologiques.

Usage :
    python benchmark_captioning_at_scale.py --n_samples 400
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_captioning import LOADERS, INFERRERS, compute_nlp_metrics, load_clip, compute_clip_score  # noqa: E402

DATASET_DIR = Path(__file__).parent / "finetune_dataset"
CATEGORIES = ["error", "ticket", "chat", "dashboard", "chart", "document", "workflow", "table", "email"]


def sample_images(n_samples: int, seed: int = 42) -> list[dict]:
    rows = []
    with open(DATASET_DIR / "manifest.jsonl", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    per_cat = max(1, n_samples // len(CATEGORIES))
    rng = random.Random(seed)
    sample = []
    for cat in CATEGORIES:
        pool = by_cat.get(cat, [])
        rng.shuffle(pool)
        sample.extend(pool[:per_cat])
    return sample


def main(n_samples: int, out_dir: Path):
    out_dir.mkdir(exist_ok=True)
    sample = sample_images(n_samples)
    print(f"[INFO] {len(sample)} images echantillonnees ({len(sample)//len(CATEGORIES)}/categorie x {len(CATEGORIES)})")

    print("[INFO] chargement de CLIP...")
    clip_proc, clip_mdl = load_clip()

    all_rows = []
    summary_rows = []

    for model_name in LOADERS:
        print(f"\n{'='*65}\n  {model_name}\n{'='*65}")
        t0 = time.time()
        loaded = LOADERS[model_name]()
        print(f"  Chargement : {round(time.time()-t0, 2)}s")

        infer = INFERRERS[model_name]
        rows = []
        t0 = time.time()
        for i, row in enumerate(sample, 1):
            image_path = DATASET_DIR / row["file"]
            refs = row.get("captions") or [row["caption"]]
            try:
                hyp = infer(loaded, image_path)
                metrics = max((compute_nlp_metrics(hyp, r) for r in refs), key=lambda m: m["meteor"])
                clip = compute_clip_score(clip_proc, clip_mdl, image_path, hyp)
            except Exception as e:
                hyp, metrics, clip = f"[ERREUR: {e}]", {"bleu": 0, "rouge_l": 0, "meteor": 0}, 0.0
            rows.append({"model": model_name, "file": row["file"], "category": row["category"],
                         "hypothesis": hyp, "reference": refs[0], **metrics, "clip": clip})
            if i % 50 == 0:
                print(f"  [{i}/{len(sample)}]")
        elapsed = round(time.time() - t0, 1)
        print(f"  Inference totale : {elapsed}s ({round(elapsed/len(sample), 2)}s/image)")

        all_rows.extend(rows)
        n = len(rows)
        summary_rows.append({
            "model": model_name, "n": n,
            "bleu": round(sum(r["bleu"] for r in rows) / n, 4),
            "rouge_l": round(sum(r["rouge_l"] for r in rows) / n, 4),
            "meteor": round(sum(r["meteor"] for r in rows) / n, 4),
            "clip": round(sum(r["clip"] for r in rows) / n, 2),
            "inference_sec_per_image": round(elapsed / n, 2),
        })

        # libere la memoire avant le modele suivant
        del loaded
        import gc, torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ── par categorie (BLIP-base seulement, le plus rapide a lire) ──────────
    by_cat_model: dict[tuple, list] = defaultdict(list)
    for r in all_rows:
        by_cat_model[(r["model"], r["category"])].append(r["clip"])
    cat_rows = []
    for (model, cat), clips in sorted(by_cat_model.items()):
        cat_rows.append({"model": model, "category": cat, "n": len(clips),
                          "clip_mean": round(sum(clips) / len(clips), 2)})

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader(); w.writerows(summary_rows)
    with open(out_dir / "by_category.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cat_rows[0].keys()))
        w.writeheader(); w.writerows(cat_rows)
    with open(out_dir / "details.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader(); w.writerows(all_rows)

    print(f"\n{'='*75}\n{'Modele':<14}{'n':>5}{'BLEU':>8}{'ROUGE-L':>10}{'METEOR':>9}{'CLIP':>8}{'s/image':>10}")
    for s in summary_rows:
        print(f"{s['model']:<14}{s['n']:>5}{s['bleu']:>8}{s['rouge_l']:>10}{s['meteor']:>9}{s['clip']:>8}{s['inference_sec_per_image']:>10}")
    print("=" * 75)
    print(f"[OK] resultats dans {out_dir}/ (summary.csv, by_category.csv, details.csv)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_samples", type=int, default=400)
    parser.add_argument("--out_dir", type=str, default="benchmark_captioning_scale")
    args = parser.parse_args()
    main(args.n_samples, Path(args.out_dir))
