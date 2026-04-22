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
Si tu n'as pas assez de données, dis-le honnêtement."""

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
    period = f"{(now - timedelta(days=since_days)).strftime('%d/%m')} – {now.strftime('%d/%m/%Y')}"
    stats  = compute_overview(item_store, since_days=since_days)

    provider_info = get_provider_info()
    provider_name = provider_info["provider"]

    if provider_name == "azure":
        # GPT-4o : utilise les MCP tools pour collecter les données dynamiquement
        user_msg = (
            f"Nous sommes le {now.strftime('%d/%m/%Y')}. "
            f"Génère le brief exécutif de la semaine ({period}). "
            f"Utilise tes outils pour collecter les données réelles : "
            f"analytics, emails urgents, risques, signaux burnout."
        )
        brief_text = await complete(
            system=BRIEF_SYSTEM_MCP,
            user=user_msg,
            use_tools=True,
            temperature=0.4,
            max_tokens=700,
        )
    else:
        # Ollama : prompt avec stats pré-calculées
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
        "provider":     provider_name,
        "stats_summary": {
            "total_items": stats.get("total_items", 0),
            "risk_index":  stats.get("risk_index", 0),
            "sentiment":   stats.get("sentiment", {}),
            "velocity":    stats.get("velocity", {}),
            "climate":     stats.get("intelligence", {}).get("climate_label", ""),
        },
        "brief": brief_text,
    }
