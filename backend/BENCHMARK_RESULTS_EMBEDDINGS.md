# Benchmark Modèles d'Embedding — InsightFlow Executive (RAG)

Justification empirique du modèle d'embedding utilisé par le RAG
(`intelligence/rag/embedder.py`, actuellement **all-MiniLM-L6-v2**).
Méthodologie : comparer à 3 alternatives sur un corpus business
synthétique bilingue (français/anglais), avec vérité terrain connue —
même esprit que les benchmarks OCR/Vision (Phase 0) et Vector Store.

Script : `benchmark_embeddings.py`. Graphiques : `ml/charts/embeddings/`.
Résultats bruts : `benchmark_embeddings_results.csv`,
`benchmark_embeddings_retrieval_detail.csv`.

## Résumé

| Modèle | Dim | Disque (MB) | Débit (phrases/s) | P@1 | P@3 | MRR | **P@1 cross-lingue** | Écart sémantique |
|---|---|---|---|---|---|---|---|---|
| **MiniLM-L6-v2 (actuel)** | 384 | 174.7 | **169.6** | 0.65 | 0.65 | 0.663 | **0.00** | 0.662 |
| **Multilingual-MiniLM-L12** | 384 | 457.5 | 45.1 | **1.00** | **1.00** | **1.00** | **1.00** | **0.755** |
| MPNet-base-v2 | 768 | 418.4 | 27.3 | 0.65 | 0.70 | 0.688 | 0.00 | 0.676 |
| BGE-small-en-v1.5 | 384 | 128.3 | 96.3 | 0.65 | 0.70 | 0.697 | 0.00 | 0.340 |

**Pourquoi le modèle multilingue est retenu** : c'est le seul des quatre
qui retrouve les documents pertinents quand la langue de la question du
CEO diffère de la langue du message source (P@1 cross-lingue = 1.00 contre
**0.00 pour les trois autres**, y compris le modèle actuellement en
production) — un scénario qui arrive réellement dans InsightFlow (emails
en français, tickets Jira/Slack en anglais). Le coût est raisonnable :
~2.7× plus lourd sur disque et ~3.8× plus lent à encoder, sans impact
pratique vu le volume traité (voir section Performance).

## Méthodologie

- **Corpus** : 60 messages synthétiques (12 sujets business × 5
  reformulations chacun — facturation, churn, incident sécurité, sprint,
  budget, recrutement, bug production, déploiement, feedback beta,
  fournisseur, panne serveur, onboarding), moitié à dominante française,
  moitié anglaise — reflète le mélange réel des sources InsightFlow
  (Gmail souvent FR, Jira/Slack souvent EN).
- **20 requêtes** CEO avec sujet correct connu à l'avance, dont **7
  volontairement cross-lingues** (question posée dans la langue opposée à
  celle du document cible — ex. question en anglais sur un sujet à
  documents français).
- **Retrieval** : Precision@1, Precision@3, Mean Reciprocal Rank (MRR),
  calculés globalement et séparément sur le sous-ensemble cross-lingue.
- **Discrimination sémantique** : 15 paires de phrases étiquetées à la
  main (paraphrase / même domaine mais fait différent / sans rapport),
  mesure l'écart de similarité cosinus entre catégories et la corrélation
  de Spearman entre l'étiquette humaine et la similarité mesurée (même
  méthodologie que le score CLIP du benchmark Vision).
- **Performance** : temps de chargement, débit d'encodage (phrases/sec,
  CPU), taille sur disque mesurée réellement via
  `huggingface_hub.scan_cache_dir()` (pas une estimation).
- **Équité** : tous les modèles sont appelés avec un `encode()` simple,
  sans prefixe d'instruction spécial. BGE recommande officiellement un
  préfixe côté requête ("Represent this sentence for searching relevant
  passages: ") qui améliorerait probablement ses scores — non appliqué ici
  car aucun autre candidat n'a d'équivalent en production, et
  `embedder.py` n'implémente pas ce genre de logique par modèle.

## Constats

**1. Le modèle en production échoue totalement dès que la langue de la
question diffère de celle du document (P@1 cross-lingue = 0.00).** Ce
n'est pas un défaut spécifique à MiniLM : MPNet-base-v2 et BGE-small-en,
tous deux entraînés presque exclusivement sur de l'anglais, échouent de la
même façon (0.00 / 0.00). Le seul modèle qui s'en sort est celui
explicitement entraîné à aligner les langues entre elles
(**paraphrase-multilingual-MiniLM-L12-v2**, 1.00 partout). C'est un mode
d'échec silencieux en production : le retriever ne renvoie pas d'erreur,
il renvoie juste les mauvais documents avec un score de distance
plausible — l'utilisateur ne peut pas savoir qu'il rate l'information
pertinente.

**2. Sur les requêtes dans la même langue que le document, tous les
modèles sont globalement comparables (P@1 = 0.65 pour trois modèles sur
quatre).** La différence ne se joue donc pas sur la qualité sémantique
générale, mais spécifiquement sur la couverture multilingue — un point
qu'un benchmark anglais-only (comme la plupart des benchmarks publics
MTEB) ne révèle pas, d'où l'intérêt de ce test maison avec des données
représentatives d'InsightFlow.

**3. Le score de discrimination sémantique de BGE-small est trompeur pris
isolément.** Son écart absolu (paraphrase − non-lié = 0.340) est le plus
faible des quatre, mais sa corrélation de Spearman est la meilleure
(ρ=0.945) — signe que BGE compresse ses scores de similarité dans une
plage plus étroite tout en gardant le bon ordre relatif. Aucun des deux
indicateurs pris seul ne suffit ; c'est la performance de retrieval
concrète (P@1/P@3/MRR) qui reste le critère décisif ici, pas le score STS
abstrait.

**4. Le coût du modèle multilingue est net mais reste largement gérable.**
457 MB contre 174 MB (+162%), et 45 phrases/sec contre 170 (~3.8× plus
lent). À l'échelle de la réindexation en production (`limit=2000` par
défaut, cf. [[project_vectorstore_benchmark]]), cela représente environ
44s au lieu de 12s pour un job de réindexation en tâche de fond — un
delta non gênant pour un traitement asynchrone planifié
(`ml_scheduler.py`), largement compensé par la disparition d'un vrai
angle mort fonctionnel.

## Décision retenue

**Remplacer `all-MiniLM-L6-v2` par
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** dans
`embedder.py` (`EMBED_MODEL`). Justification : c'est le seul candidat qui
couvre le cas d'usage réel d'InsightFlow où les sources sont dans une
langue et la question du CEO dans une autre — un gain de P@1 cross-lingue
de 0.00 à 1.00 sur le jeu de test, pour un surcoût de latence
d'indexation négligeable à l'échelle de production actuelle. Même
dimension d'embedding (384) que le modèle actuel, donc aucun changement
requis côté ChromaDB (`hnsw:space: cosine` reste valide).

**Action de suivi nécessaire si ce changement est appliqué** : une
réindexation complète de `chroma_db/` est obligatoire (les vecteurs de
deux modèles différents ne sont pas comparables dans une même
collection) — via `index_from_db(org_id=None)` pour toutes les
organisations.
