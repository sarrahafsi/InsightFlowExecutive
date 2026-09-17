# Synthèse complète des benchmarks — InsightFlow Executive

Ce document réunit **les 4 benchmarks empiriques** réalisés pour justifier
les choix techniques d'InsightFlow Executive : OCR/Vision (analyse
d'images), Vector Store (recherche RAG), Modèles d'embedding (RAG), et LLM
(génération des réponses). Chaque benchmark suit la même philosophie :
comparer plusieurs candidats sur un jeu de test avec **vérité terrain
connue à l'avance**, pas une simple impression subjective — comme dans un
vrai protocole d'évaluation scientifique, à l'échelle d'un projet de PFE.

Documents détaillés (un par benchmark) :
- `BENCHMARK_RESULTS.md` — OCR & Vision (Phase 0, analyse d'images)
- `BENCHMARK_RESULTS_VECTORSTORE.md` — ChromaDB vs FAISS vs NumPy
- `BENCHMARK_RESULTS_EMBEDDINGS.md` — Modèles d'embedding (RAG)
- `BENCHMARK_RESULTS_LLM.md` — Ollama vs Groq (génération de réponses)

Graphiques : `ml/charts/vision/`, `ml/charts/vectorstore/`,
`ml/charts/embeddings/`. Scripts reproductibles : `backend/benchmark_*.py`.

---

## Vue d'ensemble — décisions finales

| # | Benchmark | Candidats comparés | Décision retenue | Appliqué au code ? |
|---|---|---|---|---|
| 1 | OCR (extraction de texte d'image) | Tesseract, EasyOCR, PaddleOCR | **Tesseract** | Oui (déjà en place) |
| 2 | Captioning (description d'image) | BLIP-base, ViT-GPT2, GIT-base | **BLIP-base** | Oui (déjà en place) |
| 3 | Vector Store (recherche RAG) | ChromaDB, FAISS-Flat, FAISS-HNSW, NumPy | **ChromaDB confirmé** | Oui (aucun changement nécessaire) |
| 4 | Modèle d'embedding (RAG) | MiniLM-L6, Multilingual-MiniLM-L12, MPNet, BGE-small | **Multilingual-MiniLM-L12** | **Oui — appliqué et réindexé** |
| 5 | LLM (génération réponses) | Ollama (local), Groq (cloud) | **Ollama reste par défaut** ; Groq recommandé en option | Non — décision produit/confidentialité, pas encore appliquée |

---

## 1. OCR & Vision — analyse d'images (Phase 0)

**Contexte** : InsightFlow doit extraire l'information de captures d'écran
(erreurs, tickets, dashboards, conversations) partagées dans les messages.
Deux briques testées séparément : OCR (extraire le texte) et Captioning
(décrire l'image).

### OCR — extraction de texte

| Moteur | Précision (word accuracy) | Erreur caractère (CER) | Chargement | Inférence/image |
|---|---|---|---|---|
| **Tesseract** | **100%** | **0%** | **0.78s** | **0.35s** |
| EasyOCR | 97.2% | 0.4% | 11.31s | 1.37s |
| PaddleOCR | Échec (bug technique reproductible) | — | — | — |

**Décision : Tesseract** — précision parfaite, le plus rapide au chargement
et à l'inférence sur le jeu de test (8 images de texte synthétique avec
vérité terrain exacte).

### Captioning — description d'image

| Modèle | Score humain (/5) | Corrélation avec score humain (CLIP) |
|---|---|---|
| **BLIP-base** | **2.40** | ρ = 0.73 (fiable) |
| GIT-base | 1.47 | — |
| ViT-GPT2 | 1.00 | — |

**Découverte méthodologique importante** : les métriques automatiques
classiques (BLEU, ROUGE-L, METEOR) se sont révélées **contredire le
jugement humain** (corrélation négative, ρ entre -0.16 et -0.27) sur ce
type d'images hors-distribution (captures d'écran, pas des photos). Seul le
score CLIP restait fiable. **Décision : BLIP-base**, confirmé à la fois par
CLIP et par l'évaluation humaine directe, malgré une qualité globalement
limitée sur les catégories les plus difficiles (compensée architecturalement
par l'OCR comme source d'information primaire).

*(Détail complet : `BENCHMARK_RESULTS.md`)*

---

## 2. Vector Store — moteur de recherche du RAG

**Contexte** : le RAG (`intelligence/rag/retriever.py`) cherche les
messages les plus pertinents pour répondre à une question du CEO, via une
recherche par similarité (pas par mot-clé). ChromaDB est utilisé en
production — jamais comparé empiriquement avant ce benchmark.

**Candidats** : ChromaDB (en place), FAISS-Flat (recherche exacte), FAISS-HNSW
(recherche approximative), NumPy brute-force (méthode la plus simple, sert
de référence "100% juste").

**Échelles testées** : 200 / 1 000 / 5 000 / 10 000 messages (volume
réaliste par organisation).

| Base | Vitesse rangement | Vitesse recherche | Précision (Recall@10) | Filtre par entreprise (org_id) | Taille disque |
|---|---|---|---|---|---|
| NumPy brute-force | Instantané | Rapide (0.7ms) | Parfaite (1.000) | ❌ à coder à la main | 14.6 Mo |
| FAISS-Flat (exact) | Instantané | Moyen (2.0ms) | Parfaite (1.000) | ❌ à coder à la main | 14.6 Mo |
| FAISS-HNSW (approximatif) | Rapide (0.25s) | Très rapide (0.12ms) | **Faible (0.736)** | ❌ à coder à la main | 17.2 Mo |
| **ChromaDB (retenu)** | Lent (12.5s) | Rapide (1.8ms) | **Quasi-parfaite (1.000)** | ✅ natif | 29.3 Mo |

*(Recall@10 = sur les 10 meilleurs résultats trouvés, combien sont
vraiment les 10 meilleurs comparé à la méthode 100% juste. 1.000 = parfait.)*

**Constat clé** : FAISS-HNSW, avec ses réglages par défaut, **rate près de
3 résultats pertinents sur 10** dès que le volume de messages grandit — un
piège classique de ce type d'index quand il n'est pas réglé finement.
ChromaDB reste quasi-parfait sur toute la plage testée, sans réglage
particulier.

**Décision : ChromaDB confirmé.** Le compromis (indexation plus lente,
latence de requête légèrement plus haute en absolu) est largement compensé
par la précision de recherche stable et le filtrage natif par entreprise —
une fonctionnalité de sécurité critique pour un produit multi-clients, que
les alternatives obligeraient à coder et maintenir à la main.

*(Détail complet, méthodologie, graphiques : `BENCHMARK_RESULTS_VECTORSTORE.md`,
`ml/charts/vectorstore/`)*

---

## 3. Modèle d'embedding — "traducteur" texte → vecteur du RAG

**Contexte** : avant de chercher un message pertinent, il faut le
transformer en vecteur numérique (embedding) qui capture son sens. Le
modèle en production, `all-MiniLM-L6-v2`, n'avait jamais été comparé à des
alternatives.

**Candidats** : MiniLM-L6-v2 (en place), Multilingual-MiniLM-L12 (version
multilingue du même modèle), MPNet-base-v2 (qualité générale plus élevée),
BGE-small-en (optimisé recherche).

**Jeu de test** : 60 messages business synthétiques (12 sujets, moitié en
français, moitié en anglais — reflète le mélange réel des sources
InsightFlow : Gmail souvent FR, Jira/Slack souvent EN), 20 questions dont 7
volontairement posées **dans une langue différente** de celle du message
recherché.

| Modèle | 1er résultat correct | Bon résultat dans le top 3 | 1er résultat correct, **langue différente** | Vitesse | Poids |
|---|---|---|---|---|---|
| MiniLM-L6-v2 (actuel) | 65% | 65% | **0%** | 170 phrases/sec | 175 Mo |
| **Multilingual-MiniLM-L12 (retenu)** | **100%** | **100%** | **100%** | 45 phrases/sec | 458 Mo |
| MPNet-base-v2 | 65% | 70% | 0% | 27 phrases/sec | 418 Mo |
| BGE-small-en-v1.5 | 65% | 70% | 0% | 96 phrases/sec | 128 Mo |

**Découverte majeure** : le modèle en production **échouait totalement**
(0% de bonnes réponses) dès que la question du CEO était posée dans une
langue différente de celle du message source — un vrai angle mort
silencieux (pas d'erreur affichée, juste les mauvais documents retournés).
Ce n'était pas spécifique à MiniLM : MPNet et BGE, tous deux
anglais-centrés, échouaient pareil. Seul le modèle explicitement entraîné à
aligner plusieurs langues entre elles s'en sortait.

**Décision : remplacer par `paraphrase-multilingual-MiniLM-L12-v2`.**
**Changement déjà appliqué** dans `embedder.py` — la collection ChromaDB
complète a été réindexée (143 messages, aucune perte de données, les
vecteurs de l'ancien modèle n'étant pas compatibles avec le nouveau). Même
dimension d'embedding (384), aucun changement requis côté ChromaDB.

*(Détail complet, méthodologie, glossaire des métriques P@1/P@3/MRR,
graphiques : `BENCHMARK_RESULTS_EMBEDDINGS.md`, `ml/charts/embeddings/`)*

---

## 4. LLM — génération des réponses au CEO

**Contexte** : Ollama (local, gratuit) est le fournisseur LLM par défaut,
mais un commentaire dans le code de production notait déjà "Ollama sur CPU
est lent". Question : un service cloud rapide (Groq) change-t-il la donne ?

**Candidats** : Ollama (llama3.2:3b, local) vs Groq (openai/gpt-oss-20b,
cloud — modèle de taille comparable, les modèles Llama ayant disparu du
catalogue Groq entre la conception et l'exécution du benchmark).

**8 scénarios réalistes** (même format que la vraie route `/api/ask`),
avec mots-clés attendus connus à l'avance pour noter automatiquement la
qualité des réponses.

| Fournisseur | Latence moyenne | Débit | Mots-clés attendus trouvés | Format respecté |
|---|---|---|---|---|
| Ollama (llama3.2:3b, local) | 36.3s | 8.3 tokens/sec | 100% | 100% |
| **Groq (gpt-oss-20b, cloud)** | **1.1s** | **365 tokens/sec** | 96% | 100% |

**Constat** : Groq répond **~32× plus vite**, pour une qualité quasi
identique. Mais contrairement aux 3 autres benchmarks, ce n'est **pas
seulement une question de performance** : utiliser Groq signifie envoyer
les messages de l'entreprise (contexte RAG inclus dans le prompt) à un
service cloud tiers, avec un coût au-delà du free tier.

**Décision : Ollama reste le fournisseur par défaut** (100% local, aucune
donnée ne sort de la machine). Groq est recommandé comme **option
supplémentaire** activable par l'utilisateur avec avertissement explicite —
pas comme remplacement silencieux. **Aucun changement de code appliqué**
pour ce benchmark : c'est un arbitrage confidentialité/coût vs vitesse qui
dépasse le cadre d'une simple optimisation technique.

*(Détail complet : `BENCHMARK_RESULTS_LLM.md`)*

---

## Glossaire — toutes les métriques utilisées, en clair

| Métrique | Ce qu'elle mesure |
|---|---|
| **Word accuracy / CER** (OCR) | Fraction des mots correctement extraits d'une image / taux d'erreur caractère par caractère. |
| **Score humain, score CLIP** (Vision) | Note attribuée par une personne à la description générée / score automatique fiable mesurant si le texte décrit vraiment l'image. |
| **Recall@10** (Vector Store) | Sur les 10 meilleurs résultats renvoyés, combien sont vraiment les 10 meilleurs (comparé à une recherche exhaustive 100% juste). 1.0 = parfait. |
| **Temps d'indexation** | Le temps pour "ranger" tous les documents dans la base avant de pouvoir chercher dedans. |
| **Latence de requête** | Le temps de réponse à une seule recherche. |
| **P@1** (embeddings) | Sur 100 questions, dans combien de cas le tout premier résultat renvoyé est le bon. |
| **P@3** | Pareil, mais on tolère que le bon résultat soit n'importe où dans les 3 premiers. |
| **MRR** | Note qui punit la position du bon résultat dans la liste (1er = 1 point, 2e = 0.5, 4e = 0.25...). |
| **P@1 cross-lingue** | La même mesure que P@1, mais uniquement quand la question est posée dans une langue différente de celle du document recherché. |
| **Écart sémantique / Spearman ρ** | Capacité du modèle à distinguer des phrases qui disent la même chose de phrases sans rapport / à classer les phrases comme le ferait un humain. |
| **Débit (tokens ou phrases/sec)** | La vitesse de traitement — combien d'unités (mots ou phrases) le modèle traite par seconde. |
| **Latence moyenne / p95** (LLM) | Le temps d'attente moyen pour une réponse complète / le pire cas observé sur l'ensemble des essais. |
| **Mots-clés attendus trouvés** | Sur les mots-clés qu'une bonne réponse devrait contenir (connus à l'avance), la fraction réellement présente dans la réponse du modèle. |
| **Format respecté** | Le modèle suit-il bien la structure imposée par les instructions (sections obligatoires) ? |

---

## Actions de suivi

- [x] **Vector Store** : aucune action — ChromaDB confirmé tel quel.
- [x] **Embeddings** : modèle changé (`embedder.py`) + réindexation complète
      effectuée (143 messages).
- [ ] **LLM** : décision produit à prendre par l'équipe — ajouter Groq comme
      option `LLM_PROVIDER=groq` avec avertissement RGPD/confidentialité
      explicite dans l'UI avant de l'activer pour un client.
- [ ] **Vector Store — point de vigilance** : remesurer le temps
      d'indexation ChromaDB si le volume par organisation dépasse
      significativement 10 000-20 000 messages.

## Reproductibilité

Tous les scripts sont dans `backend/` et rejouables tels quels :
`benchmark_ocr.py`, `benchmark_captioning.py`, `benchmark_vectorstore.py`,
`benchmark_embeddings.py`, `benchmark_llm.py` (nécessite `GROQ_API_KEY` en
variable d'environnement pour la partie Groq). Les graphiques se
régénèrent via `ml/generate_vectorstore_charts.py` et
`ml/generate_embeddings_charts.py`.
