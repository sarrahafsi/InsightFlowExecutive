"""
Benchmark Vector Store — InsightFlow Executive PFE
====================================================
Candidats   : ChromaDB (HNSW, en place), FAISS-IndexFlatIP (exact),
              FAISS-IndexHNSWFlat (ANN), NumPy brute-force (baseline sans
              librairie dediee).
Question    : le choix de ChromaDB pour le RAG (retriever.py) est-il justifie
              empiriquement a l'echelle de donnees realiste d'InsightFlow
              (messages par organisation), ou une alternative serait-elle
              plus rapide / plus precise ?

Methodologie : memes embeddings (all-MiniLM-L6-v2, normalises L2) injectes
directement dans chaque backend — on isole la performance de l'index/de la
recherche, pas le cout de l'embedding (identique partout, deja mesure comme
cout fixe hors benchmark). Corpus synthetique de messages business
(email/slack/jira/clickup) genere a plusieurs echelles pour observer le
comportement au fil de la croissance du volume.

Metriques :
- index_time_sec   : temps pour construire/peupler l'index
- query_avg_ms / query_p95_ms : latence de recherche top-10 (25 requetes)
- recall_at_10     : accord avec le top-10 exact (NumPy brute-force = verite
                     terrain), mesure la perte de precision de l'ANN
- disk_mb          : taille de l'index serialise sur disque
- ram_delta_mb     : delta RSS process pendant l'indexation (best-effort)

Une section separee mesure le filtrage par metadonnees (org_id), fonctionnalite
native de ChromaDB utilisee en production (isolation multi-tenant, cf.
retriever.py) mais absente de FAISS/NumPy sans code maison.
"""

import csv
import gc
import os
import random
import shutil
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np

RESULTS_FILE = Path(__file__).parent / "benchmark_vectorstore_results.csv"
FILTER_RESULTS_FILE = Path(__file__).parent / "benchmark_vectorstore_filter_results.csv"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # identique a embedder.py
SCALES      = [200, 1000, 5000, 10000]                    # volumes realistes par organisation
N_QUERIES   = 25
TOP_K       = 10
N_ORGS      = 5                                           # pour le test de filtrage multi-tenant

random.seed(42)
np.random.seed(42)


# ── Generation du corpus synthetique (messages business) ────────────────────
SOURCES  = ["gmail", "slack", "jira", "clickup", "teams"]
SUBJECTS = [
    "Retard sur le sprint API", "Facture client en attente", "Churn detecte sur compte majeur",
    "Bug critique en production", "Revue budgetaire Q3", "Recrutement poste backend",
    "Escalade support client", "Deploiement bloque en CI/CD", "Feedback beta testeurs",
    "Renegociation contrat fournisseur", "Panne serveur cette nuit", "Objectifs sprint suivant",
    "Plainte client sur la facturation", "Nouvelle fonctionnalite dashboard", "Fuite de donnees suspectee",
    "Retour investisseur apres demo", "Congres partenaire annuel", "Migration base de donnees",
    "Incident securite mineur", "Onboarding nouveau client entreprise",
]
BODIES = [
    "Le probleme vient d'un timeout de connexion a la base de donnees, l'equipe travaille sur un correctif.",
    "Le client menace de resilier si le probleme n'est pas resolu avant vendredi.",
    "Les metriques montrent une baisse d'engagement de 15% ce mois-ci sur ce compte.",
    "Le deploiement a echoue trois fois de suite, rollback effectue en attendant.",
    "Budget approuve sous reserve d'une revue trimestrielle des couts d'infrastructure.",
    "Candidat retenu apres le dernier entretien technique, offre en cours de redaction.",
    "Ticket escalade niveau 2 apres 48h sans reponse du support de premier niveau.",
    "Pipeline bloque sur l'etape de tests d'integration, erreur de configuration Docker.",
    "Retours globalement positifs, quelques demandes sur la performance mobile.",
    "Fournisseur propose une hausse de 8%, a negocier avant renouvellement du contrat.",
    "Serveur principal indisponible 20 minutes cette nuit, cause encore en investigation.",
    "Objectif fixe a 40 points de velocite, en baisse par rapport au sprint precedent.",
    "Client conteste un montant sur la derniere facture, ecart de 350 euros a verifier.",
    "Prototype pret pour demo interne, integration prevue le mois prochain.",
    "Acces anormal detecte depuis une IP inconnue, equipe securite en cours d'analyse.",
    "Investisseur satisfait de la demo, demande un suivi mensuel des metriques cles.",
    "Stand reserve pour le salon, materiel de presentation a preparer avant le 15.",
    "Migration prevue ce week-end, fenetre de maintenance de 4 heures annoncee.",
    "Tentative de connexion suspecte bloquee automatiquement, aucun acces confirme.",
    "Kickoff prevu la semaine prochaine avec l'equipe technique du nouveau client.",
]
AUTHORS = ["Sarah Hafsi", "Karim Haddad", "Yasmine Trabelsi", "Omar Ben Ali", "Lina Gharbi", "Noah Berrada"]


def generate_corpus(n: int) -> list[dict]:
    """Genere n messages synthetiques distincts (texte + metadonnees org_id/source)."""
    docs = []
    for i in range(n):
        subject = random.choice(SUBJECTS)
        body = random.choice(BODIES)
        text = f"{subject}\n\n{body} (ref-{i})"   # ref-i garantit l'unicite du texte
        docs.append({
            "id": f"doc_{i}",
            "text": text,
            "source": random.choice(SOURCES),
            "author": random.choice(AUTHORS),
            "org_id": f"org_{i % N_ORGS}",
        })
    return docs


QUERIES = [
    "probleme de facturation avec un client",
    "retard sur le developpement de l'API",
    "signe de churn sur un compte important",
    "incident de securite a investiguer",
    "budget et couts d'infrastructure",
    "recrutement d'un nouveau developpeur",
    "escalade d'un ticket support",
    "echec de deploiement en production",
    "retour des utilisateurs beta",
    "negociation avec un fournisseur",
    "panne serveur cette nuit",
    "objectifs du prochain sprint",
    "client qui conteste une facture",
    "nouvelle fonctionnalite du dashboard",
    "fuite de donnees potentielle",
    "reunion avec un investisseur",
    "salon professionnel a venir",
    "migration de la base de donnees",
    "tentative d'acces non autorisee",
    "integration d'un nouveau client entreprise",
    "velocite de l'equipe en baisse",
    "demo produit interne",
    "connexion suspecte bloquee",
    "renouvellement de contrat fournisseur",
    "support client de premier niveau",
]


# ── Utilitaires ───────────────────────────────────────────────────────────
def _rss_mb() -> float:
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 3)


def recall_at_k(retrieved_ids: list[str], ground_truth_ids: list[str], k: int) -> float:
    gt = set(ground_truth_ids[:k])
    got = set(retrieved_ids[:k])
    return round(len(gt & got) / k, 4)


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    idx = int(round(p / 100 * (len(s) - 1)))
    return s[idx]


# ── Backends ─────────────────────────────────────────────────────────────
def bench_numpy(embeddings: np.ndarray, query_vecs: np.ndarray, ground_truth: list[list[str]], ids: list[str]):
    """Brute-force cosine via produit matriciel (embeddings deja normalises L2)."""
    gc.collect()
    ram0 = _rss_mb()
    t0 = time.perf_counter()
    matrix = embeddings.copy()   # "indexation" = copie en memoire, pas de structure dediee
    index_time = time.perf_counter() - t0
    ram_delta = max(0.0, _rss_mb() - ram0)

    lat = []
    recalls = []
    for qi, qv in enumerate(query_vecs):
        t0 = time.perf_counter()
        scores = matrix @ qv
        top_idx = np.argpartition(-scores, TOP_K)[:TOP_K]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        lat.append((time.perf_counter() - t0) * 1000)
        retrieved = [ids[i] for i in top_idx]
        recalls.append(recall_at_k(retrieved, ground_truth[qi], TOP_K))

    tmp_npy = Path(tempfile.gettempdir()) / "bench_vs_numpy.npy"
    np.save(tmp_npy, matrix)
    disk_mb = round(tmp_npy.stat().st_size / (1024 * 1024), 3)
    tmp_npy.unlink(missing_ok=True)

    return {
        "backend": "NumPy-BruteForce", "index_time_sec": round(index_time, 4),
        "query_avg_ms": round(statistics.mean(lat), 3), "query_p95_ms": round(percentile(lat, 95), 3),
        "recall_at_10": round(statistics.mean(recalls), 4), "disk_mb": disk_mb,
        "ram_delta_mb": round(ram_delta, 2),
    }


def bench_faiss_flat(embeddings: np.ndarray, query_vecs: np.ndarray, ground_truth: list[list[str]], ids: list[str]):
    import faiss
    gc.collect()
    ram0 = _rss_mb()
    d = embeddings.shape[1]
    index = faiss.IndexFlatIP(d)   # exact, produit scalaire = cosinus (vecteurs normalises)
    t0 = time.perf_counter()
    index.add(embeddings)
    index_time = time.perf_counter() - t0
    ram_delta = max(0.0, _rss_mb() - ram0)

    lat, recalls = [], []
    for qi, qv in enumerate(query_vecs):
        t0 = time.perf_counter()
        _, idx = index.search(qv.reshape(1, -1), TOP_K)
        lat.append((time.perf_counter() - t0) * 1000)
        retrieved = [ids[i] for i in idx[0]]
        recalls.append(recall_at_k(retrieved, ground_truth[qi], TOP_K))

    tmp_idx = Path(tempfile.gettempdir()) / "bench_vs_flat.index"
    faiss.write_index(index, str(tmp_idx))
    disk_mb = round(tmp_idx.stat().st_size / (1024 * 1024), 3)
    tmp_idx.unlink(missing_ok=True)

    return {
        "backend": "FAISS-FlatIP(exact)", "index_time_sec": round(index_time, 4),
        "query_avg_ms": round(statistics.mean(lat), 3), "query_p95_ms": round(percentile(lat, 95), 3),
        "recall_at_10": round(statistics.mean(recalls), 4), "disk_mb": disk_mb,
        "ram_delta_mb": round(ram_delta, 2),
    }


def bench_faiss_hnsw(embeddings: np.ndarray, query_vecs: np.ndarray, ground_truth: list[list[str]], ids: list[str]):
    import faiss
    gc.collect()
    ram0 = _rss_mb()
    d = embeddings.shape[1]
    index = faiss.IndexHNSWFlat(d, 32)   # M=32, meme famille d'algo que ChromaDB (HNSW)
    index.hnsw.efConstruction = 40
    t0 = time.perf_counter()
    index.add(embeddings)
    index_time = time.perf_counter() - t0
    ram_delta = max(0.0, _rss_mb() - ram0)

    lat, recalls = [], []
    for qi, qv in enumerate(query_vecs):
        t0 = time.perf_counter()
        _, idx = index.search(qv.reshape(1, -1), TOP_K)
        lat.append((time.perf_counter() - t0) * 1000)
        retrieved = [ids[i] for i in idx[0] if i != -1]
        recalls.append(recall_at_k(retrieved, ground_truth[qi], TOP_K))

    tmp_idx = Path(tempfile.gettempdir()) / "bench_vs_hnsw.index"
    faiss.write_index(index, str(tmp_idx))
    disk_mb = round(tmp_idx.stat().st_size / (1024 * 1024), 3)
    tmp_idx.unlink(missing_ok=True)

    return {
        "backend": "FAISS-HNSW(ANN)", "index_time_sec": round(index_time, 4),
        "query_avg_ms": round(statistics.mean(lat), 3), "query_p95_ms": round(percentile(lat, 95), 3),
        "recall_at_10": round(statistics.mean(recalls), 4), "disk_mb": disk_mb,
        "ram_delta_mb": round(ram_delta, 2),
    }


def bench_chromadb(docs: list[dict], embeddings: np.ndarray, query_vecs: np.ndarray,
                    ground_truth: list[list[str]], ids: list[str]):
    import chromadb
    tmp_dir = Path(tempfile.mkdtemp(prefix="bench_chroma_"))
    try:
        gc.collect()
        ram0 = _rss_mb()
        client = chromadb.PersistentClient(path=str(tmp_dir))
        # meme config que embedder.py (espace cosinus) — embeddings pre-calcules
        # fournis directement, pas de embedding_function ici (comparaison equitable
        # de l'index/recherche, cout d'embedding deja identique partout)
        col = client.get_or_create_collection(name="bench", metadata={"hnsw:space": "cosine"})

        t0 = time.perf_counter()
        batch_size = 100
        n = len(docs)
        for i in range(0, n, batch_size):
            col.add(
                ids=ids[i:i + batch_size],
                embeddings=embeddings[i:i + batch_size].tolist(),
                documents=[d["text"] for d in docs[i:i + batch_size]],
                metadatas=[{"org_id": d["org_id"], "source": d["source"]} for d in docs[i:i + batch_size]],
            )
        index_time = time.perf_counter() - t0
        ram_delta = max(0.0, _rss_mb() - ram0)

        lat, recalls = [], []
        for qi, qv in enumerate(query_vecs):
            t0 = time.perf_counter()
            res = col.query(query_embeddings=[qv.tolist()], n_results=TOP_K, include=[])
            lat.append((time.perf_counter() - t0) * 1000)
            retrieved = res["ids"][0]
            recalls.append(recall_at_k(retrieved, ground_truth[qi], TOP_K))

        disk_mb = _dir_size_mb(tmp_dir)

        # test de filtrage natif par metadonnees (isolation multi-tenant, cf. retriever.py)
        filter_lat = []
        target_org = "org_0"
        for qv in query_vecs:
            t0 = time.perf_counter()
            col.query(query_embeddings=[qv.tolist()], n_results=TOP_K,
                      where={"org_id": {"$eq": target_org}}, include=[])
            filter_lat.append((time.perf_counter() - t0) * 1000)

        return {
            "backend": "ChromaDB(HNSW)", "index_time_sec": round(index_time, 4),
            "query_avg_ms": round(statistics.mean(lat), 3), "query_p95_ms": round(percentile(lat, 95), 3),
            "recall_at_10": round(statistics.mean(recalls), 4), "disk_mb": disk_mb,
            "ram_delta_mb": round(ram_delta, 2),
        }, round(statistics.mean(filter_lat), 3)
    finally:
        del client, col
        gc.collect()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def bench_manual_filter_numpy(embeddings: np.ndarray, docs: list[dict], query_vecs: np.ndarray) -> float:
    """
    Filtrage 'fait maison' equivalent pour NumPy/FAISS (qui n'ont pas de filtre
    natif par metadonnees) : masque booleen + recherche restreinte a org_0.
    Represente le cout d'implementation qu'imposerait FAISS/NumPy en prod pour
    reproduire l'isolation multi-tenant que ChromaDB offre nativement.
    """
    mask = np.array([d["org_id"] == "org_0" for d in docs])
    subset = embeddings[mask]
    lat = []
    for qv in query_vecs:
        t0 = time.perf_counter()
        scores = subset @ qv
        k = min(TOP_K, len(subset))
        top_idx = np.argpartition(-scores, k - 1)[:k] if k > 0 else np.array([])
        _ = top_idx[np.argsort(-scores[top_idx])] if k > 0 else top_idx
        lat.append((time.perf_counter() - t0) * 1000)
    return round(statistics.mean(lat), 3)


# ── Boucle principale ───────────────────────────────────────────────────
def main():
    print("Etape 1/4 — Chargement du modele d'embedding (identique a embedder.py)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)

    print(f"Etape 2/4 — Generation du corpus synthetique (max {max(SCALES)} messages)...")
    all_docs = generate_corpus(max(SCALES))
    print(f"  [OK] {len(all_docs)} messages generes ({N_ORGS} organisations simulees).")

    print("Etape 3/4 — Encodage des embeddings (une seule fois, reutilises pour tous les backends)...")
    t0 = time.perf_counter()
    all_texts = [d["text"] for d in all_docs]
    all_embeddings = model.encode(all_texts, batch_size=64, show_progress_bar=True,
                                   normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    query_vecs = model.encode(QUERIES[:N_QUERIES], normalize_embeddings=True,
                               convert_to_numpy=True).astype("float32")
    print(f"  [OK] Embeddings encodes en {time.perf_counter() - t0:.1f}s "
          f"(dim={all_embeddings.shape[1]}).")

    print("\nEtape 4/4 — Benchmark par echelle de corpus...")
    results = []
    filter_rows = []

    for n in SCALES:
        print(f"\n{'=' * 70}")
        print(f"  Echelle : {n} messages")
        print(f"{'=' * 70}")
        docs = all_docs[:n]
        embeddings = all_embeddings[:n]
        ids = [d["id"] for d in docs]

        # verite terrain exacte (numpy brute-force) pour le calcul du recall
        ground_truth = []
        for qv in query_vecs:
            scores = embeddings @ qv
            top_idx = np.argsort(-scores)[:TOP_K]
            ground_truth.append([ids[i] for i in top_idx])

        for label, fn in [
            ("NumPy-BruteForce", lambda: bench_numpy(embeddings, query_vecs, ground_truth, ids)),
            ("FAISS-FlatIP(exact)", lambda: bench_faiss_flat(embeddings, query_vecs, ground_truth, ids)),
            ("FAISS-HNSW(ANN)", lambda: bench_faiss_hnsw(embeddings, query_vecs, ground_truth, ids)),
        ]:
            print(f"  -> {label}...", end=" ", flush=True)
            r = fn()
            r["scale"] = n
            results.append(r)
            print(f"index={r['index_time_sec']}s  query_avg={r['query_avg_ms']}ms  "
                  f"recall@10={r['recall_at_10']}  disk={r['disk_mb']}MB")

        print("  -> ChromaDB(HNSW)...", end=" ", flush=True)
        r_chroma, filter_avg_ms = bench_chromadb(docs, embeddings, query_vecs, ground_truth, ids)
        r_chroma["scale"] = n
        results.append(r_chroma)
        print(f"index={r_chroma['index_time_sec']}s  query_avg={r_chroma['query_avg_ms']}ms  "
              f"recall@10={r_chroma['recall_at_10']}  disk={r_chroma['disk_mb']}MB")

        manual_avg_ms = bench_manual_filter_numpy(embeddings, docs, query_vecs)
        filter_rows.append({
            "scale": n,
            "chromadb_native_filter_avg_ms": filter_avg_ms,
            "manual_numpy_filter_avg_ms": manual_avg_ms,
        })
        print(f"  -> Filtrage org_id : ChromaDB natif={filter_avg_ms}ms  "
              f"vs masque NumPy maison={manual_avg_ms}ms")

    # ── Sauvegarde ──────────────────────────────────────────────────────
    fields = ["scale", "backend", "index_time_sec", "query_avg_ms", "query_p95_ms",
              "recall_at_10", "disk_mb", "ram_delta_mb"]
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(f"\n[OK] CSV sauvegarde : {RESULTS_FILE}")

    with open(FILTER_RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["scale", "chromadb_native_filter_avg_ms", "manual_numpy_filter_avg_ms"])
        w.writeheader()
        w.writerows(filter_rows)
    print(f"[OK] CSV filtrage sauvegarde : {FILTER_RESULTS_FILE}")

    # ── Resume ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 100}")
    print(f"  {'Echelle':>8} {'Backend':<22} {'Index(s)':>9} {'Query avg(ms)':>14} "
          f"{'Query p95(ms)':>14} {'Recall@10':>10} {'Disk(MB)':>9} {'RAM(MB)':>8}")
    print(f"{'=' * 100}")
    for r in results:
        print(f"  {r['scale']:>8} {r['backend']:<22} {r['index_time_sec']:>9} "
              f"{r['query_avg_ms']:>14} {r['query_p95_ms']:>14} {r['recall_at_10']:>10} "
              f"{r['disk_mb']:>9} {r['ram_delta_mb']:>8}")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    main()
