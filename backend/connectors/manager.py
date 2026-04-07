from datetime import datetime, timedelta
from typing import Any
import asyncio
import logging

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, SourceType, SyncResult

# Import connectors so their @register decorators run
from . import slack, gmail, jira  # noqa: F401

logger = logging.getLogger(__name__)


class ConnectorManager:
    """
    Orchestrates all registered connectors.

    Usage:
        manager = ConnectorManager(configs={
            SourceType.SLACK: {"use_mock": True},
            SourceType.GMAIL: {"use_mock": True},
            SourceType.JIRA:  {"use_mock": True},
        })
        results = await manager.sync_all(since=datetime.utcnow() - timedelta(days=7))
        items = manager.collect_items(results)
    """

    def __init__(self, configs: dict[SourceType, dict[str, Any]]):
        self._connectors: dict[SourceType, BaseConnector] = {
            source: ConnectorRegistry.build(source, config)
            for source, config in configs.items()
        }

    async def sync_all(
        self,
        since: datetime | None = None,
        sources: list[SourceType] | None = None,
    ) -> list[SyncResult]:
        """
        Run all (or a subset of) connectors concurrently.

        Args:
            since:   fetch data updated after this datetime (default: 7 days ago)
            sources: restrict to these sources (default: all configured)
        """
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        targets = sources or list(self._connectors.keys())
        tasks = [
            self._connectors[s].sync(since)
            for s in targets
            if s in self._connectors
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        sync_results: list[SyncResult] = []
        for source, result in zip(targets, results):
            if isinstance(result, Exception):
                logger.error("[%s] Unexpected error: %s", source, result)
                sync_results.append(
                    SyncResult(source=source, success=False, items_fetched=0, error=str(result))
                )
            else:
                sync_results.append(result)

        return sync_results

    @staticmethod
    def collect_items(results: list[SyncResult]) -> list[DataItem]:
        """Flatten all SyncResults into a single sorted list of DataItems."""
        items = [item for r in results for item in r.items]
        return sorted(items, key=lambda x: x.timestamp, reverse=True)

    def summary(self, results: list[SyncResult]) -> dict:
        return {
            "total_items": sum(r.items_fetched for r in results),
            "by_source": {
                r.source: {"items": r.items_fetched, "success": r.success, "error": r.error}
                for r in results
            },
        }
