"""
Monday Brief — résumé narratif hebdomadaire.
LLM_PROVIDER=ollama → Ollama local (défaut)
LLM_PROVIDER=azure  → GPT-4o + MCP tools (dynamique)
"""
from datetime import datetime, timedelta
from fastapi import APIRouter
from application.deps import item_store
from data.analytics.engine import compute_overview
from intelligence.llm.client import complete, get_provider_info

router = APIRouter(prefix="/brief", tags=["brief"])

BRIEF_SYSTEM = """Tu es l'assistant IA personnel d'un CEO d'entreprise.
Ta tâche est de rédiger un brief exécutif hebdomadaire concis et perspicace en français.
Adopte un ton professionnel et direct — comme un conseiller de confiance qui parle à un CEO.
Concentre-toi sur ce qui compte : risques, décisions nécessaires, signaux positifs, signaux équipe.
Structure : 3-4 paragraphes courts. Pas de listes à puces. Pas d'en-têtes markdown. Prose claire.
Termine par une recommandation concrète pour la semaine.
IMPORTANT : Tu DOIS rédiger le brief directement avec les données fournies. Ne pose aucune question. Ne demande pas de confirmation. Génère le texte immédiatement."""

BRIEF_SYSTEM_MCP = """Tu es l'assistant IA personnel d'un CEO d'entreprise.
Ta tâche est de rédiger un brief exécutif hebdomadaire en français.
Tu as accès à des outils pour récupérer les données réelles de la semaine.
Utilise les outils disponibles pour collecter : analytics, emails urgents, risques, burnout.
Ensuite rédige un brief concis en 3-4 paragraphes. Prose claire, pas de listes ni markdown.
Termine par une recommandation concrète. Si une donnée manque, ne l'invente pas."""


def _build_brief_prompt(stats: dict, period: str) -> str:
    intel     = stats.get("intelligence", {})
    sentiment = stats.get("sentiment", {})
    bl        = intel.get("business_labels", [])
    risk_items= intel.get("at_risk_items", [])[:3]
    burnout   = intel.get("burnout", {})

    label_summary = ", ".join(
        f"{b['label']} ({b['count']})" for b in bl if b["count"] > 0
    ) or "Aucune classification disponible"

    risk_msgs = "\n".join(
        f"- [{r['business_label']}] {r['title']} (de {r['author']})"
        for r in risk_items
    ) or "Aucun message critique"

    return f"""Données de la semaine ({period}) :

Total messages analysés : {stats.get('total_items', 0)}
Sentiment : {sentiment.get('positive', 0)}% positif, {sentiment.get('negative', 0)}% négatif, {sentiment.get('neutral', 0)}% neutre
Indice de risque : {stats.get('risk_index', 0)}/100
Vélocité : {stats.get('velocity', {}).get('this_week', 0)} messages cette semaine vs {stats.get('velocity', {}).get('last_week', 0)} la semaine dernière

Catégories business : {label_summary}

Messages à risque :
{risk_msgs}

Signaux comportementaux :
- Hors horaires : {burnout.get('after_hours_count', 0)} ({burnout.get('after_hours_rate', 0)}%)
- Week-end : {burnout.get('weekend_count', 0)} ({burnout.get('weekend_rate', 0)}%)
- Score burnout moyen : {int(burnout.get('avg_burnout_score', 0) * 100)}%

Rédige maintenant le brief exécutif hebdomadaire."""


@router.get("/weekly")
async def weekly_brief(since_days: int = 7):
    """Génère un brief narratif de la semaine."""
    now    = datetime.utcnow()
    # Brief always covers 7 days regardless of dashboard filter — needs enough data for narrative
    brief_days = max(since_days, 7)
    period = f"{(now - timedelta(days=brief_days)).strftime('%d/%m')} – {now.strftime('%d/%m/%Y')}"
    stats  = compute_overview(item_store, since_days=brief_days)

    # Tous les providers utilisent les stats pré-calculées — plus fiable que les MCP tools
    prompt     = _build_brief_prompt(stats, period)
    brief_text = await complete(
        system=BRIEF_SYSTEM,
        user=prompt,
        use_tools=False,
        temperature=0.4,
        max_tokens=700,
    )

    return {
        "period":       period,
        "since_days":   since_days,
        "generated_at": now.isoformat(),
        "provider":     get_provider_info()["provider"],
        "stats_summary": {
            "total_items": stats.get("total_items", 0),
            "risk_index":  stats.get("risk_index", 0),
            "sentiment":   stats.get("sentiment", {}),
            "velocity":    stats.get("velocity", {}),
            "climate":     stats.get("intelligence", {}).get("climate_label", ""),
        },
        "brief": brief_text,
    }
