"""
Charts — Benchmark modeles d'embedding (MiniLM vs multilingue vs MPNet vs BGE)
================================================================================
Lit backend/benchmark_embeddings_results.csv, genere les graphiques du
rapport (meme convention que ml/benchmark.py, ml/generate_vectorstore_charts.py) :
matplotlib + seaborn, dpi=150, sauvegarde dans ml/charts/embeddings/.
"""

import csv
import os

CHARTS_DIR = os.path.join(os.path.dirname(__file__), "charts", "embeddings")
os.makedirs(CHARTS_DIR, exist_ok=True)

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "..", "backend", "benchmark_embeddings_results.csv")

COLORS = {
    "MiniLM-L6-v2 (actuel)":      "#95A5A6",
    "Multilingual-MiniLM-L12":    "#2ECC71",
    "MPNet-base-v2":              "#3498DB",
    "BGE-small-en-v1.5":          "#E74C3C",
}
ORDER = ["MiniLM-L6-v2 (actuel)", "Multilingual-MiniLM-L12", "MPNet-base-v2", "BGE-small-en-v1.5"]

# Libellés en clair + terme technique entre parentheses (pour le rapport PFE)
LBL_P1        = "Bonne réponse en 1er (P@1)"
LBL_P3        = "Bonne réponse dans le top 3 (P@3)"
LBL_MRR       = "Qualité du classement (MRR)"
LBL_P1_CROSS  = "1er résultat correct, langue différente (P@1 cross-lingue)"
LBL_MRR_CROSS = "Qualité classement, langue différente (MRR cross-lingue)"
LBL_STS_GAP   = "Écart sémantique paraphrase/non-lié (STS gap)"
LBL_SPEARMAN  = "Fiabilité du classement vs jugement humain (Spearman ρ)"
LBL_THROUGHPUT = "Vitesse de traitement — phrases/sec (débit d'encodage)"
LBL_DISK       = "Poids du modèle — Mo (taille disque)"


def load_results():
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ["dim", "disk_mb", "load_sec", "throughput_docs_per_sec", "p_at_1", "p_at_3", "mrr",
                  "p_at_1_cross_lingual", "mrr_cross_lingual", "sts_sim_paraphrase", "sts_sim_related",
                  "sts_sim_unrelated", "sts_gap", "sts_spearman_rho"]:
            r[k] = float(r[k])
    by_name = {r["model"]: r for r in rows}
    return [by_name[m] for m in ORDER]


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    import seaborn as sns

    sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
    rows = load_results()
    names = [r["model"] for r in rows]
    colors = [COLORS[n] for n in names]
    x = np.arange(len(names))

    # ── 1. Retrieval global : P@1 / P@3 / MRR ────────────────────────
    fig, ax = plt.subplots(figsize=(11, 6))
    w = 0.25
    ax.bar(x - w, [r["p_at_1"] for r in rows], w, label=LBL_P1, color=[c + "cc" for c in colors], edgecolor="white")
    ax.bar(x,     [r["p_at_3"] for r in rows], w, label=LBL_P3, color=colors, edgecolor="white")
    ax.bar(x + w, [r["mrr"]    for r in rows], w, label=LBL_MRR, color=[c + "80" for c in colors], edgecolor="white")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=12, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score (0 = jamais bon, 1 = toujours bon)")
    ax.set_title("Qualité de recherche (retrieval) — toutes requêtes",
                  fontsize=14, fontweight="bold")
    ax.legend(fontsize=9)
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "1_retrieval_overall.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 2. Cross-lingual : le constat principal ──────────────────────
    fig, ax = plt.subplots(figsize=(10, 6))
    w = 0.35
    bars1 = ax.bar(x - w/2, [r["p_at_1_cross_lingual"] for r in rows], w,
                   label=LBL_P1_CROSS, color=[c + "cc" for c in colors], edgecolor="white")
    bars2 = ax.bar(x + w/2, [r["mrr_cross_lingual"] for r in rows], w,
                   label=LBL_MRR_CROSS, color=colors, edgecolor="white")
    for bar in list(bars1) + list(bars2):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{bar.get_height():.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=12, ha="right")
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score (0 = jamais bon, 1 = toujours bon)")
    ax.set_title("Recherche cross-lingue (question en FR sur un doc EN, ou inverse)\n"
                  "Seul le modèle multilingue retrouve les documents dans l'autre langue",
                  fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, loc="upper right")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "2_cross_lingual.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 3. Discrimination semantique : gap + spearman ────────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    axes[0].bar(x, [r["sts_gap"] for r in rows], color=colors, edgecolor="white")
    axes[0].set_xticks(x); axes[0].set_xticklabels(names, rotation=12, ha="right")
    axes[0].set_title(f"{LBL_STS_GAP}\n(plus haut = distingue mieux les phrases proches des phrases différentes)",
                       fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Écart de similarité (0 à 1)")

    axes[1].bar(x, [r["sts_spearman_rho"] for r in rows], color=colors, edgecolor="white")
    axes[1].set_xticks(x); axes[1].set_xticklabels(names, rotation=12, ha="right")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_title(f"{LBL_SPEARMAN}\n(1 = classe les phrases comme le ferait une personne)",
                       fontsize=11, fontweight="bold")
    axes[1].set_ylabel("Accord avec le jugement humain (0 à 1)")
    fig.suptitle("Discrimination sémantique (paires de phrases : paraphrase / même domaine / sans rapport)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "3_semantic_discrimination.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 4. Performance : debit vs taille disque ──────────────────────
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for r, c in zip(rows, colors):
        ax.scatter(r["throughput_docs_per_sec"], r["disk_mb"], s=280, color=c,
                   zorder=5, edgecolors="white", linewidth=1.5)
        ax.annotate(f"{r['model']}\n(dim={int(r['dim'])})", (r["throughput_docs_per_sec"], r["disk_mb"]),
                    textcoords="offset points", xytext=(10, 6), fontsize=9)
    ax.set_xlabel(f"{LBL_THROUGHPUT}  →  plus à droite = plus rapide")
    ax.set_ylabel(f"{LBL_DISK}  ↓  plus bas = plus léger")
    ax.set_title("Coût pratique : vitesse vs poids du modèle", fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "4_performance_tradeoff.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 0. Dashboard resume ───────────────────────────────────────────
    fig = plt.figure(figsize=(16, 11))
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.3)

    ax1 = fig.add_subplot(gs[0, 0])
    w = 0.25
    ax1.bar(x - w, [r["p_at_1"] for r in rows], w, label="1er résultat correct (P@1)", color=[c + "cc" for c in colors])
    ax1.bar(x,     [r["p_at_3"] for r in rows], w, label="Bon résultat dans le top 3 (P@3)", color=colors)
    ax1.bar(x + w, [r["mrr"]    for r in rows], w, label="Qualité du classement (MRR)", color=[c + "80" for c in colors])
    ax1.set_xticks(x); ax1.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
    ax1.set_ylim(0, 1.05); ax1.set_title("Qualité de recherche — toutes requêtes", fontweight="bold")
    ax1.legend(fontsize=7)

    ax2 = fig.add_subplot(gs[0, 1])
    bars1 = ax2.bar(x - w/2, [r["p_at_1_cross_lingual"] for r in rows], w,
                     label="1er résultat correct (P@1 cross)", color=[c + "cc" for c in colors])
    bars2 = ax2.bar(x + w/2, [r["mrr_cross_lingual"] for r in rows], w,
                     label="Qualité classement (MRR cross)", color=colors)
    ax2.set_xticks(x); ax2.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
    ax2.set_ylim(0, 1.15); ax2.set_title("Recherche langue différente — constat clé", fontweight="bold")
    ax2.legend(fontsize=7)

    ax3 = fig.add_subplot(gs[1, 0])
    ax3.bar(x, [r["sts_gap"] for r in rows], color=colors)
    ax3.set_xticks(x); ax3.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
    ax3.set_title("Écart sémantique — phrases proches vs différentes (STS gap)", fontweight="bold", fontsize=10)

    ax4 = fig.add_subplot(gs[1, 1])
    for r, c in zip(rows, colors):
        ax4.scatter(r["throughput_docs_per_sec"], r["disk_mb"], s=200, color=c, edgecolors="white", linewidth=1.5)
    ax4.set_xlabel("Vitesse — phrases/sec (débit)"); ax4.set_ylabel("Poids — Mo (taille disque)")
    ax4.set_title("Vitesse vs poids du modèle", fontweight="bold")

    handles = [plt.Rectangle((0,0),1,1, color=COLORS[n]) for n in names]
    fig.legend(handles, names, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.03), fontsize=10)
    fig.suptitle("Benchmark Modèles d'Embedding — InsightFlow Executive",
                 fontsize=16, fontweight="bold", y=1.08)
    path = os.path.join(CHARTS_DIR, "0_benchmark_dashboard.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    print(f"\n[OK] Tous les graphiques sauvegardes dans : {CHARTS_DIR}")


if __name__ == "__main__":
    main()
