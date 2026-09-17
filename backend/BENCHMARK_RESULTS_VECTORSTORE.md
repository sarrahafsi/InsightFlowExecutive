# Benchmark Vector Store — InsightFlow Executive (RAG)

Justification empirique du choix de **ChromaDB** comme vector store pour le
RAG (`intelligence/rag/retriever.py`, `embedder.py`). Méthodologie : comparer
ChromaDB à des alternatives sur un corpus synthétique de messages business
(email/Slack/Jira/ClickUp), à plusieurs échelles représentatives du volume
par organisation, avec vérité terrain connue pour mesurer la perte de
précision de l'approximation (recall).

Script : `benchmark_vectorstore.py`. Résultats bruts : `benchmark_vectorstore_results.csv`,
`benchmark_vectorstore_filter_results.csv`.

## Résumé (échelle 10 000 messages — cas le plus exigeant testé)

| Base | Vitesse rangement (indexation) | Vitesse recherche | Précision (Recall@10) | Filtre par entreprise (org_id) | Taille disque |
|---|---|---|---|---|---|
| NumPy brute-force | Instantané (0.006s) | Rapide (0.7ms) | Parfaite (1.000) | ❌ à coder à la main | 14.6 MB |
| FAISS-Flat (exact) | Instantané (0.008s) | Moyen (2.0ms) | Parfaite (1.000) | ❌ à coder à la main | 14.6 MB |
| FAISS-HNSW (approximatif) | Rapide (0.25s) | Très rapide (0.12ms) | Faible (0.736) | ❌ à coder à la main | 17.2 MB |
| **ChromaDB (retenu)** | Lent (12.5s) | Rapide (1.8ms) | **Quasi-parfaite (1.000)** | ✅ natif | 29.3 MB |

**Pourquoi ChromaDB est retenu** : c'est le seul des quatre qui reste
quasi-parfait en précision (Recall@10 proche de 1.000, même avec beaucoup de
messages) tout en offrant nativement le filtrage par entreprise — les
alternatives sont plus rapides à ranger ou à chercher, mais soit ratent près
de 3 résultats pertinents sur 10 (FAISS-HNSW), soit obligeraient à coder et
maintenir à la main l'isolation entre entreprises (NumPy, FAISS), un risque
de sécurité pour un dashboard multi-clients.

## Méthodologie

- **Corpus** : messages synthétiques (sujet + corps + référence unique),
  5 organisations simulées (`org_id`), 5 sources — mêmes dimensions que
  `MessageRaw`/`DataItem` en production.
- **Embeddings** : `all-MiniLM-L6-v2` (identique à `embedder.py`), calculés
  **une seule fois** et réutilisés tels quels pour tous les backends — on
  isole la performance de l'index/recherche, pas le coût d'embedding
  (identique partout).
- **Échelles** : 200 / 1 000 / 5 000 / 10 000 messages — couvre le volume
  réaliste par organisation (la tâche planifiée de réindexation utilise
  `limit=2000` par défaut, voir `embedder.py::index_from_db`).
- **Requêtes** : 25 questions CEO typiques (facturation, churn, incidents,
  sprint, sécurité...), latence moyenne + p95 sur recherche top-10.
- **Recall@10** : accord avec le top-10 exact (NumPy brute-force = vérité
  terrain), mesure la perte de précision de l'approximation (ANN).
- **Candidats** :
  - **ChromaDB** (HNSW, `PersistentClient`, config identique à la prod)
  - **FAISS `IndexFlatIP`** — recherche exacte, bibliothèque dédiée
  - **FAISS `IndexHNSWFlat`** — ANN, même famille d'algorithme que ChromaDB
  - **NumPy brute-force** (produit matriciel) — baseline sans dépendance dédiée

## Résultats

| Échelle | Backend | Index (s) | Query avg (ms) | Query p95 (ms) | Recall@10 | Disque (MB) |
|---|---|---|---|---|---|---|
| 200 | NumPy | 0.0001 | 0.065 | 0.051 | 1.000 | 0.29 |
| 200 | FAISS-Flat (exact) | 0.001 | 0.212 | 0.170 | 1.000 | 0.29 |
| 200 | FAISS-HNSW | 0.011 | 0.153 | 0.122 | 1.000 | 0.35 |
| 200 | **ChromaDB** | 0.245 | 2.105 | 1.885 | **1.000** | 1.00 |
| 1 000 | NumPy | 0.001 | 0.114 | 0.147 | 1.000 | 1.47 |
| 1 000 | FAISS-Flat (exact) | 0.001 | 0.180 | 0.349 | 1.000 | 1.47 |
| 1 000 | FAISS-HNSW | 0.024 | 0.113 | 0.161 | 0.968 | 1.72 |
| 1 000 | **ChromaDB** | 0.930 | 1.786 | 1.742 | **1.000** | 4.89 |
| 5 000 | NumPy | 0.003 | 0.456 | 0.569 | 1.000 | 7.32 |
| 5 000 | FAISS-Flat (exact) | 0.004 | 0.702 | 0.803 | 1.000 | 7.32 |
| 5 000 | FAISS-HNSW | 0.106 | 0.115 | 0.154 | **0.724** | 8.62 |
| 5 000 | **ChromaDB** | 6.017 | 1.819 | 2.041 | **0.996** | 15.74 |
| 10 000 | NumPy | 0.006 | 0.726 | 0.810 | 1.000 | 14.65 |
| 10 000 | FAISS-Flat (exact) | 0.008 | 2.048 | 2.396 | 1.000 | 14.65 |
| 10 000 | FAISS-HNSW | 0.246 | 0.119 | 0.148 | **0.736** | 17.24 |
| 10 000 | **ChromaDB** | 12.452 | 1.824 | 1.849 | **1.000** | 29.31 |

### Filtrage multi-tenant par métadonnées (`org_id`)

Isolation multi-tenant utilisée en production (voir `retriever.py`,
`where={"org_id": {"$eq": org_id}}`) — comparaison au filtrage natif
ChromaDB vs un masque NumPy fait maison (seule option pour FAISS, qui n'a pas
de filtrage par métadonnées intégré) :

| Échelle | ChromaDB natif (ms) | Masque NumPy maison (ms) |
|---|---|---|
| 200 | 2.27 | 0.03 |
| 1 000 | 3.30 | 0.04 |
| 5 000 | 8.79 | 0.11 |
| 10 000 | 19.05 | 0.28 |

## Constats

**1. Le recall de FAISS-HNSW se dégrade fortement avec la taille, celui de
ChromaDB reste stable.** Avec des paramètres HNSW comparables (M=32), FAISS
tombe à 0.724–0.736 de recall@10 dès 5 000 documents — c'est-à-dire qu'un
quart des vrais top-10 résultats sont manqués — alors que ChromaDB reste à
0.996–1.000 sur toute la plage testée. Cause identifiée : le paramètre de
recherche `efSearch` de FAISS a une valeur par défaut trop basse (16) pour
ce volume, et nécessite un réglage manuel pour ce cas d'usage — un piège
classique de FAISS "prêt à l'emploi". ChromaDB gère ce compromis en interne
avec des valeurs par défaut plus sûres. **Argument fort en faveur de
ChromaDB** : la précision "out of the box" est fiable sans expertise ANN
supplémentaire, ce qui compte pour un produit où une recherche RAG ratée
(document pertinent non retrouvé) dégrade directement la réponse au CEO.

**2. Le surcoût d'indexation de ChromaDB est réel et croît plus vite que les
alternatives.** 12.5s pour indexer 10 000 documents contre 0.25s pour
FAISS-HNSW (~50×) et 0.008s pour FAISS-Flat. Ce coût vient de la couche de
persistance (écriture SQLite par batch) que FAISS/NumPy n'ont pas nativement.
**Pas bloquant en l'état** : la tâche de réindexation en production plafonne
à `limit=2000` par appel (`index_from_db`), soit environ 2s d'après
l'interpolation des mesures — largement acceptable pour un job planifié en
arrière-plan (`ml_scheduler.py`). À surveiller si ce plafond était relevé de
façon significative.

**3. La latence de requête de ChromaDB est dominée par un coût fixe (~1.8ms),
pas par la taille du corpus.** Elle reste quasi constante entre 200 et 10 000
documents, alors que NumPy/FAISS-Flat (exacts, sans structure d'index)
croissent avec la taille. Ce coût fixe correspond au passage par la couche
Python/FFI de ChromaDB, pas à la recherche elle-même. **Conséquence
pratique** : à l'échelle actuelle d'InsightFlow (quelques milliers de
messages par organisation), toutes les solutions répondent en moins de
2-3ms — la latence n'est décisive pour aucun choix ici.

**4. À cette échelle, un vector store dédié n'est pas strictement
nécessaire pour la vitesse brute** — NumPy brute-force reste sous la
milliseconde jusqu'à 10 000 documents. Ce qui justifie ChromaDB n'est donc
pas la vitesse de recherche, mais les fonctionnalités obtenues "gratuitement" :
persistance sur disque, upsert incrémental, et surtout le **filtrage natif
par métadonnées** (constat 5).

**5. Le filtrage par métadonnées est ~10-70× plus lent chez ChromaDB qu'un
masque NumPy fait main (2 à 19ms vs 0.03 à 0.28ms), mais reste largement
dans un budget acceptable (<20ms) et ne nécessite aucun code
d'infrastructure supplémentaire.** FAISS/NumPy n'offrent pas de filtrage par
métadonnées intégré — l'isolation multi-tenant par `org_id` (critique pour
la sécurité, cf. [[feedback_connector_manager]]) devrait être codée et
maintenue à la main avec ces alternatives. Le surcoût de latence de ChromaDB
est le prix d'une fonctionnalité de sécurité native plutôt qu'un
désavantage brut.

## Décision retenue

**ChromaDB confirmé.** Aux volumes réels d'InsightFlow (quelques milliers de
messages par organisation, réindexation plafonnée à 2000), aucune des
alternatives testées n'apporte un gain qui justifierait de réécrire le
filtrage multi-tenant à la main (FAISS/NumPy) ou d'accepter une dégradation
de recall non triviale (FAISS-HNSW avec réglages par défaut). Le compromis
observé — indexation plus lente, latence de requête légèrement plus haute
en absolu — est largement compensé par la précision de recherche stable et
le filtrage par métadonnées natif, tous deux directement utilisés en
production dans `retriever.py`.

**Point de vigilance pour la suite** : si le volume par organisation dépasse
significativement 10 000-20 000 messages (hors du périmètre testé ici), le
temps d'indexation de ChromaDB devra être remesuré — c'est la seule
dimension où l'écart avec les alternatives s'élargit avec l'échelle dans nos
mesures.
