"""
Charts — Benchmark Vector Store (ChromaDB vs FAISS vs NumPy)
================================================================
Lit les CSV produits par backend/benchmark_vectorstore.py et genere les
graphiques du rapport, meme convention que les autres benchmarks du projet
(ml/benchmark.py, ml/charts/vision/...) : matplotlib + seaborn, dpi=150,
sauvegarde dans ml/charts/vectorstore/.
"""

import csv
import os

CHARTS_DIR = os.path.join(os.path.dirname(__file__), "charts", "vectorstore")
os.makedirs(CHARTS_DIR, exist_ok=True)

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "..", "backend", "benchmark_vectorstore_results.csv")
FILTER_CSV  = os.path.join(os.path.dirname(__file__), "..", "backend", "benchmark_vectorstore_filter_results.csv")

COLORS = {
    "NumPy-BruteForce":     "#95A5A6",
    "FAISS-FlatIP(exact)":  "#3498DB",
    "FAISS-HNSW(ANN)":      "#E74C3C",
    "ChromaDB(HNSW)":       "#2ECC71",
}
ORDER = ["NumPy-BruteForce", "FAISS-FlatIP(exact)", "FAISS-HNSW(ANN)", "ChromaDB(HNSW)"]


def load_results():
    rows = []
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["scale"]          = int(r["scale"])
            r["index_time_sec"] = float(r["index_time_sec"])
            r["query_avg_ms"]   = float(r["query_avg_ms"])
            r["query_p95_ms"]   = float(r["query_p95_ms"])
            r["recall_at_10"]   = float(r["recall_at_10"])
            r["disk_mb"]        = float(r["disk_mb"])
            r["ram_delta_mb"]   = float(r["ram_delta_mb"])
            rows.append(r)
    return rows


def load_filter_results():
    rows = []
    with open(FILTER_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["scale"] = int(r["scale"])
            r["chromadb_native_filter_avg_ms"] = float(r["chromadb_native_filter_avg_ms"])
            r["manual_numpy_filter_avg_ms"]    = float(r["manual_numpy_filter_avg_ms"])
            rows.append(r)
    return rows


def by_backend(rows, backend, field):
    pts = [(r["scale"], r[field]) for r in rows if r["backend"] == backend]
    pts.sort()
    return [p[0] for p in pts], [p[1] for p in pts]


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import seaborn as sns

    sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
    rows = load_results()
    frows = load_filter_results()
    scales = sorted(set(r["scale"] for r in rows))

    # ── 1. Recall@10 vs echelle — le constat principal ─────────────
    fig, ax = plt.subplots(figsize=(9, 6))
    for backend in ORDER:
        x, y = by_backend(rows, backend, "recall_at_10")
        ax.plot(x, y, marker="o", linewidth=2.5, markersize=8,
                label=backend, color=COLORS[backend])
    ax.set_xscale("log")
    ax.set_xticks(scales)
    ax.set_xticklabels([str(s) for s in scales])
    ax.set_ylim(0.65, 1.03)
    ax.set_xlabel("Taille du corpus (nombre de messages)")
    ax.set_ylabel("Recall@10 (1.0 = parfait)")
    ax.set_title("Précision de la recherche selon la taille du corpus\n"
                  "FAISS-HNSW se dégrade, ChromaDB reste stable",
                  fontsize=14, fontweight="bold")
    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.4)
    ax.legend(loc="lower left")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "1_recall_vs_scale.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 2. Latence de requete (avg) vs echelle ──────────────────────
    fig, ax = plt.subplots(figsize=(9, 6))
    for backend in ORDER:
        x, y = by_backend(rows, backend, "query_avg_ms")
        ax.plot(x, y, marker="o", linewidth=2.5, markersize=8,
                label=backend, color=COLORS[backend])
    ax.set_xscale("log")
    ax.set_xticks(scales)
    ax.set_xticklabels([str(s) for s in scales])
    ax.set_xlabel("Taille du corpus (nombre de messages)")
    ax.set_ylabel("Latence moyenne par requête (ms)")
    ax.set_title("Latence de recherche (top-10) selon la taille du corpus",
                  fontsize=14, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "2_query_latency_vs_scale.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 3. Temps d'indexation vs echelle (log) ──────────────────────
    fig, ax = plt.subplots(figsize=(9, 6))
    for backend in ORDER:
        x, y = by_backend(rows, backend, "index_time_sec")
        ax.plot(x, y, marker="o", linewidth=2.5, markersize=8,
                label=backend, color=COLORS[backend])
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(scales)
    ax.set_xticklabels([str(s) for s in scales])
    ax.set_xlabel("Taille du corpus (nombre de messages)")
    ax.set_ylabel("Temps d'indexation (secondes, échelle log)")
    ax.set_title("Coût d'indexation selon la taille du corpus\n"
                  "ChromaDB paie sa persistance disque",
                  fontsize=14, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "3_index_time_vs_scale.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 4. Filtrage par metadonnees : natif vs fait maison ──────────
    fig, ax = plt.subplots(figsize=(9, 6))
    x = list(range(len(frows)))
    w = 0.35
    ax.bar([i - w/2 for i in x], [r["chromadb_native_filter_avg_ms"] for r in frows], w,
           label="ChromaDB (filtre natif)", color=COLORS["ChromaDB(HNSW)"], edgecolor="white")
    ax.bar([i + w/2 for i in x], [r["manual_numpy_filter_avg_ms"] for r in frows], w,
           label="Masque NumPy (fait maison)", color=COLORS["NumPy-BruteForce"], edgecolor="white")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([str(r["scale"]) for r in frows])
    ax.set_xlabel("Taille du corpus (nombre de messages)")
    ax.set_ylabel("Latence filtrage org_id (ms, échelle log)")
    ax.set_title("Filtrage multi-tenant par entreprise (org_id)\n"
                  "ChromaDB : nativement inclus, pas de code à maintenir",
                  fontsize=14, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "4_metadata_filtering.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 0. Dashboard resume (4 panneaux) ────────────────────────────
    fig = plt.figure(figsize=(16, 11))
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.28)

    ax1 = fig.add_subplot(gs[0, 0])
    for backend in ORDER:
        x, y = by_backend(rows, backend, "recall_at_10")
        ax1.plot(x, y, marker="o", linewidth=2, markersize=6, label=backend, color=COLORS[backend])
    ax1.set_xscale("log"); ax1.set_xticks(scales); ax1.set_xticklabels([str(s) for s in scales])
    ax1.set_ylim(0.65, 1.03)
    ax1.set_title("Recall@10", fontweight="bold")
    ax1.set_xlabel("Corpus"); ax1.set_ylabel("Recall@10")

    ax2 = fig.add_subplot(gs[0, 1])
    for backend in ORDER:
        x, y = by_backend(rows, backend, "query_avg_ms")
        ax2.plot(x, y, marker="o", linewidth=2, markersize=6, label=backend, color=COLORS[backend])
    ax2.set_xscale("log"); ax2.set_xticks(scales); ax2.set_xticklabels([str(s) for s in scales])
    ax2.set_title("Latence de requête (ms)", fontweight="bold")
    ax2.set_xlabel("Corpus"); ax2.set_ylabel("ms")

    ax3 = fig.add_subplot(gs[1, 0])
    for backend in ORDER:
        x, y = by_backend(rows, backend, "index_time_sec")
        ax3.plot(x, y, marker="o", linewidth=2, markersize=6, label=backend, color=COLORS[backend])
    ax3.set_xscale("log"); ax3.set_yscale("log")
    ax3.set_xticks(scales); ax3.set_xticklabels([str(s) for s in scales])
    ax3.set_title("Temps d'indexation (s, log)", fontweight="bold")
    ax3.set_xlabel("Corpus"); ax3.set_ylabel("secondes")

    ax4 = fig.add_subplot(gs[1, 1])
    x4 = list(range(len(frows)))
    ax4.bar([i - w/2 for i in x4], [r["chromadb_native_filter_avg_ms"] for r in frows], w,
            label="ChromaDB natif", color=COLORS["ChromaDB(HNSW)"], edgecolor="white")
    ax4.bar([i + w/2 for i in x4], [r["manual_numpy_filter_avg_ms"] for r in frows], w,
            label="Masque NumPy", color=COLORS["NumPy-BruteForce"], edgecolor="white")
    ax4.set_yscale("log")
    ax4.set_xticks(x4); ax4.set_xticklabels([str(r["scale"]) for r in frows])
    ax4.set_title("Filtrage org_id (ms, log)", fontweight="bold")
    ax4.set_xlabel("Corpus"); ax4.set_ylabel("ms")

    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.04), fontsize=10)
    fig.suptitle("Benchmark Vector Store — ChromaDB vs FAISS vs NumPy",
                 fontsize=16, fontweight="bold", y=1.09)
    path = os.path.join(CHARTS_DIR, "0_benchmark_dashboard.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    print(f"\n[OK] Tous les graphiques sauvegardes dans : {CHARTS_DIR}")


if __name__ == "__main__":
    main()
