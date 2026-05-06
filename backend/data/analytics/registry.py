"""Maps source names to their analytics compute functions."""

from integrations.connectors.schemas import SourceType
from data.analytics.engine import compute_gmail, compute_generic, compute_jira, compute_outlook

ANALYTICS_REGISTRY: dict[str, any] = {
    "gmail":   lambda store, since_days: compute_gmail(store, since_days),
    "slack":   lambda store, since_days: compute_generic(store, SourceType.SLACK, since_days),
    "jira":    lambda store, since_days: compute_jira(store, since_days),
    "teams":   lambda store, since_days: compute_generic(store, SourceType.TEAMS, since_days),
    "clickup": lambda store, since_days: compute_generic(store, SourceType.CLICKUP, since_days),
    "outlook": lambda store, since_days: compute_outlook(store, since_days),
}
