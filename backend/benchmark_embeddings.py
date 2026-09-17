"""
Benchmark Modeles d'Embedding — InsightFlow Executive PFE
============================================================
Modele en place : sentence-transformers/all-MiniLM-L6-v2 (embedder.py).
Question : ce choix est-il justifie empiriquement, ou un autre modele
serait-il plus pertinent pour le RAG (retriever.py) ?

Candidats :
- all-MiniLM-L6-v2                     (actuel — leger, anglais-centre)
- paraphrase-multilingual-MiniLM-L12-v2 (multilingue FR/EN — meme famille)
- all-mpnet-base-v2                     (qualite generale plus elevee, EN)
- BAAI/bge-small-en-v1.5                 (optimise recherche/retrieval, EN)

Pourquoi le multilingue compte specifiquement ici : les sources ingerees par
InsightFlow melangent les langues dans la vraie vie (Gmail/reunions internes
souvent en francais, Jira/Slack techniques souvent en anglais) alors que le
CEO peut poser sa question dans l'une ou l'autre langue. Un modele mono-
langue peut echouer a retrouver un document pertinent ecrit dans l'autre
langue — c'est mesure explicitement ici (sous-ensemble "cross-lingual").

Trois familles de tests, avec verite terrain connue (comme les benchmarks
OCR/Vision de Phase 0) :
1. Retrieval (P@1 / P@3 / MRR) : 60 messages synthetiques (12 sujets x 5
   reformulations), 20 requetes CEO avec le sujet correct connu a l'avance.
   Mesure aussi separement le sous-ensemble "cross-lingual" (7 requetes ou
   la langue de la question differe de la langue dominante du sujet cible).
2. Discrimination semantique (paires) : 15 paires de phrases etiquetees
   parapharse / lie / non-lie (verite terrain manuelle), mesure l'ecart de
   similarite cosinus entre categories + correlation de Spearman.
3. Performance : temps de chargement, debit d'encodage (phrases/sec, CPU),
   dimension du vecteur, taille sur disque (mesuree via huggingface_hub
   scan_cache_dir, pas une estimation).

Note d'honnetete methodologique : tous les modeles sont testes avec un
encode() simple, sans prefixe d'instruction special — c'est ainsi que
embedder.py appelle le modele en production. BGE recommande officiellement
un prefixe cote requete ("Represent this sentence for searching relevant
passages: ") qui ameliorerait probablement ses scores de retrieval — non
applique ici pour rester a competences egales avec les autres candidats
(aucun n'a de tel prefixe en production).
"""

import csv
import statistics
import time
from pathlib import Path

import numpy as np

RESULTS_CSV       = Path(__file__).parent / "benchmark_embeddings_results.csv"
RETRIEVAL_CSV     = Path(__file__).parent / "benchmark_embeddings_retrieval_detail.csv"

MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/all-mpnet-base-v2",
    "BAAI/bge-small-en-v1.5",
]
MODEL_LABELS = {
    "sentence-transformers/all-MiniLM-L6-v2": "MiniLM-L6-v2 (actuel)",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "Multilingual-MiniLM-L12",
    "sentence-transformers/all-mpnet-base-v2": "MPNet-base-v2",
    "BAAI/bge-small-en-v1.5": "BGE-small-en-v1.5",
}

TOP_K = 3  # pour P@3


# ── Corpus : 12 sujets business x 5 reformulations (verite terrain = sujet) ──
CORPUS = {
    "facturation_client": {"lang": "fr", "docs": [
        "Le client conteste un montant de 350 euros sur sa derniere facture.",
        "Nous avons recu une reclamation concernant un ecart de facturation avec ce client.",
        "Le service comptabilite signale une erreur sur le montant facture au client.",
        "Le client demande un remboursement partiel suite a une erreur de facturation.",
        "Un litige est en cours avec le client au sujet du montant de la facture.",
    ]},
    "retard_sprint": {"lang": "en", "docs": [
        "The API sprint is delayed due to unresolved integration issues.",
        "Our velocity dropped this sprint because of blocked tickets.",
        "The backend team is behind schedule on the current sprint deliverables.",
        "Sprint planning shows we will miss the deadline for the API milestone.",
        "The development team reports a slip in the sprint timeline.",
    ]},
    "churn_client": {"lang": "fr", "docs": [
        "Un client important montre des signes clairs de desengagement.",
        "L'usage du produit par ce compte a fortement baisse ce mois-ci.",
        "Nous risquons de perdre un client majeur si rien n'est fait rapidement.",
        "Le taux d'engagement de ce compte cle est en chute libre.",
        "Ce client n'a pas ouvert l'application depuis plusieurs semaines, signe de churn.",
    ]},
    "incident_securite": {"lang": "en", "docs": [
        "A suspicious login attempt was detected from an unknown IP address.",
        "Our security team is investigating a potential unauthorized access.",
        "An anomalous access pattern triggered a security alert overnight.",
        "We blocked a suspicious connection attempt to the admin panel.",
        "The security team flagged unusual activity on a user account.",
    ]},
    "budget_infra": {"lang": "fr", "docs": [
        "Le budget infrastructure du trimestre a ete revu a la hausse.",
        "Les couts serveurs ont augmente de 20 pourcent ce mois-ci.",
        "La direction financiere demande une reduction des depenses cloud.",
        "Le budget alloue a l'infrastructure doit etre valide avant vendredi.",
        "Une revue des couts d'hebergement est prevue avec l'equipe finance.",
    ]},
    "recrutement": {"lang": "fr", "docs": [
        "Un candidat a ete retenu pour le poste de developpeur backend.",
        "L'entretien technique du candidat senior s'est bien deroule.",
        "Nous avons une offre a envoyer au candidat retenu pour le poste.",
        "Le recrutement pour le poste de developpeur avance bien.",
        "Le processus de recrutement du nouveau developpeur touche a sa fin.",
    ]},
    "bug_production": {"lang": "en", "docs": [
        "A critical bug was found in the production payment flow.",
        "Users are reporting errors when checking out in production.",
        "The production environment is showing a critical defect since this morning.",
        "A severe bug is affecting checkout for some users in production.",
        "Our monitoring detected a critical issue in the live payment system.",
    ]},
    "deploiement_echec": {"lang": "en", "docs": [
        "The deployment pipeline failed three times in a row today.",
        "Our CI/CD build is broken after the latest configuration change.",
        "The last release failed to deploy due to a Docker configuration error.",
        "Deployment to production failed and we had to roll back.",
        "The release pipeline is stuck at the integration test stage.",
    ]},
    "feedback_beta": {"lang": "en", "docs": [
        "Beta testers gave mostly positive feedback on the new dashboard.",
        "Early users are happy with the product but want better mobile performance.",
        "Feedback from the beta group was largely favorable this round.",
        "Most beta testers liked the new feature but flagged some UI bugs.",
        "The beta cohort reported a good overall experience with minor issues.",
    ]},
    "negociation_fournisseur": {"lang": "fr", "docs": [
        "Le fournisseur propose une augmentation de tarif de 8 pourcent pour l'annee prochaine.",
        "Nous devons renegocier le contrat avec notre fournisseur cloud.",
        "Le renouvellement du contrat fournisseur est prevu ce mois-ci.",
        "Une hausse de prix du fournisseur est a discuter avant signature.",
        "L'equipe achats negocie de meilleures conditions avec le fournisseur.",
    ]},
    "panne_serveur": {"lang": "en", "docs": [
        "The main server was down for 20 minutes last night.",
        "We experienced an unexpected outage on the primary database server.",
        "A server crash caused a brief service interruption overnight.",
        "The infrastructure team is investigating last night's server outage.",
        "Our production server went offline unexpectedly for several minutes.",
    ]},
    "onboarding_client": {"lang": "fr", "docs": [
        "Le kickoff avec le nouveau client entreprise est prevu la semaine prochaine.",
        "L'equipe technique prepare l'integration du nouveau client majeur.",
        "L'onboarding du nouveau client grand compte demarre lundi.",
        "Une reunion de demarrage est planifiee avec le nouveau client.",
        "Le processus d'integration du nouveau client entreprise est en cours.",
    ]},
}

# (requete, sujet_correct, cross_lingual)
# cross_lingual=True si la langue de la requete differe de la langue dominante du sujet cible
QUERIES = [
    ("Le client se plaint du montant facture sur sa derniere facture.", "facturation_client", False),
    ("Why is the API sprint behind schedule?", "retard_sprint", False),
    ("Un gros client montre des signes de desabonnement.", "churn_client", False),
    ("Was there any unauthorized login attempt recently?", "incident_securite", False),
    ("Le budget infrastructure a-t-il ete approuve ce trimestre ?", "budget_infra", False),
    ("Ou en est le recrutement du developpeur backend ?", "recrutement", False),
    ("Is there a critical bug affecting production checkout?", "bug_production", False),
    ("Why did the last deployment fail?", "deploiement_echec", False),
    ("What do beta testers think about the new dashboard?", "feedback_beta", False),
    ("Le fournisseur a-t-il propose une hausse de prix ?", "negociation_fournisseur", False),
    ("What happened during last night's server outage?", "panne_serveur", False),
    ("Quand demarre l'onboarding du nouveau client entreprise ?", "onboarding_client", False),
    ("Y a-t-il un litige en cours sur une facture client ?", "facturation_client", False),
    ("Are we going to lose an important customer soon?", "churn_client", True),
    ("Did we get overcharged or is there a billing dispute?", "facturation_client", True),
    ("Le pipeline de deploiement a-t-il echoue ?", "deploiement_echec", True),
    ("L'equipe est-elle en retard sur le sprint en cours ?", "retard_sprint", True),
    ("Y a-t-il eu une activite suspecte sur un compte utilisateur ?", "incident_securite", True),
    ("Le serveur principal est-il tombe en panne cette nuit ?", "panne_serveur", True),
    ("Is the cloud vendor asking for a price increase?", "negociation_fournisseur", True),
]

# (phrase_a, phrase_b, label) — label: 2=paraphrase, 1=lie (meme domaine), 0=non-lie
STS_PAIRS = [
    ("Le serveur est tombe en panne cette nuit.", "Il y a eu une panne serveur durant la nuit.", 2),
    ("The deployment failed again today.", "Today's deployment failed once more.", 2),
    ("Le client menace de resilier son contrat.", "Le client envisage de mettre fin a son contrat.", 2),
    ("A critical bug is affecting checkout.", "There's a severe bug impacting the checkout process.", 2),
    ("Le budget infrastructure a augmente.", "Les couts d'infrastructure ont grimpe.", 2),
    ("Le serveur est tombe en panne cette nuit.", "Le budget serveur a ete augmente ce trimestre.", 1),
    ("The deployment failed today.", "The sprint is behind schedule.", 1),
    ("Le client menace de resilier son contrat.", "Le fournisseur a augmente ses tarifs.", 1),
    ("A critical bug is affecting checkout.", "Beta testers reported UI issues.", 1),
    ("Le recrutement du developpeur avance bien.", "L'onboarding du nouveau client demarre lundi.", 1),
    ("Le serveur est tombe en panne cette nuit.", "Le recrutement du developpeur avance bien.", 0),
    ("The deployment failed today.", "Le client menace de resilier son contrat.", 0),
    ("A critical bug is affecting checkout.", "Le fournisseur propose une hausse de tarif.", 0),
    ("Beta testers gave positive feedback.", "Un acces suspect a ete detecte sur un compte.", 0),
    ("L'onboarding du nouveau client demarre lundi.", "The API sprint is delayed.", 0),
]


def _flatten_corpus():
    ids, texts, topics = [], [], []
    for topic_id, meta in CORPUS.items():
        for i, doc in enumerate(meta["docs"]):
            ids.append(f"{topic_id}_{i}")
            texts.append(doc)
            topics.append(topic_id)
    return ids, texts, topics


def _model_disk_size_mb(model_name: str) -> float:
    try:
        from huggingface_hub import scan_cache_dir
        info = scan_cache_dir()
        for repo in info.repos:
            if repo.repo_id == model_name:
                return round(repo.size_on_disk / (1024 * 1024), 1)
    except Exception:
        pass
    return -1.0


def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))  # vecteurs deja normalises L2


def evaluate_model(model_name: str) -> dict:
    from sentence_transformers import SentenceTransformer

    print(f"\n{'=' * 70}")
    print(f"  {model_name}")
    print(f"{'=' * 70}")

    t0 = time.perf_counter()
    model = SentenceTransformer(model_name)
    load_sec = round(time.perf_counter() - t0, 2)
    dim = model.get_sentence_embedding_dimension()
    disk_mb = _model_disk_size_mb(model_name)
    print(f"  Charge en {load_sec}s — dimension={dim} — disque={disk_mb}MB")

    # ── Debit d'encodage (throughput) ────────────────────────────────
    doc_ids, doc_texts, doc_topics = _flatten_corpus()
    t0 = time.perf_counter()
    doc_embeddings = model.encode(doc_texts, batch_size=32, normalize_embeddings=True,
                                   convert_to_numpy=True).astype("float32")
    encode_sec = time.perf_counter() - t0
    throughput = round(len(doc_texts) / encode_sec, 1) if encode_sec > 0 else -1
    print(f"  Debit encodage : {throughput} phrases/sec ({len(doc_texts)} docs en {encode_sec:.3f}s)")

    query_texts = [q[0] for q in QUERIES]
    query_embeddings = model.encode(query_texts, normalize_embeddings=True,
                                     convert_to_numpy=True).astype("float32")

    # ── Retrieval : P@1 / P@3 / MRR (global + cross-lingual) ─────────
    retrieval_rows = []
    p1_all, p3_all, rr_all = [], [], []
    p1_cross, p3_cross, rr_cross = [], [], []

    for qi, (qtext, correct_topic, cross) in enumerate(QUERIES):
        scores = doc_embeddings @ query_embeddings[qi]
        ranked_idx = np.argsort(-scores)
        ranked_topics = [doc_topics[i] for i in ranked_idx]

        p1 = 1.0 if ranked_topics[0] == correct_topic else 0.0
        p3 = 1.0 if correct_topic in ranked_topics[:TOP_K] else 0.0
        rank = next((r + 1 for r, t in enumerate(ranked_topics) if t == correct_topic), len(ranked_topics))
        rr = 1.0 / rank

        p1_all.append(p1); p3_all.append(p3); rr_all.append(rr)
        if cross:
            p1_cross.append(p1); p3_cross.append(p3); rr_cross.append(rr)

        retrieval_rows.append({
            "model": model_name, "query": qtext, "correct_topic": correct_topic,
            "cross_lingual": cross, "top1_topic": ranked_topics[0],
            "p_at_1": p1, "p_at_3": p3, "reciprocal_rank": round(rr, 4),
        })

    # ── Discrimination semantique (paires STS-like) ──────────────────
    from scipy.stats import spearmanr
    sims, labels = [], []
    cat_sims = {2: [], 1: [], 0: []}
    for a, b, label in STS_PAIRS:
        emb = model.encode([a, b], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        sim = _cos_sim(emb[0], emb[1])
        sims.append(sim); labels.append(label)
        cat_sims[label].append(sim)

    rho, _ = spearmanr(labels, sims)
    sts_gap = statistics.mean(cat_sims[2]) - statistics.mean(cat_sims[0])

    result = {
        "model": MODEL_LABELS[model_name],
        "model_full_name": model_name,
        "dim": dim,
        "disk_mb": disk_mb,
        "load_sec": load_sec,
        "throughput_docs_per_sec": throughput,
        "p_at_1": round(statistics.mean(p1_all), 4),
        "p_at_3": round(statistics.mean(p3_all), 4),
        "mrr": round(statistics.mean(rr_all), 4),
        "p_at_1_cross_lingual": round(statistics.mean(p1_cross), 4) if p1_cross else -1,
        "mrr_cross_lingual": round(statistics.mean(rr_cross), 4) if rr_cross else -1,
        "sts_sim_paraphrase": round(statistics.mean(cat_sims[2]), 4),
        "sts_sim_related": round(statistics.mean(cat_sims[1]), 4),
        "sts_sim_unrelated": round(statistics.mean(cat_sims[0]), 4),
        "sts_gap": round(sts_gap, 4),
        "sts_spearman_rho": round(float(rho), 4),
    }

    print(f"  Retrieval  : P@1={result['p_at_1']}  P@3={result['p_at_3']}  MRR={result['mrr']}")
    print(f"  Cross-lingual (n={len(p1_cross)}) : P@1={result['p_at_1_cross_lingual']}  MRR={result['mrr_cross_lingual']}")
    print(f"  STS gap (parapharse-non_lie) : {result['sts_gap']}  |  Spearman rho={result['sts_spearman_rho']}")

    return result, retrieval_rows


def main():
    print("Benchmark modeles d'embedding — InsightFlow Executive")
    print(f"Corpus : {sum(len(m['docs']) for m in CORPUS.values())} documents / "
          f"{len(CORPUS)} sujets — {len(QUERIES)} requetes — {len(STS_PAIRS)} paires STS")

    all_results = []
    all_retrieval_rows = []
    for model_name in MODELS:
        result, retrieval_rows = evaluate_model(model_name)
        all_results.append(result)
        all_retrieval_rows.extend(retrieval_rows)

    fields = ["model", "model_full_name", "dim", "disk_mb", "load_sec", "throughput_docs_per_sec",
              "p_at_1", "p_at_3", "mrr", "p_at_1_cross_lingual", "mrr_cross_lingual",
              "sts_sim_paraphrase", "sts_sim_related", "sts_sim_unrelated", "sts_gap", "sts_spearman_rho"]
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(all_results)
    print(f"\n[OK] CSV sauvegarde : {RESULTS_CSV}")

    rfields = ["model", "query", "correct_topic", "cross_lingual", "top1_topic", "p_at_1", "p_at_3", "reciprocal_rank"]
    with open(RETRIEVAL_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rfields)
        w.writeheader(); w.writerows(all_retrieval_rows)
    print(f"[OK] Detail retrieval sauvegarde : {RETRIEVAL_CSV}")

    print(f"\n{'=' * 115}")
    print(f"  {'Modele':<26} {'Dim':>5} {'Disque(MB)':>11} {'Debit(doc/s)':>13} "
          f"{'P@1':>6} {'P@3':>6} {'MRR':>6} {'P@1 cross':>10} {'STS gap':>8}")
    print(f"{'=' * 115}")
    for r in all_results:
        print(f"  {r['model']:<26} {r['dim']:>5} {r['disk_mb']:>11} {r['throughput_docs_per_sec']:>13} "
              f"{r['p_at_1']:>6} {r['p_at_3']:>6} {r['mrr']:>6} {r['p_at_1_cross_lingual']:>10} {r['sts_gap']:>8}")
    print(f"{'=' * 115}")


if __name__ == "__main__":
    main()
