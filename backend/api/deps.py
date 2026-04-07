"""
Shared FastAPI dependencies — injected via Depends().
"""
from connectors import ConnectorManager, SourceType
from store import item_store

# Single ConnectorManager instance — all connectors in mock mode by default.
# Change use_mock=False and provide real credentials when ready.
connector_manager = ConnectorManager(
    configs={
        SourceType.SLACK: {"use_mock": True},
        SourceType.GMAIL: {"use_mock": False},   # real Gmail API
        SourceType.JIRA:  {"use_mock": True},
    }
)


def get_manager() -> ConnectorManager:
    return connector_manager


def get_store():
    return item_store
