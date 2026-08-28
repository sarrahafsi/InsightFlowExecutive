"""
Évaluation BLIP-base vs BLIP fine-tuné (LoRA) — InsightFlow Executive PFE
============================================================================
Réutilise EXACTEMENT les mêmes métriques que le benchmark Phase 0
(compute_nlp_metrics, compute_clip_score de benchmark_captioning.py) pour
que les chiffres soient directement comparables au tableau déjà dans
BENCHMARK_RESULTS.md.

Deux jeux de test, gardés séparés :
1. Les 45 images du benchmark Phase 0 (benchmark_images/) — jamais vues à
   l'entraînement, référence directe au chiffre déjà publié (BLIP-base
   pré-entraîné : METEOR 0.194 / ROUGE-L 0.243 / CLIP 28.5, cf.
   BENCHMARK_RESULTS.md). Sert aussi de test de non-régression / généralisation
   hors du dataset synthétique de fine-tuning.
2. Le split "test" de finetune_dataset/ (jamais vu à l'entraînement non plus).

Génère aussi un échantillon pour évaluation humaine (comme Phase 0), prêt à
noter manuellement.

Colab quickstart :
    !python evaluate_blip_finetune.py --adapter_dir blip_insightflow_lora/best \
        --data_dir finetune_dataset --phase0_dir benchmark_images
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from peft import PeftModel

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_captioning import REFERENCES, compute_nlp_metrics, compute_clip_score, load_clip  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_models(adapter_dir: str):
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    base_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base").to(DEVICE)
    base_model.eval()

    ft_base = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    ft_model = PeftModel.from_pretrained(ft_base, adapter_dir).to(DEVICE)
    ft_model.eval()

    return processor, base_model, ft_model


@torch.no_grad()
def infer(model, processor, image_path: Path) -> str:
    image = Image.open(image_path).convert("RGB")
    inputs = processor(image, return_tensors="pt").to(DEVICE)
    out = model.generate(**inputs, max_new_tokens=50, no_repeat_ngram_size=3)
    return processor.decode(out[0], skip_special_tokens=True).strip()


def eval_on_phase0(processor, model, phase0_dir: Path, clip_proc, clip_mdl, limit: int | None = None) -> list[dict]:
    rows = []
    items = list(REFERENCES.items())[:limit] if limit else REFERENCES.items()
    for name, ref in items:
        img_path = phase0_dir / f"{name}.png"
        if not img_path.exists():
            continue
        hyp = infer(model, processor, img_path)
        metrics = compute_nlp_metrics(hyp, ref)
        clip = compute_clip_score(clip_proc, clip_mdl, img_path, hyp)
        rows.append({"image": name, "hypothesis": hyp, "reference": ref, **metrics, "clip": clip})
    return rows


def eval_on_finetune_test(processor, model, data_dir: Path, clip_proc, clip_mdl, limit: int) -> list[dict]:
    manifest_path = data_dir / "manifest.jsonl"
    test_rows = []
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["split"] == "test":
                test_rows.append(row)
    random.Random(42).shuffle(test_rows)
    test_rows = test_rows[:limit]

    rows = []
    for row in test_rows:
        img_path = data_dir / row["file"]
        hyp = infer(model, processor, img_path)
        refs = row.get("captions") or [row["caption"]]
        best = max((compute_nlp_metrics(hyp, r) for r in refs), key=lambda m: m["meteor"])
        clip = compute_clip_score(clip_proc, clip_mdl, img_path, hyp)
        rows.append({"image": row["file"], "hypothesis": hyp, "reference": refs[0],
                      "category": row["category"], **best, "clip": clip})
    return rows


def summarize(rows: list[dict], label: str) -> dict:
    if not rows:
        return {"label": label, "n": 0}
    n = len(rows)
    return {
        "label": label, "n": n,
        "bleu": round(sum(r["bleu"] for r in rows) / n, 4),
        "rouge_l": round(sum(r["rouge_l"] for r in rows) / n, 4),
        "meteor": round(sum(r["meteor"] for r in rows) / n, 4),
        "clip": round(sum(r["clip"] for r in rows) / n, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter_dir", type=str, required=True)
    parser.add_argument("--data_dir", type=str, default="finetune_dataset")
    parser.add_argument("--phase0_dir", type=str, default="benchmark_images")
    parser.add_argument("--test_limit", type=int, default=150)
    parser.add_argument("--phase0_limit", type=int, default=None)
    parser.add_argument("--human_eval_sample", type=int, default=30)
    parser.add_argument("--out_dir", type=str, default="eval_results")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[INFO] chargement des modeles...")
    processor, base_model, ft_model = load_models(args.adapter_dir)
    print("[INFO] chargement de CLIP...")
    clip_proc, clip_mdl = load_clip()

    phase0_dir = Path(args.phase0_dir)
    data_dir = Path(args.data_dir)

    summaries = []
    all_rows = {}
    for model_name, model in (("BLIP-base", base_model), ("BLIP-finetuned", ft_model)):
        print(f"\n[INFO] evaluation {model_name} sur Phase 0 (45 images)...")
        rows_p0 = eval_on_phase0(processor, model, phase0_dir, clip_proc, clip_mdl, args.phase0_limit)
        summaries.append(summarize(rows_p0, f"{model_name} / Phase0"))
        all_rows[f"{model_name}_phase0"] = rows_p0

        print(f"[INFO] evaluation {model_name} sur test set finetune ({args.test_limit} images)...")
        rows_test = eval_on_finetune_test(processor, model, data_dir, clip_proc, clip_mdl, args.test_limit)
        summaries.append(summarize(rows_test, f"{model_name} / FinetuneTest"))
        all_rows[f"{model_name}_test"] = rows_test

    with open(out_dir / "summary.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "n", "bleu", "rouge_l", "meteor", "clip"])
        writer.writeheader()
        writer.writerows(summaries)

    for key, rows in all_rows.items():
        with open(out_dir / f"detail_{key}.csv", "w", encoding="utf-8", newline="") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

    # Échantillon pour évaluation humaine (base vs fine-tuné, côte à côte)
    p0_names = list(REFERENCES.keys())
    sample_names = random.Random(42).sample(p0_names, min(args.human_eval_sample, len(p0_names)))
    human_rows = []
    for name in sample_names:
        base_row = next((r for r in all_rows["BLIP-base_phase0"] if r["image"] == name), None)
        ft_row = next((r for r in all_rows["BLIP-finetuned_phase0"] if r["image"] == name), None)
        if base_row and ft_row:
            human_rows.append({
                "image": name, "reference": base_row["reference"],
                "base_caption": base_row["hypothesis"], "base_score_1to5": "",
                "finetuned_caption": ft_row["hypothesis"], "finetuned_score_1to5": "",
            })
    with open(out_dir / "human_eval_sample.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(human_rows[0].keys()) if human_rows else [])
        writer.writeheader()
        writer.writerows(human_rows)

    print("\n" + "=" * 80)
    print(f"{'Model / Set':<28}{'n':>5}{'BLEU':>8}{'ROUGE-L':>10}{'METEOR':>9}{'CLIP':>8}")
    for s in summaries:
        print(f"{s['label']:<28}{s['n']:>5}{s.get('bleu', 0):>8}{s.get('rouge_l', 0):>10}"
              f"{s.get('meteor', 0):>9}{s.get('clip', 0):>8}")
    print("=" * 80)
    print(f"[OK] resultats dans {out_dir}/ (summary.csv, detail_*.csv, human_eval_sample.csv)")


if __name__ == "__main__":
    main()
