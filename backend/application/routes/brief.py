"""
Monday Brief — résumé narratif hebdomadaire.
LLM_PROVIDER=ollama → Ollama local (défaut)
LLM_PROVIDER=azure  → GPT-4o + MCP tools (dynamique)
"""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from core.models import User
from core.security import require_plan
from core.store import OrgScopedItemStore
from data.analytics.engine import compute_overview, compute_daily_insights
from intelligence.llm.client import complete, get_provider_info

router = APIRouter(prefix="/brief", tags=["brief"])

BRIEF_SYSTEM_FR = """Tu es l'assistant IA personnel d'un CEO d'entreprise.
Ta tâche est de rédiger un brief exécutif hebdomadaire concis et perspicace en français.
Adopte un ton professionnel et direct — comme un conseiller de confiance qui parle à un CEO.
Concentre-toi sur ce qui compte : risques, décisions nécessaires, signaux positifs, signaux équipe.
Structure : 3-4 paragraphes courts. Prose claire et fluide. Pas de listes à puces. Pas d'en-têtes.
Mise en forme : utilise **gras** pour mettre en valeur les chiffres clés, les noms de sources importantes, les alertes critiques et les mots d'action essentiels.
Termine par une recommandation concrète pour la semaine.
IMPORTANT : Tu DOIS rédiger le brief directement avec les données fournies. Ne pose aucune question. Ne demande pas de confirmation. Génère le texte immédiatement."""

BRIEF_SYSTEM_EN = """You are the personal AI assistant of a company CEO.
Your task is to write a concise and insightful weekly executive brief in English.
Adopt a professional and direct tone — like a trusted advisor speaking to a CEO.
Focus on what matters: risks, required decisions, positive signals, team signals.
Structure: 3-4 short paragraphs. Clear flowing prose. No bullet points. No headers.
Formatting: use **bold** to highlight key figures, important source names, critical alerts, and essential action words.
End with a concrete recommendation for the week.
IMPORTANT: You MUST write the brief directly using the provided data. Do not ask questions. Do not ask for confirmation. Generate the text immediately."""


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
async def weekly_brief(
    since_days: int = 7,
    lang: str = "fr",
    current_user: User = Depends(require_plan("brief")),
):
    """Génère un brief narratif de la semaine — données scoped à l'org du CEO."""
    now        = datetime.utcnow()
    brief_days = max(since_days, 7)
    period     = f"{(now - timedelta(days=brief_days)).strftime('%d/%m')} – {now.strftime('%d/%m/%Y')}"

    store = OrgScopedItemStore(current_user.org_id)
    stats = compute_overview(store, since_days=brief_days)

    system = BRIEF_SYSTEM_EN if lang == "en" else BRIEF_SYSTEM_FR
    prompt     = _build_brief_prompt(stats, period)
    brief_text = await complete(
        system=system,
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


# ── Daily Brief — "3 choses qui nécessitent votre attention aujourd'hui" ──────

DAILY_SYSTEM_FR = """Tu es l'assistant IA personnel d'un CEO. On te donne 1 à 3 signaux
détectés automatiquement dans ses données (Gmail, Slack, Jira...), avec les faits
et preuves déjà calculés. Ta seule tâche : reformuler chaque signal en français
clair et direct, pour un CEO pressé.

Réponds STRICTEMENT en JSON, un tableau d'objets dans le même ordre que les
signaux fournis, sans aucun texte avant/après, format exact :
[{"what_happened": "...", "why_it_matters": "...", "recommendation": "..."}]

Règles :
- "what_happened" : 1 phrase, ce qui s'est passé, factuel.
- "why_it_matters" : 1-2 phrases, pourquoi le CEO doit s'en soucier maintenant.
- "recommendation" : 1 phrase, action concrète et spécifique à recommander.
- N'invente AUCUN chiffre, nom ou fait qui n'est pas dans les données fournies.
- Pas de listes à puces, pas de markdown, pas de gras."""

DAILY_SYSTEM_EN = """You are the personal AI assistant of a CEO. You're given 1 to 3
automatically detected signals from their data (Gmail, Slack, Jira...), with facts
and evidence already computed. Your only task: rephrase each signal into clear,
direct English for a busy CEO.

Respond STRICTLY in JSON, an array of objects in the same order as the provided
signals, no text before/after, exact format:
[{"what_happened": "...", "why_it_matters": "...", "recommendation": "..."}]

Rules:
- "what_happened": 1 sentence, what happened, factual.
- "why_it_matters": 1-2 sentences, why the CEO should care right now.
- "recommendation": 1 sentence, concrete and specific action to recommend.
- Do NOT invent any number, name, or fact not present in the given data.
- No bullet points, no markdown, no bold."""


def _build_daily_prompt(candidates: list[dict]) -> str:
    blocks = []
    for idx, c in enumerate(candidates, 1):
        evidence = "\n".join(f"- {e}" for e in c["evidence"]) or "- (aucune preuve additionnelle)"
        blocks.append(
            f"Signal {idx} — {c['title']}\n"
            f"Preuves :\n{evidence}\n"
            f"Impact mesuré : {c.get('impact_estimate') or 'non chiffré'}"
        )
    return "\n\n".join(blocks) + "\n\nRédige le JSON maintenant."


def _parse_daily_narratives(raw: str, expected: int) -> list[dict]:
    """Parse best-effort du JSON renvoyé par le LLM. Ne lève jamais — retourne
    des dicts vides (fallback déterministe) si le parsing échoue."""
    text = (raw or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            out = [p if isinstance(p, dict) else {} for p in parsed]
            while len(out) < expected:
                out.append({})
            return out[:expected]
    except Exception:
        pass
    return [{} for _ in range(expected)]


ACTIONS = ["create_meeting", "send_message", "create_task", "ignore", "remind_tomorrow"]


@router.get("/daily")
async def daily_brief(
    lang: str = "fr",
    since_days: int = 14,
    current_user: User = Depends(require_plan("brief")),
):
    """
    Daily Brief — jusqu'à 3 insights nécessitant l'attention du CEO aujourd'hui.
    Les faits (preuves, chiffres, heures) sont calculés de façon déterministe
    (compute_daily_insights) ; le LLM ne fait que les reformuler en prose. Si le
    LLM échoue, les champs déterministes restent affichés (jamais de page vide).
    """
    now   = datetime.utcnow()
    store = OrgScopedItemStore(current_user.org_id)
    candidates = compute_daily_insights(store, org_id=current_user.org_id, since_days=since_days)

    if not candidates:
        return {
            "generated_at": now.isoformat(),
            "provider":     get_provider_info()["provider"],
            "insights":     [],
        }

    system = DAILY_SYSTEM_EN if lang == "en" else DAILY_SYSTEM_FR
    prompt = _build_daily_prompt(candidates)
    raw = await complete(
        system=system, user=prompt, use_tools=False, temperature=0.3, max_tokens=700,
    )
    narratives = _parse_daily_narratives(raw, len(candidates))

    insights = []
    for cand, narr in zip(candidates, narratives):
        insights.append({
            "id":              cand["id"],
            "type":            cand["type"],
            "title":           cand["title"],
            "what_happened":   narr.get("what_happened") or cand["title"],
            "why_it_matters":  narr.get("why_it_matters") or " · ".join(cand["evidence"]),
            "evidence":        cand["evidence"],
            "impact":          cand.get("impact_estimate") or "",
            "recommendation":  narr.get("recommendation") or "",
            "source_items":    cand["source_items"],
            "actions":         ACTIONS,
        })

    return {
        "generated_at": now.isoformat(),
        "provider":     get_provider_info()["provider"],
        "insights":     insights,
    }
