# Benchmark multimodal — InsightFlow Executive (Phase 0)

Justification empirique des choix OCR et Vision (captioning) pour la
fonctionnalité d'analyse d'images. Méthodologie : comparer plusieurs modèles
pré-entraînés sur un jeu de test avec vérité terrain connue, sur deux
familles d'images :
- **catégories génériques** (30 images) : graphiques (bar/pie/line), tableaux,
  captures d'email — présentes dans le benchmark original.
- **catégories cibles** (15 images, ajoutées) : boîte de dialogue d'erreur,
  stack trace, page d'erreur 503, crash report, notification de déploiement,
  carte de ticket Jira/ClickUp, liste de tickets, thread de commentaires,
  ticket bloqué, conversation Slack/Teams — reflètent les cas réels visés
  par le besoin (captures d'erreur technique, de ticket, de conversation).

Scripts : `benchmark_captioning.py` (Vision), `benchmark_ocr.py` (OCR).
Images générées : `benchmark_images/` (captioning), `benchmark_ocr_images/`
(OCR) — 100% synthétiques, aucune donnée réelle, régénérées à chaque run.

## 1. Captioning (Vision Understanding)

Modèles testés : **ViT-GPT2**, **BLIP-base**, **GIT-base** — tous via
`transformers`, CPU-only. Métriques : BLEU / ROUGE-L / METEOR (comparaison à
une référence écrite à la main) et CLIP score (similarité image↔texte, ne
dépend pas du choix des mots).

### Résultat global (45 images) vs par famille de catégories

| | ViT-GPT2 | BLIP-base | GIT-base |
|---|---|---|---|
| **Toutes (n=45)** — BLEU/ROUGE-L/METEOR/CLIP | 0.025 / 0.193 / 0.108 / 14.8 | **0.035 / 0.243 / 0.194 / 28.5** | 0.018 / 0.148 / 0.092 / 25.1 |
| **Catégories génériques (n=30)** | 0.021 / 0.162 / 0.088 / 13.7 | **0.045 / 0.299 / 0.251 / 30.0** | 0.023 / 0.189 / 0.121 / 25.3 |
| **Catégories cibles (n=15)** | **0.032 / 0.254 / 0.146** / 17.0 | 0.014 / 0.131 / 0.082 / **25.5** | 0.008 / 0.068 / 0.034 / 24.6 |

**Constat important** : sur les catégories génériques, BLIP-base gagne
largement sur les 4 métriques. Sur les catégories cibles (celles qui
comptent réellement pour InsightFlow), BLEU/ROUGE-L/METEOR **s'inversent** en
faveur de ViT-GPT2 — seul CLIP conserve BLIP-base en tête, avec un écart
réduit. Les métriques se contredisent : nécessite une évaluation humaine
pour trancher (voir ci-dessous), pas juste la moyenne automatique.

### Évaluation humaine (15 catégories cibles × 3 modèles = 45 captions notées)

Notées manuellement (échelle 1-5) en comparant chaque caption à l'image
réelle — voir `benchmark_results_human.csv`.

| Modèle | Score humain moyen |
|---|---|
| **BLIP-base** | **2.40 / 5** |
| GIT-base | 1.47 / 5 |
| ViT-GPT2 | 1.00 / 5 |

**Corrélation de Spearman (métrique automatique ↔ score humain)** —
voir `benchmark_correlation.csv` :

| Métrique | ρ | Interprétation |
|---|---|---|
| BLEU | -0.27 | négative — trompeuse sur ce domaine |
| ROUGE-L | -0.19 | négative — trompeuse |
| METEOR | -0.16 | négative — trompeuse |
| **CLIP** | **+0.73** | forte corrélation — fiable |

**Conclusion** : BLEU/ROUGE/METEOR sont construites pour comparer à une
référence figée mot-pour-mot — sur des images hors-distribution (captures
d'écran/documents, très différentes des photos COCO sur lesquelles ces 3
modèles sont entraînés), un modèle qui produit une légende générique et
vague (ViT-GPT2 : "a black and white photo of a computer keyboard") peut
obtenir un meilleur score n-gram qu'un modèle qui tente une vraie
description, purement par chevauchement lexical accidentel avec le gabarit
de la référence ("a screenshot of a..."). La corrélation négative de ces 3
métriques avec le jugement humain le confirme empiriquement sur ce jeu de
test. Le CLIP score, lui, reste fiable (ρ=0.73) et confirme le classement
humain : **BLIP-base reste le meilleur choix des 3, mais avec une
performance médiocre sur les catégories cibles (2.4/5)** — pas un problème
de choix de modèle parmi les 3, mais une limite partagée par tous
(entraînement COCO, pas documents/UI).

**Défaut observé chez BLIP-base à corriger dans `vision_service.py`** :
dégénérescence par répétition sur plusieurs images hors-distribution
(`"the api api api api api api..."`, `"krinrod krinrod krinrod..."`) — un
mode d'échec connu du décodage greedy/beam sans contrainte anti-répétition.
Corrigible simplement à l'inférence avec `no_repeat_ngram_size=3` (ou
`repetition_penalty>1.0`) sur `model.generate(...)` — à appliquer dans
l'implémentation finale, indépendamment du modèle retenu.

### Décision retenue

**BLIP-base**, confirmé par CLIP score (métrique la plus fiable sur ce
domaine, ρ=0.73 avec le jugement humain) et par l'évaluation humaine directe
— gagnant sur les deux tests malgré la contradiction des métriques n-gram.
Meilleur compromis vitesse/qualité (inférence la plus rapide du benchmark :
3.49s/image en moyenne). La faiblesse sur les catégories cibles est gérée
architecturalement : l'OCR reste la source d'information primaire pour les
images texte-lourdes (voir `image_processor.py`), le caption Vision n'étant
qu'un complément — cohérent avec le comportement mesuré ici.

## 2. OCR

Moteurs testés : **EasyOCR**, **Tesseract** (`pytesseract`), **PaddleOCR**.
Jeu de test : 8 images de texte synthétique (rendu PIL, police claire sur
fond blanc) avec vérité terrain exacte connue — messages d'erreur, KPI de
dashboard, champ de ticket, message de chat, paragraphe, stack trace,
facture — mêmes thèmes que les catégories cibles du benchmark captioning.
Métriques : word accuracy (mots de référence retrouvés) et CER (character
error rate, distance d'édition normalisée).

| Moteur | Word Accuracy | CER | Load | Inférence/image | Taille |
|---|---|---|---|---|---|
| **Tesseract** | **1.000** | **0.000** | **0.78s** | **0.346s** | 15 MB |
| EasyOCR | 0.972 | 0.004 | 11.31s | 1.37s | 65 MB |
| PaddleOCR | — | — | — | — | 45 MB |

**Tesseract gagne nettement** : précision parfaite sur les 8 images, ~15×
plus rapide à charger et ~4× plus rapide à l'inférence qu'EasyOCR — alors
que l'hypothèse de départ (voir section "Choix techniques" du plan)
favorisait EasyOCR sur un critère différent (aucun binaire système à
installer). Les chiffres contredisent cette hypothèse initiale sur ce jeu de
test : **la précision et la vitesse tranchent en faveur de Tesseract**,
malgré la dépendance à un binaire externe (déjà présent sur cette machine de
dev — `Tesseract-OCR/tesseract.exe` — et trivial à ajouter à une image Docker
de production via `apt-get install tesseract-ocr` sous Linux, pratique
standard). EasyOCR reste une alternative pip-only crédible (précision quasi
identique) si l'environnement cible interdit toute dépendance système.

**PaddleOCR a échoué sur les 8 images**, de façon reproductible sur deux
runs indépendants : `NotImplementedError:
ConvertPirAttribute2RuntimeAttribute not support [...]`, une incompatibilité
interne du moteur d'inférence PaddlePaddle (exécuteur "PIR") avec cette
configuration Windows/CPU/oneDNN — pas un bug de notre code (confirmé après
correction d'un premier problème d'API, `show_log`/`use_angle_cls` retirés
dans la version installée, et tentative de désactivation de l'accélération
oneDNN, sans effet). C'est en soi un résultat de benchmark valide : ajouter
PaddleOCR au projet introduit un risque d'intégration réel, pas seulement
théorique, cohérent avec l'hypothèse de départ ("second framework deep
learning, plus de friction").

### Décision retenue

**Tesseract**, choix empiriquement le plus fort des trois : précision
parfaite sur le jeu de test, le plus rapide au chargement comme à
l'inférence. La dépendance au binaire système est un compromis assumé et
documenté (installation triviale en production Linux), pas un blocage.

## Décisions finales — Phase 0

| Composant | Modèle retenu | Justification |
|---|---|---|
| OCR (`ocr_service.py`) | **Tesseract** (`pytesseract`) | Précision parfaite + le plus rapide, sur données synthétiques représentatives des catégories cibles |
| Captioning (`vision_service.py`) | **BLIP-base** | Meilleur des 3 sur CLIP score (ρ=0.73 avec jugement humain) et sur l'évaluation humaine directe ; le plus rapide en inférence. Prévoir `no_repeat_ngram_size=3` à la génération pour éviter la dégénérescence par répétition observée sur les images hors-distribution |
| `image_type` (classification) | Zero-shot (pattern `topics.py`) | Pas de benchmark séparé nécessaire — réutilisation directe d'un modèle déjà en production dans le pipeline NLP existant |
| `business_relevance` | Réutilisation de `BusinessClassifier` | Idem — pas de calcul séparé |

Prochaine étape : implémentation Phase 1 (`ocr_service.py` avec Tesseract +
`image_processor.py` en mode OCR-only), conformément au plan approuvé.
