"""Maps source names to their analytics compute functions."""

from connectors.schemas import SourceType
from analytics.engine import compute_gmail, compute_generic

ANALYTICS_REGISTRY: dict[str, any] = {
    "gmail": lambda store, since_days: compute_gmail(store, since_days),
    "slack": lambda store, since_days: compute_generic(store, SourceType.SLACK, since_days),
    "jira":  lambda store, since_days: compute_generic(store, SourceType.JIRA,  since_days),
}
