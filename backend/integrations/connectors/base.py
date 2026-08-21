from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
import logging

from .schemas import DataItem, SourceType, SyncResult

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """
    Abstract base class for all data source connectors.

    To add a new connector:
      1. Subclass BaseConnector
      2. Implement authenticate(), fetch_raw(), normalize()
      3. Register it with @ConnectorRegistry.register(SourceType.YOUR_SOURCE)
    """

    source: SourceType  # must be set by each subclass

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._authenticated = False

    # ------------------------------------------------------------------
    # Abstract interface — every connector must implement these three
    # ------------------------------------------------------------------

    @abstractmethod
    async def authenticate(self) -> None:
        """
        Establish authentication (OAuth token refresh, API key validation…).
        Set self._authenticated = True on success.
        """

    @abstractmethod
    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        """
        Pull raw data from the source since the given datetime.
        Returns a list of raw dicts (source-specific structure).
        """

    @abstractmethod
    def normalize(self, raw_item: dict[str, Any]) -> DataItem:
        """
        Convert a single raw dict into a normalized DataItem.
        """

    # ------------------------------------------------------------------
    # Orchestration — provided by the base class, do not override
    # ------------------------------------------------------------------

    async def sync(self, since: datetime) -> SyncResult:
        """
        Full sync pipeline: authenticate → fetch → normalize.
        Returns a SyncResult with all normalized DataItems.
        """
        try:
            if not self._authenticated:
                await self.authenticate()

            if not self._authenticated:
                # Not configured / no credentials — skip quietly
                return SyncResult(source=self.source, success=True, items_fetched=0)

            logger.info("[%s] Fetching data since %s", self.source, since.isoformat())
            raw_items = await self.fetch_raw(since)

            items: list[DataItem] = []
            for raw in raw_items:
                try:
                    items.append(self.normalize(raw))
                except Exception as e:
                    logger.warning("[%s] Failed to normalize item: %s", self.source, e)

            logger.info("[%s] Synced %d items", self.source, len(items))
            return SyncResult(
                source=self.source,
                success=True,
                items_fetched=len(items),
                items=items,
            )

        except Exception as e:
            logger.error("[%s] Sync failed: %s", self.source, e)
            return SyncResult(
                source=self.source,
                success=False,
                items_fetched=0,
                error=str(e),
            )

    def is_authenticated(self) -> bool:
        return self._authenticated
