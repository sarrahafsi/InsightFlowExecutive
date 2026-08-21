"""
Shared FastAPI dependencies — injected via Depends().
"""
from fastapi import Depends
from integrations.connectors import ConnectorManager, SourceType
from core.store import item_store, OrgScopedItemStore
from core.models import User
from core.security import get_current_user

# Global ConnectorManager — used for background sync operations
connector_manager = ConnectorManager(
    configs={
        SourceType.SLACK:   {"use_mock": False},
        SourceType.GMAIL:   {"use_mock": False},
        SourceType.JIRA:    {"use_mock": False},
        SourceType.CLICKUP: {"use_mock": False},
        SourceType.TEAMS:   {"use_mock": True},
        SourceType.OUTLOOK: {},
    }
)


def get_manager() -> ConnectorManager:
    return connector_manager


async def get_store(current_user: User = Depends(get_current_user)) -> OrgScopedItemStore:
    """Returns a per-org store scoped to the authenticated user's organisation."""
    return OrgScopedItemStore(current_user.org_id)
