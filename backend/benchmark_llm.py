"""
Benchmark LLM — Ollama (local) vs Groq (cloud) — InsightFlow Executive PFE
============================================================================
Fournisseur en place : Ollama local (llama3.2:3b, cf. intelligence/llm/client.py,
_complete_ollama) — "gratuit, illimite" mais commentaire dans le code de prod
signale deja : "Ollama sur CPU est lent — cap a 400 tokens et timeout genereux".
Question : Groq (materiel LPU dedie, API cloud compatible OpenAI) apporte-t-il
un gain de vitesse suffisant pour justifier une dependance a un service externe ?

Candidats :
- Ollama local  : llama3.2:3b (modele deja installe, utilise en prod)
- Groq cloud    : llama-3.1-8b-instant (taille comparable — 8B vs 3B local,
                  la plus proche disponible chez Groq pour une comparaison
                  equitable sur la qualite, pas seulement sur la vitesse brute)

Methodologie : memes prompts (system + user) pour les deux, construits sur le
meme patron que la vraie route /api/ask en mode RAG (SYSTEM_ANALYST +
contexte "MESSAGES: ... QUESTION: ...", cf. application/routes/ask.py) — pas
des prompts jouets, le format reellement envoye en production.

8 scenarios avec mots-cles attendus connus a l'avance (verite terrain, meme
esprit que les benchmarks OCR/Vision) pour mesurer objectivement :
1. Couverture des mots-cles attendus (la reponse mentionne-t-elle les faits
   demandes ?)
2. Conformite au format impose par le prompt systeme (3 sections obligatoires)
3. Latence totale (secondes, de l'appel a la reponse complete)
4. Debit de generation (tokens/sec, mesure native de chaque fournisseur —
   eval_count/eval_duration pour Ollama, usage.completion_tokens pour Groq)

Securite : la cle API Groq est lue depuis la variable d'environnement
GROQ_API_KEY (jamais codee en dur, jamais affichee dans les logs/CSV).
"""

import csv
import os
import re
import statistics
import time
import unicodedata
from pathlib import Path

import httpx

RESULTS_CSV = Path(__file__).parent / "benchmark_llm_results.csv"
DETAIL_CSV  = Path(__file__).parent / "benchmark_llm_detail.csv"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "llama3.2"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# llama-3.1-8b-instant n'est plus dans le catalogue Groq (verifie via /v1/models
# le 07/09/2026 — plus aucun modele Llama disponible). gpt-oss-20b est le plus
# proche en taille du llama3.2:3b local parmi les modeles restants.
GROQ_MODEL    = "openai/gpt-oss-20b"
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")

# ── Meme prompt systeme que la production (application/routes/ask.py) ───────
SYSTEM_ANALYST = """Tu es l'assistant IA personnel d'un CEO d'entreprise.
Ton role est d'ANALYSER les donnees de l'entreprise et de repondre aux questions du CEO.

REGLE CRITIQUE — FORMAT : Structure TOUJOURS ta reponse ainsi :

**Analyse des messages**
Voici les informations cles extraites des messages :
* [point cle 1] (Messages [N])
* [point cle 2] (Messages [N])
...

**Projections et recommandations**
* [recommandation 1]
* [recommandation 2]
...

**Prochaines etapes**
* [action concrete 1]
* [action concrete 2]
...

Si aucune donnee trouvee, dis-le clairement sans inventer."""

REQUIRED_SECTIONS = ["analyse des messages", "projections et recommandations", "prochaines etapes"]

# (contexte messages, question, mots-cles attendus dans la reponse)
SCENARIOS = [
    (
        "[1] Sarah (gmail) — 2026-09-01\nLe client conteste un montant de 350 euros sur sa derniere facture.\n\n"
        "[2] Karim (gmail) — 2026-09-02\nUn litige est en cours avec le client au sujet du montant de la facture.",
        "Y a-t-il un litige en cours avec un client sur une facture ?",
        ["facture", "client", "litige"],
    ),
    (
        "[1] Yasmine (slack) — 2026-09-03\nLe serveur principal est tombe en panne 20 minutes cette nuit.\n\n"
        "[2] Omar (slack) — 2026-09-03\nL'equipe infra investigue la cause de la panne serveur d'hier soir.",
        "Que s'est-il passe cette nuit avec le serveur ?",
        ["serveur", "panne", "nuit"],
    ),
    (
        "[1] Lina (jira) — 2026-09-04\nUn bug critique affecte le paiement en production depuis ce matin.\n\n"
        "[2] Noah (jira) — 2026-09-04\nLes utilisateurs signalent des erreurs au moment de payer en production.",
        "Y a-t-il un bug critique en production actuellement ?",
        ["bug", "production", "critique"],
    ),
    (
        "[1] Sarah (gmail) — 2026-09-05\nUn client important montre des signes clairs de desengagement ce mois-ci.\n\n"
        "[2] Karim (gmail) — 2026-09-05\nNous risquons de perdre ce client majeur si rien n'est fait rapidement.",
        "Risque-t-on de perdre un client important ?",
        ["client", "perdre", "important"],
    ),
    (
        "[1] Omar (gmail) — 2026-09-06\nLe budget infrastructure du trimestre a ete revu a la hausse de 20 pourcent.\n\n"
        "[2] Lina (gmail) — 2026-09-06\nLa direction financiere valide la hausse du budget cloud pour ce trimestre.",
        "Le budget infrastructure a-t-il augmente ce trimestre ?",
        ["budget", "infrastructure", "hausse"],
    ),
    (
        "[1] Noah (gmail) — 2026-09-07\nUn candidat a ete retenu pour le poste de developpeur backend.\n\n"
        "[2] Yasmine (gmail) — 2026-09-07\nL'offre au candidat retenu pour le poste de developpeur va etre envoyee.",
        "Ou en est le recrutement du developpeur backend ?",
        ["recrutement", "developpeur", "candidat"],
    ),
    (
        "[1] Sarah (jira) — 2026-09-08\nLe deploiement a echoue trois fois de suite a cause d'une erreur Docker.\n\n"
        "[2] Karim (jira) — 2026-09-08\nLe dernier deploiement en production a echoue, rollback effectue.",
        "Pourquoi le dernier deploiement a-t-il echoue ?",
        ["deploiement", "echoue", "docker"],
    ),
    (
        "[1] Lina (gmail) — 2026-09-09\nLe fournisseur cloud propose une hausse de tarif de 8 pourcent l'an prochain.\n\n"
        "[2] Omar (gmail) — 2026-09-09\nUne hausse de prix du fournisseur est a negocier avant la signature.",
        "Le fournisseur propose-t-il une hausse de prix ?",
        ["fournisseur", "prix", "hausse"],
    ),
]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _normalize(s: str) -> str:
    return _strip_accents(s.lower())


def keyword_coverage(answer: str, keywords: list[str]) -> float:
    norm = _normalize(answer)
    hits = sum(1 for kw in keywords if _normalize(kw) in norm)
    return round(hits / len(keywords), 4)


def format_compliance(answer: str) -> float:
    norm = _normalize(answer)
    hits = sum(1 for section in REQUIRED_SECTIONS if _normalize(section) in norm)
    return round(hits / len(REQUIRED_SECTIONS), 4)


def call_ollama(system: str, user: str) -> dict:
    prompt = f"{system}\n\n{user}"
    t0 = time.perf_counter()
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.3, "num_predict": 400, "num_gpu": 0},
            },
        )
        resp.raise_for_status()
        data = resp.json()
    wall_sec = time.perf_counter() - t0

    answer = data.get("response", "").strip()
    eval_count = data.get("eval_count", 0)
    eval_duration_sec = data.get("eval_duration", 0) / 1e9  # nanosecondes -> secondes
    tokens_per_sec = round(eval_count / eval_duration_sec, 1) if eval_duration_sec > 0 else 0.0

    return {"answer": answer, "wall_sec": round(wall_sec, 3),
            "tokens": eval_count, "tokens_per_sec": tokens_per_sec}


def call_groq(system: str, user: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=60.0)

    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
        max_tokens=400,
    )
    wall_sec = time.perf_counter() - t0

    answer = resp.choices[0].message.content or ""
    completion_tokens = resp.usage.completion_tokens if resp.usage else 0
    tokens_per_sec = round(completion_tokens / wall_sec, 1) if wall_sec > 0 else 0.0

    return {"answer": answer, "wall_sec": round(wall_sec, 3),
            "tokens": completion_tokens, "tokens_per_sec": tokens_per_sec}


def run_backend(label: str, call_fn) -> tuple[dict, list[dict]]:
    print(f"\n{'=' * 70}\n  {label}\n{'=' * 70}")
    detail_rows = []
    wall_secs, tps_list, kw_scores, fmt_scores = [], [], [], []

    for i, (context, question, keywords) in enumerate(SCENARIOS, 1):
        user_msg = f"MESSAGES :\n{context}\n\nQUESTION : {question}"
        print(f"  [{i}/{len(SCENARIOS)}] {question[:55]:<55}", end=" ", flush=True)
        try:
            r = call_fn(SYSTEM_ANALYST, user_msg)
            kw = keyword_coverage(r["answer"], keywords)
            fmt = format_compliance(r["answer"])
            wall_secs.append(r["wall_sec"]); tps_list.append(r["tokens_per_sec"])
            kw_scores.append(kw); fmt_scores.append(fmt)
            print(f"{r['wall_sec']}s  {r['tokens_per_sec']}tok/s  mots-cles={kw}  format={fmt}")
            detail_rows.append({
                "backend": label, "question": question, "wall_sec": r["wall_sec"],
                "tokens": r["tokens"], "tokens_per_sec": r["tokens_per_sec"],
                "keyword_coverage": kw, "format_compliance": fmt,
                "answer_excerpt": r["answer"][:300].replace("\n", " "),
            })
        except Exception as e:
            print(f"ERREUR : {e}")
            detail_rows.append({
                "backend": label, "question": question, "wall_sec": -1,
                "tokens": -1, "tokens_per_sec": -1, "keyword_coverage": -1,
                "format_compliance": -1, "answer_excerpt": f"ERREUR: {e}",
            })

    def avg(lst):
        vals = [v for v in lst if v >= 0]
        return round(statistics.mean(vals), 3) if vals else -1

    def p95(lst):
        vals = sorted(v for v in lst if v >= 0)
        if not vals:
            return -1
        idx = int(round(0.95 * (len(vals) - 1)))
        return round(vals[idx], 3)

    summary = {
        "backend": label,
        "wall_sec_avg": avg(wall_secs), "wall_sec_p95": p95(wall_secs),
        "tokens_per_sec_avg": avg(tps_list),
        "keyword_coverage_avg": avg(kw_scores),
        "format_compliance_avg": avg(fmt_scores),
    }
    return summary, detail_rows


def main():
    all_summaries, all_details = [], []

    s, d = run_backend("Ollama (llama3.2:3b, local)", call_ollama)
    all_summaries.append(s); all_details.extend(d)

    if not GROQ_API_KEY:
        print("\n[SKIP] GROQ_API_KEY absent de l'environnement — benchmark Groq ignore.")
    else:
        s, d = run_backend(f"Groq ({GROQ_MODEL}, cloud)", call_groq)
        all_summaries.append(s); all_details.extend(d)

    fields = ["backend", "wall_sec_avg", "wall_sec_p95", "tokens_per_sec_avg",
              "keyword_coverage_avg", "format_compliance_avg"]
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(all_summaries)
    print(f"\n[OK] CSV sauvegarde : {RESULTS_CSV}")

    dfields = ["backend", "question", "wall_sec", "tokens", "tokens_per_sec",
               "keyword_coverage", "format_compliance", "answer_excerpt"]
    with open(DETAIL_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=dfields)
        w.writeheader(); w.writerows(all_details)
    print(f"[OK] Detail sauvegarde : {DETAIL_CSV}")

    print(f"\n{'=' * 100}")
    print(f"  {'Backend':<32} {'Latence avg(s)':>15} {'Latence p95(s)':>15} {'Tokens/s':>10} "
          f"{'Mots-cles':>10} {'Format':>8}")
    print(f"{'=' * 100}")
    for s in all_summaries:
        print(f"  {s['backend']:<32} {s['wall_sec_avg']:>15} {s['wall_sec_p95']:>15} "
              f"{s['tokens_per_sec_avg']:>10} {s['keyword_coverage_avg']:>10} {s['format_compliance_avg']:>8}")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    main()
