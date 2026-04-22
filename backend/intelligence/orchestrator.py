"""
AI Orchestrator — cerveau central d'InsightFlow Executive.

Reçoit un contexte post-sync, combine règles déterministes + LLM
pour décider quelles tâches déclencher ensuite.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationContext:
    """Snapshot du contexte à l'instant T, après un sync."""
    source: str
    new_items: int
    total_recent: int
    negative_pct: float          # 0.0 – 1.0
    high_burnout_count: int
    urgent_count: int
    risk_count: int              # Blocked + Urgent + Risk + Conflict
    is_monday_morning: bool
    corrections_pending: int     # corrections humaines non encore utilisées
    drift_detected: bool         # % négatif > seuil baseline


@dataclass
class OrchestrationDecision:
    """Actions décidées par l'orchestrateur."""
    should_alert: bool = False
    alert_level: str = "info"       # info | warning | critical
    alert_reason: str = ""
    should_generate_brief: bool = False
    should_retrain: bool = False
    retrain_task: str = "sentiment"
    should_index_rag: bool = False
    priority_actions: list[str] = field(default_factory=list)
    ai_commentary: str = ""
    decided_at: str = ""


class AIOrchestrator:
    """
    Orchestre les tâches async en fonction du contexte.

    Logique :
      1. Règles déterministes rapides (toujours exécutées)
      2. Commentaire LLM optionnel (seulement si événement significatif)
    """

    # ── Seuils configurables ────────────────────────────────────────────
    CRITICAL_NEGATIVE_PCT  = 0.40
    CRITICAL_URGENT_COUNT  = 5
    WARNING_NEGATIVE_PCT   = 0.25
    WARNING_BURNOUT_COUNT  = 3
    MIN_ITEMS_FOR_BRIEF    = 10
    MIN_CORRECTIONS_RETRAIN = 20
    MIN_ITEMS_FOR_RAG      = 5

    def analyze(self, ctx: OrchestrationContext) -> OrchestrationDecision:
        """Règles déterministes — pas d'I/O, toujours synchrone."""
        d = OrchestrationDecision(decided_at=datetime.utcnow().isoformat())

        # Alertes
        if ctx.negative_pct >= self.CRITICAL_NEGATIVE_PCT or ctx.urgent_count >= self.CRITICAL_URGENT_COUNT:
            d.should_alert  = True
            d.alert_level   = "critical"
            d.alert_reason  = (
                f"{ctx.urgent_count} messages urgents — "
                f"{round(ctx.negative_pct * 100)}% sentiment négatif"
            )
        elif ctx.negative_pct >= self.WARNING_NEGATIVE_PCT or ctx.high_burnout_count >= self.WARNING_BURNOUT_COUNT:
            d.should_alert  = True
            d.alert_level   = "warning"
            d.alert_reason  = (
                f"{ctx.high_burnout_count} signaux burnout — "
                f"{round(ctx.negative_pct * 100)}% sentiment négatif"
            )

        # Monday Brief
        if ctx.is_monday_morning and ctx.total_recent >= self.MIN_ITEMS_FOR_BRIEF:
            d.should_generate_brief = True

        # Retraining
        if ctx.corrections_pending >= self.MIN_CORRECTIONS_RETRAIN or ctx.drift_detected:
            d.should_retrain = True
            d.retrain_task   = "sentiment"

        # Indexation RAG
        if ctx.new_items >= self.MIN_ITEMS_FOR_RAG:
            d.should_index_rag = True

        # Actions prioritaires (affichées dans l'UI)
        if ctx.risk_count > 0:
            d.priority_actions.append(
                f"{ctx.risk_count} élément(s) à risque détecté(s) depuis {ctx.source}"
            )
        if ctx.high_burnout_count > 0:
            d.priority_actions.append(
                f"{ctx.high_burnout_count} signal(aux) burnout à surveiller"
            )
        if d.should_retrain:
            d.priority_actions.append(
                f"Retraining suggéré ({ctx.corrections_pending} corrections en attente)"
            )

        return d

    async def analyze_with_llm(self, ctx: OrchestrationContext) -> OrchestrationDecision:
        """Règles + commentaire LLM (appelé seulement si événement significatif)."""
        d = self.analyze(ctx)

        # Appel LLM uniquement si l'événement mérite un commentaire
        if not (d.should_alert or d.should_generate_brief or ctx.new_items >= 20):
            return d

        try:
            from intelligence.llm.client import complete

            prompt = f"""Analyse post-synchronisation InsightFlow — source : {ctx.source}

Données :
- Nouveaux éléments synchro : {ctx.new_items}
- Messages analysés (90j) : {ctx.total_recent}
- Sentiment négatif : {round(ctx.negative_pct * 100)}%
- Messages urgents : {ctx.urgent_count}
- Signaux burnout (score ≥ 0.7) : {ctx.high_burnout_count}
- Éléments à risque : {ctx.risk_count}
- Lundi matin : {"oui" if ctx.is_monday_morning else "non"}

Décisions automatiques :
- Alerte déclenchée : {"oui (" + d.alert_level + ")" if d.should_alert else "non"}
- Brief hebdo : {"oui" if d.should_generate_brief else "non"}
- Retraining modèle : {"oui" if d.should_retrain else "non"}

Donne un commentaire exécutif en 2 phrases maximum. Ton direct, sans markdown."""

            d.ai_commentary = await complete(
                system="Tu es l'assistant IA d'un CEO. Réponds en français, 2 phrases max, ton direct.",
                user=prompt,
                use_tools=False,
                temperature=0.2,
                max_tokens=120,
            )
        except Exception as e:
            logger.warning("[Orchestrator] LLM unavailable: %s", e)

        return d
