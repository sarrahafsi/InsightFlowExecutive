"""
AI Recommendations — Agent proposals based on real message feature extraction.
Analyses recurring patterns, bottlenecks, and action types to suggest
intelligent agents and automation workflows.
"""
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from core.models import User
from core.security import get_current_user
from core.store import OrgScopedItemStore
from data.analytics.engine import compute_overview
from intelligence.llm.client import complete, get_provider_info

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

# ── Action word patterns to detect in message subjects ──────────────────────
ACTION_PATTERNS = [
    ("validation / approbation", ["approv", "valid", "approbation", "autorisation", "sign off", "approve"]),
    ("demande de réunion",       ["meeting", "réunion", "call", "sync", "rendez-vous", "rdv", "agenda"]),
    ("suivi / relance",          ["follow", "suivi", "relance", "reminder", "rappel", "update", "statut"]),
    ("blocage / aide",           ["block", "bloqué", "stuck", "help", "aide", "urgent", "asap", "critical"]),
    ("rapport / compte-rendu",   ["report", "rapport", "summary", "résumé", "bilan", "compte-rendu", "cr"]),
    ("livraison / deadline",     ["deadline", "deliver", "livraison", "due", "échéance", "retard", "delay"]),
]


def _extract_message_features(store: OrgScopedItemStore, since_days: int) -> dict:
    """Extract actionable features from raw messages for agent proposal generation."""
    since = datetime.utcnow() - timedelta(days=since_days)
    items = store.all(since=since, limit=60)

    # ── Label distribution ───────────────────────────────────────────────────
    by_label: dict[str, int] = Counter(
        item.metadata.get("business_label", "Neutral") for item in items
    )

    # ── Top senders ──────────────────────────────────────────────────────────
    sender_counts: Counter = Counter()
    for item in items:
        if item.author:
            sender_counts[item.author] += 1
    top_senders = [{"name": n, "count": c} for n, c in sender_counts.most_common(5)]

    # ── Action pattern detection in subjects ─────────────────────────────────
    matched_patterns: Counter = Counter()
    for item in items:
        title_lower = (item.title or "").lower()
        for pattern_name, keywords in ACTION_PATTERNS:
            if any(kw in title_lower for kw in keywords):
                matched_patterns[pattern_name] += 1

    # ── Critical message samples (title + label + author + source) ───────────
    critical_labels = {"Blocked", "Urgent", "Risk", "Conflict", "Overload"}
    critical_messages = [
        {
            "title":  (item.title or "")[:90],
            "label":  item.metadata.get("business_label", ""),
            "author": item.author or "",
            "source": item.source or "",
            "reason": item.metadata.get("business_reason", ""),
        }
        for item in items
        if item.metadata.get("business_label") in critical_labels
    ][:8]

    # ── Topic distribution ────────────────────────────────────────────────────
    topic_counts: Counter = Counter(
        item.metadata.get("topic", "")
        for item in items
        if item.metadata.get("topic")
    )
    top_topics = dict(topic_counts.most_common(5))

    # ── Source distribution ───────────────────────────────────────────────────
    source_counts: Counter = Counter(item.source for item in items if item.source)

    # ── Time patterns ─────────────────────────────────────────────────────────
    after_hours = sum(1 for item in items if item.metadata.get("is_after_hours"))
    weekend     = sum(1 for item in items if item.metadata.get("is_weekend"))

    # ── Repeat senders in critical messages ───────────────────────────────────
    critical_senders = Counter(
        m["author"] for m in critical_messages if m["author"]
    )

    return {
        "total":             len(items),
        "by_label":          dict(by_label),
        "top_senders":       top_senders,
        "action_patterns":   dict(matched_patterns.most_common(4)),
        "critical_messages": critical_messages,
        "critical_senders":  dict(critical_senders.most_common(3)),
        "top_topics":        top_topics,
        "top_sources":       dict(source_counts.most_common(4)),
        "after_hours_count": after_hours,
        "weekend_count":     weekend,
    }


# ── System prompt ────────────────────────────────────────────────────────────
RECO_SYSTEM = """Tu es un architecte de solutions IA spécialisé dans l'automatisation du travail exécutif.

À partir des patterns détectés dans les messages de l'organisation, propose des agents intelligents ou des workflows d'automatisation concrets qui vont réellement faciliter le travail du CEO et de son équipe.

RÈGLES STRICTES :
- Ne parle JAMAIS de sentiments, émotions ou humeur
- Concentre-toi sur les PATTERNS DE TRAVAIL : tâches répétitives, goulots d'étranglement, types d'actions récurrentes
- Chaque proposition doit être un agent ou workflow spécifique et immédiatement utile
- Base chaque proposition sur les patterns réels détectés dans les données

Types de solutions possibles :
- agent : un agent IA autonome qui prend en charge une tâche récurrente
- workflow : un processus automatisé déclenché par un événement
- alerte : un système de détection et notification intelligent
- rapport : un rapport automatique généré selon un pattern détecté

Réponds UNIQUEMENT avec un tableau JSON valide, sans texte autour :
[{
  "priority": "critique|urgent|important",
  "agent_name": "Nom court et clair de l'agent ou solution",
  "type": "agent|workflow|alerte|rapport",
  "trigger": "Pattern exact détecté dans les données qui justifie cette proposition (sois précis : cite des chiffres ou patterns)",
  "action": "Ce que l'agent ou workflow fait concrètement, étape par étape (2-3 phrases max)",
  "benefit": "Gain mesurable : temps économisé, réduction de friction, visibilité gagnée"
}]
Génère exactement 4 propositions pertinentes et différentes."""


def _build_reco_prompt(features: dict, stats: dict, period: str) -> str:
    bl       = features.get("by_label", {})
    critical = features.get("critical_messages", [])
    senders  = features.get("top_senders", [])
    patterns = features.get("action_patterns", {})
    topics   = features.get("top_topics", {})
    sources  = features.get("top_sources", {})

    label_lines = "\n".join(f"  - {label}: {count} messages" for label, count in bl.items() if count > 0)
    senders_str = ", ".join(f"{s['name']} ({s['count']} msgs)" for s in senders[:4]) or "Aucun"
    patterns_str = "\n".join(f"  - {k}: {v} messages" for k, v in patterns.items()) or "  Aucun détecté"
    topics_str   = ", ".join(f"{k} ({v})" for k, v in topics.items()) or "Non disponible"
    sources_str  = ", ".join(f"{k} ({v} msgs)" for k, v in sources.items()) or "Non disponible"

    critical_str = "\n".join(
        f"  - [{m['label']}] \"{m['title']}\" — {m['author']} via {m['source']}"
        + (f" | Raison : {m['reason']}" if m.get("reason") else "")
        for m in critical
    ) or "  Aucun message critique"

    return f"""Analyse des messages de l'organisation ({period}) :

Total messages analysés : {features.get('total', 0)}
Sources actives : {sources_str}

Distribution par type de message :
{label_lines}

Patterns d'actions détectés dans les sujets :
{patterns_str}

Expéditeurs les plus actifs : {senders_str}
Sujets récurrents : {topics_str}

Messages critiques (nécessitant une action) :
{critical_str}

Activité hors horaires : {features.get('after_hours_count', 0)} messages
Activité week-end : {features.get('weekend_count', 0)} messages
Indice de risque global : {stats.get('risk_index', 0)}/100

Sur la base de ces patterns, propose 4 agents ou solutions d'automatisation."""


# ── Route ─────────────────────────────────────────────────────────────────────
@router.get("")
async def get_recommendations(
    since_days: int = 7,
    current_user: User = Depends(get_current_user),
):
    now    = datetime.utcnow()
    period = f"{(now - timedelta(days=since_days)).strftime('%d/%m')} – {now.strftime('%d/%m/%Y')}"

    store    = OrgScopedItemStore(current_user.org_id)
    stats    = compute_overview(store, since_days=since_days)
    features = _extract_message_features(store, since_days=since_days)
    prompt   = _build_reco_prompt(features, stats, period)

    raw = await complete(
        system=RECO_SYSTEM,
        user=prompt,
        use_tools=False,
        temperature=0.3,
        max_tokens=800,
    )

    recommendations = []
    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            recommendations = json.loads(match.group())
    except Exception:
        recommendations = [{
            "priority":   "important",
            "agent_name": "Analyse indisponible",
            "type":       "agent",
            "trigger":    "",
            "action":     raw[:200] if raw else "Erreur de génération.",
            "benefit":    "",
        }]

    return {
        "period":          period,
        "generated_at":    now.isoformat(),
        "provider":        get_provider_info()["provider"],
        "features_used":   {
            "total_messages": features["total"],
            "patterns_found": list(features["action_patterns"].keys()),
        },
        "recommendations": recommendations,
    }
