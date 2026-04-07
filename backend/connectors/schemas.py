from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    SLACK = "slack"
    GMAIL = "gmail"
    JIRA = "jira"


class ItemType(str, Enum):
    MESSAGE = "message"
    EMAIL = "email"
    TICKET = "ticket"
    COMMENT = "comment"


class DataItem(BaseModel):
    """
    Normalized schema shared across all connectors.
    Every connector maps its raw data to this model.
    """
    id: str
    source: SourceType
    type: ItemType
    title: str
    content: str
    author: str
    timestamp: datetime
    url: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class SyncResult(BaseModel):
    """Result returned by each connector after a sync."""
    source: SourceType
    success: bool
    items_fetched: int
    items: list[DataItem] = Field(default_factory=list)
    error: str | None = None
    synced_at: datetime = Field(default_factory=datetime.utcnow)
