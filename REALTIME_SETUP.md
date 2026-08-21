# Setup Temps Réel — InsightFlow

## 1. Démarrer le backend + frontend (normal)

```bash
# Terminal 1
cd backend && uvicorn main:app --reload

# Terminal 2
cd frontend && node node_modules/next/dist/bin/next start --port 3001
```

Le dashboard se connecte automatiquement au WebSocket (`ws://localhost:8000/ws`).
Le point vert en bas de la sidebar confirme la connexion.

---

## 2. ngrok — exposer localhost sur internet (pour les webhooks)

### Installation
```bash
# Windows (winget)
winget install ngrok.ngrok

# Ou télécharger sur https://ngrok.com/download
```

### Lancer ngrok
```bash
ngrok http 8000
# → Forwarding https://abc123.ngrok-free.app → localhost:8000
```

Copie l'URL HTTPS (ex: `https://abc123.ngrok-free.app`).

### Ajouter l'URL dans .env
```env
WEBHOOK_BASE_URL=https://abc123.ngrok-free.app
```

---

## 3. Gmail — Push Notifications (Google Pub/Sub)

### Étapes Google Cloud (5-10 min)

1. Aller sur https://console.cloud.google.com
2. Activer l'API Gmail (déjà fait si tu as OAuth)
3. **Activer l'API Pub/Sub** : APIs & Services → Enable APIs → "Cloud Pub/Sub API"
4. Créer un topic :
   ```
   Pub/Sub → Topics → Create Topic
   Topic ID : gmail-push
   → Note l'ARN complet : projects/TON_PROJECT_ID/topics/gmail-push
   ```
5. Créer une subscription push :
   ```
   Subscriptions → Create Subscription
   Type : Push
   Endpoint URL : https://abc123.ngrok-free.app/webhooks/gmail
   ```
6. Donner permission à Gmail de publier :
   ```
   Topic → Permissions → Add Principal
   Principal : gmail-api-push@system.gserviceaccount.com
   Role : Pub/Sub Publisher
   ```

### Ajouter dans .env
```env
GMAIL_PUBSUB_TOPIC=projects/TON_PROJECT_ID/topics/gmail-push
```

### Activer le watch Gmail (une fois au démarrage ou via API)
```bash
curl -X POST http://localhost:8000/webhooks/gmail/watch
```
Réponse attendue :
```json
{"status": "ok", "history_id": "...", "expiration": "..."}
```
> Le watch expire après 7 jours — relancer cette commande chaque semaine.

---

## 4. Slack — Events API (30 min)

1. Aller sur https://api.slack.com/apps → ton app InsightFlow
2. **Event Subscriptions** → Enable Events
3. Request URL : `https://abc123.ngrok-free.app/webhooks/slack`
   - Slack va envoyer un challenge → le backend répond automatiquement ✓
4. Subscribe to bot events :
   - `message.channels`
   - `message.groups`
   - `message.im` (messages directs)
5. **Reinstall** l'app dans ton workspace

### Ajouter dans .env
```env
SLACK_SIGNING_SECRET=ton_signing_secret  # Settings → Basic Information → Signing Secret
```

---

## 5. Jira — Webhooks (15 min)

1. Jira → Settings (icône ⚙️) → System → WebHooks
2. **Create WebHook** :
   - Name : InsightFlow Realtime
   - URL : `https://abc123.ngrok-free.app/webhooks/jira`
   - Events : ✓ Issue Created, ✓ Issue Updated
   - JQL Filter : `project = TON_PROJET` (optionnel)

---

## Résumé des variables .env à ajouter

```env
# Temps réel
WEBHOOK_BASE_URL=https://abc123.ngrok-free.app
GMAIL_PUBSUB_TOPIC=projects/TON_PROJECT_ID/topics/gmail-push
SLACK_SIGNING_SECRET=ton_slack_signing_secret
AUTO_SYNC_INTERVAL=120  # secondes entre chaque auto-sync (défaut: 120)
```

---

## Test rapide sans webhooks

Même sans configurer Gmail/Slack/Jira, le dashboard se met à jour automatiquement toutes les 2 minutes via la boucle d'auto-sync. Le point vert confirme la connexion WebSocket active.

Pour tester les notifications manuellement :
```bash
# Déclencher une sync manuelle (simule une arrivée de données)
curl -X POST http://localhost:8000/api/sync -H "Content-Type: application/json" -d '{"since_days": 1}'
```
→ Le frontend reçoit l'event `sync_complete` et met à jour les KPIs sans rechargement.
