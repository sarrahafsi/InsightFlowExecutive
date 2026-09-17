"""
Évaluation humaine des captions générées par le benchmark.
Lit benchmark_results.csv, demande une note 1-5 pour chaque caption,
sauvegarde dans benchmark_results_human.csv,
puis calcule la corrélation avec les métriques automatiques.

Usage : python benchmark_human_eval.py
"""

import csv
import os
from pathlib import Path
from collections import defaultdict

RESULTS_FILE      = Path(__file__).parent / "benchmark_results.csv"
HUMAN_RESULTS     = Path(__file__).parent / "benchmark_results_human.csv"
CORRELATION_FILE  = Path(__file__).parent / "benchmark_correlation.csv"

SCORE_LABELS = {
    1: "Très mauvais — aucun rapport avec l'image",
    2: "Mauvais     — vaguement lié",
    3: "Correct     — partiellement exact",
    4: "Bon         — description précise",
    5: "Excellent   — description complète et précise",
}


# ── Chargement des résultats existants ───────────────────────────────────────
def load_results() -> list:
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── Sauvegarde avec human_score ──────────────────────────────────────────────
def save_human_results(rows: list):
    fields = [
        "model", "image", "caption", "reference",
        "load_sec", "inference_sec", "total_first_image_sec",
        "bleu", "rouge_l", "meteor", "clip_score",
        "human_score",
        "approx_size_mb", "device", "error",
    ]
    with open(HUMAN_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[✓] Sauvegardé : {HUMAN_RESULTS}")


# ── Session d'évaluation interactive ─────────────────────────────────────────
def run_human_eval(rows: list) -> list:
    # Grouper par image pour voir les 3 modèles ensemble
    by_image = defaultdict(list)
    for r in rows:
        by_image[r["image"]].append(r)

    total_images = len(by_image)
    done = 0

    print("\n" + "="*65)
    print("  ÉVALUATION HUMAINE — Note chaque caption de 1 à 5")
    print("  Entrée vide = passer (score = -1)")
    print("  Ctrl+C = arrêter et sauvegarder")
    print("="*65)
    print("\nÉchelle de notation :")
    for k, v in SCORE_LABELS.items():
        print(f"  {k} = {v}")

    try:
        for img_name, img_rows in by_image.items():
            done += 1
            print(f"\n{'─'*65}")
            print(f"  Image [{done}/{total_images}] : {img_name}")
            print(f"  Référence : {img_rows[0].get('reference', 'N/A')}")
            print(f"{'─'*65}")

            for row in img_rows:
                model   = row["model"]
                caption = row["caption"] or "(caption vide)"

                print(f"\n  [{model}] → \"{caption}\"")

                while True:
                    raw = input("  Note (1-5, Entrée=passer) : ").strip()
                    if raw == "":
                        row["human_score"] = -1
                        break
                    if raw in ("1", "2", "3", "4", "5"):
                        row["human_score"] = int(raw)
                        break
                    print("  ⚠ Saisis un chiffre entre 1 et 5.")

    except KeyboardInterrupt:
        print("\n\n[i] Interruption — sauvegarde des scores déjà saisis...")
        for row in rows:
            if "human_score" not in row:
                row["human_score"] = -1

    # S'assurer que toutes les lignes ont un human_score
    for row in rows:
        if "human_score" not in row:
            row["human_score"] = -1

    return rows


# ── Calcul de corrélation ─────────────────────────────────────────────────────
def spearman_r(x: list, y: list) -> float:
    """Corrélation de Spearman manuelle (sans scipy)."""
    n = len(x)
    if n < 2:
        return 0.0

    def ranks(lst):
        sorted_idx = sorted(range(n), key=lambda i: lst[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and lst[sorted_idx[j]] == lst[sorted_idx[j+1]]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[sorted_idx[k]] = avg_rank
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num   = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = sum((rx[i] - mean_rx) ** 2 for i in range(n)) ** 0.5
    den_y = sum((ry[i] - mean_ry) ** 2 for i in range(n)) ** 0.5
    return round(num / (den_x * den_y + 1e-9), 4)


def compute_correlations(rows: list):
    # Ne garder que les lignes avec human_score valide
    valid = [r for r in rows if int(r.get("human_score", -1)) > 0
             and float(r.get("bleu", -1)) >= 0]

    if len(valid) < 5:
        print("\n[⚠] Pas assez de scores humains pour calculer les corrélations.")
        return

    human  = [int(r["human_score"])      for r in valid]
    bleu   = [float(r["bleu"])           for r in valid]
    rouge  = [float(r["rouge_l"])        for r in valid]
    meteor = [float(r["meteor"])         for r in valid]
    clip   = [float(r["clip_score"])     for r in valid]

    corr = {
        "BLEU    ↔ Human": spearman_r(bleu,   human),
        "ROUGE-L ↔ Human": spearman_r(rouge,  human),
        "METEOR  ↔ Human": spearman_r(meteor, human),
        "CLIP    ↔ Human": spearman_r(clip,   human),
    }

    print(f"\n{'='*55}")
    print("  CORRÉLATION DE SPEARMAN (métrique ↔ score humain)")
    print(f"{'='*55}")
    print(f"  {'Paire':<25} {'ρ':>8}   Interprétation")
    print(f"{'─'*55}")
    for pair, rho in corr.items():
        if abs(rho) >= 0.6:
            label = "Forte corrélation ✓"
        elif abs(rho) >= 0.4:
            label = "Corrélation modérée"
        elif abs(rho) >= 0.2:
            label = "Corrélation faible"
        else:
            label = "Pas de corrélation"
        print(f"  {pair:<25} {rho:>8.4f}   {label}")
    print(f"{'='*55}")

    # Score humain moyen par modèle
    model_scores = defaultdict(list)
    for r in valid:
        model_scores[r["model"]].append(int(r["human_score"]))

    print(f"\n  Score humain moyen par modèle :")
    print(f"{'─'*35}")
    ranked = sorted(model_scores.items(), key=lambda x: -sum(x[1])/len(x[1]))
    for model, scores in ranked:
        avg = round(sum(scores) / len(scores), 2)
        bar = "█" * int(avg * 4)
        print(f"  {model:<12}  {avg:>4.2f}/5  {bar}")
    print(f"{'─'*35}")
    print(f"\n  → Modèle gagnant selon l'évaluation humaine : {ranked[0][0]}")

    # Sauvegarder les corrélations
    with open(CORRELATION_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pair", "spearman_rho", "interpretation"])
        for pair, rho in corr.items():
            if abs(rho) >= 0.6:    label = "forte"
            elif abs(rho) >= 0.4:  label = "moderee"
            elif abs(rho) >= 0.2:  label = "faible"
            else:                   label = "nulle"
            w.writerow([pair.strip(), rho, label])
        w.writerow([])
        w.writerow(["model", "avg_human_score"])
        for model, scores in ranked:
            w.writerow([model, round(sum(scores)/len(scores), 2)])

    print(f"\n[✓] Corrélations sauvegardées : {CORRELATION_FILE}")
    print("""
  Comment utiliser dans le rapport PFE :
  ─────────────────────────────────────
  Si ρ ≥ 0.4 pour CLIP ou METEOR → écrire :
  "La corrélation de Spearman (ρ=X.XX) entre [métrique] et
   l'évaluation humaine confirme la validité des métriques
   automatiques pour ce benchmark."

  Si ρ < 0.2 pour BLEU → écrire :
  "BLEU présente une faible corrélation avec le jugement humain
   sur les images business, ce qui est cohérent avec les limites
   connues de cette métrique pour les descriptions courtes."
    """)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not RESULTS_FILE.exists():
        print(f"[✗] Fichier introuvable : {RESULTS_FILE}")
        print("    Lance d'abord : python benchmark_captioning.py")
        exit(1)

    rows = load_results()
    print(f"[✓] {len(rows)} captions chargées ({len(set(r['image'] for r in rows))} images × "
          f"{len(set(r['model'] for r in rows))} modèles)")

    # Reprendre une session interrompue si human_results existe déjà
    if HUMAN_RESULTS.exists():
        print(f"\n[i] Session précédente trouvée : {HUMAN_RESULTS}")
        rep = input("    Reprendre là où tu t'es arrêtée ? (o/n) : ").strip().lower()
        if rep == "o":
            with open(HUMAN_RESULTS, encoding="utf-8") as f:
                saved = {(r["model"], r["image"]): r for r in csv.DictReader(f)}
            for row in rows:
                key = (row["model"], row["image"])
                if key in saved and saved[key].get("human_score"):
                    row["human_score"] = saved[key]["human_score"]

    rows = run_human_eval(rows)
    save_human_results(rows)
    compute_correlations(rows)
