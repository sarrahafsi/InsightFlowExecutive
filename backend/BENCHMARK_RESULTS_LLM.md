# Benchmark LLM — Ollama (local) vs Groq (cloud)

Justification empirique du fournisseur LLM utilisé pour générer les réponses
du CEO (`intelligence/llm/client.py`). En place : **Ollama local**
(llama3.2:3b) — un commentaire déjà présent dans le code de production
signalait "Ollama sur CPU est lent — cap à 400 tokens et timeout généreux".
Question : un service cloud rapide (Groq, matériel dédié LPU) justifie-t-il
de sortir du 100% local ?

Script : `benchmark_llm.py`. Résultats : `benchmark_llm_results.csv`,
`benchmark_llm_detail.csv`.

## Résumé

| Fournisseur | Latence moyenne | Latence p95 | Débit | Mots-clés attendus trouvés | Format respecté |
|---|---|---|---|---|---|
| **Ollama (llama3.2:3b, local)** | 36.3s | 48.0s | 8.3 tokens/sec | 100% | 100% |
| **Groq (openai/gpt-oss-20b, cloud)** | **1.1s** | **1.6s** | **365 tokens/sec** | 96% | 100% |

Groq répond **~32× plus vite** et génère **~44× plus de tokens par
seconde**, pour une qualité de réponse quasi identique.

## Méthodologie

- **8 scénarios réalistes**, construits sur le même patron que la vraie route
  `/api/ask` en mode RAG : `system` = `SYSTEM_ANALYST` (prompt de production
  exact, copié depuis `application/routes/ask.py`), `user` = contexte de
  messages simulés + question du CEO — pas des prompts jouets.
- Pour chaque scénario, une **liste de mots-clés attendus** est définie à
  l'avance (vérité terrain, ex. pour "Y a-t-il un litige sur une facture ?" :
  `["facture", "client", "litige"]`) — permet une évaluation automatique et
  objective, comme les benchmarks OCR/Vision de Phase 0.
- **Note d'honnêteté** : le modèle Groq prévu initialement
  (`llama-3.1-8b-instant`) n'existe plus dans le catalogue Groq (vérifié via
  l'API `/v1/models` le 07/09/2026 — plus aucun modèle Llama disponible).
  Remplacé par `openai/gpt-oss-20b`, le plus proche en taille (20B) parmi les
  modèles restants.
- La clé API Groq est lue depuis la variable d'environnement `GROQ_API_KEY`,
  jamais codée en dur ni journalisée.

## Les métriques, expliquées

| Métrique | Ce qu'elle mesure |
|---|---|
| **Latence moyenne / p95** | Le temps entre l'envoi de la question et la réponse complète. La p95 est le pire cas observé sur 8 essais (pour repérer les ralentissements occasionnels). |
| **Débit (tokens/sec)** | La vitesse de génération pure du modèle — combien de "mots" (tokens) il produit par seconde une fois lancé. Mesuré nativement par chaque fournisseur (`eval_count`/`eval_duration` pour Ollama, `usage.completion_tokens` pour Groq), pas estimé. |
| **Mots-clés attendus trouvés** | Sur les mots-clés qu'une bonne réponse devrait contenir (définis à l'avance), quelle fraction apparaît réellement dans la réponse du modèle. |
| **Format respecté** | Le prompt système impose 3 sections obligatoires (`**Analyse des messages**`, `**Projections et recommandations**`, `**Prochaines étapes**`) — mesure si le modèle suit bien cette consigne de structure. |

## Constats

**1. L'écart de vitesse est massif et change l'expérience utilisateur.**
36 secondes d'attente (Ollama, CPU) contre ~1 seconde (Groq) pour une
question posée dans le dashboard — la différence entre "ça rame" et
"instantané" pour une fonctionnalité de type chat.

**2. La qualité ne se dégrade quasiment pas.** 96% des mots-clés attendus
retrouvés contre 100% pour Ollama — un seul mot-clé secondaire manquant sur
8 scénarios, un écart qui n'est pas significatif statistiquement à cette
échelle de test. Le respect du format imposé est parfait des deux côtés.

**3. Le compromis n'est pas la qualité, mais la confidentialité et le
coût.** Ollama tourne 100% en local — aucune donnée de l'entreprise ne sort
de la machine. Groq est un service cloud tiers : le contexte RAG (messages
de l'entreprise injectés dans le prompt) transiterait par leurs serveurs, et
l'usage a un coût au-delà du free tier (tarifs à vérifier sur
console.groq.com, sujets à changement — l'API a par exemple retiré tous ses
modèles Llama entre la conception du benchmark et son exécution).

## Décision retenue

**Pas de changement du fournisseur par défaut (`Ollama` reste le mode
"gratuit, local").** Le gain de vitesse de Groq est réel et important, mais
implique d'envoyer les données de l'entreprise (emails, tickets, messages
Slack) à un service tiers — une décision qui dépasse un choix technique et
doit être validée explicitement par l'utilisateur, pas activée par défaut.

**Recommandation** : proposer Groq comme **option supplémentaire**
sélectionnable par l'utilisateur (à côté de `ollama` / `openai` / `azure`
dans `LLM_PROVIDER`), avec un avertissement explicite sur l'envoi de données
à l'extérieur — pas comme remplacement silencieux d'Ollama. Ce changement de
code n'a pas été appliqué (contrairement au benchmark embeddings) : c'est un
choix produit/confidentialité, pas seulement une question de performance.
