"""
Shared FastAPI dependencies — injected via Depends().
"""
from integrations.connectors import ConnectorManager, SourceType
from core.store import item_store

# Single ConnectorManager instance — all connectors in mock mode by default.
# Change use_mock=False and provide real credentials when ready.
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


def get_store():
    return item_store
