from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from store import ItemStore
from connectors.schemas import SourceType
from api.deps import get_store

router = APIRouter(prefix="/api/sources", tags=["sources"])


class Source(BaseModel):
    key: str
    name: str
    icon: str
    color: str
    auth_type: str
    description: str
    available: bool
    coming_soon: bool = False
    category: str


REGISTRY: dict[str, dict] = {
    "gmail": {
        "name": "Gmail", "icon": "📧", "color": "#EA4335",
        "auth_type": "oauth2", "description": "Emails Google",
        "available": True, "coming_soon": False, "category": "Communication"
    },
    "outlook": {
        "name": "Outlook", "icon": "📨", "color": "#0078D4",
        "auth_type": "oauth2", "description": "Emails Microsoft",
        "available": False, "coming_soon": True, "category": "Communication"
    },
    "teams": {
        "name": "Teams", "icon": "💬", "color": "#6264A7",
        "auth_type": "oauth2", "description": "Messages Microsoft Teams",
        "available": False, "coming_soon": True, "category": "Communication"
    },
    "slack": {
        "name": "Slack", "icon": "💼", "color": "#4A154B",
        "auth_type": "oauth2", "description": "Communication d'équipe",
        "available": False, "coming_soon": True, "category": "Communication"
    },
    "jira": {
        "name": "Jira", "icon": "🎫", "color": "#0052CC",
        "auth_type": "api_key", "description": "Tickets & Projets",
        "available": False, "coming_soon": True, "category": "Projets"
    },
    "clickup": {
        "name": "ClickUp", "icon": "✅", "color": "#7B68EE",
        "auth_type": "api_key", "description": "Gestion de tâches",
        "available": False, "coming_soon": True, "category": "Projets"
    },
    "notion": {
        "name": "Notion", "icon": "📓", "color": "#ffffff",
        "auth_type": "api_key", "description": "Documentation & Notes",
        "available": False, "coming_soon": True, "category": "Projets"
    },
    "google_calendar": {
        "name": "Google Calendar", "icon": "📅", "color": "#4285F4",
        "auth_type": "oauth2", "description": "Agenda & Réunions",
        "available": False, "coming_soon": True, "category": "Agenda"
    },
    "salesforce": {
        "name": "Salesforce", "icon": "☁️", "color": "#00A1E0",
        "auth_type": "oauth2", "description": "CRM & Ventes",
        "available": False, "coming_soon": True, "category": "CRM"
    },
    "trello": {
        "name": "Trello", "icon": "📋", "color": "#0052CC",
        "auth_type": "api_key", "description": "Boards visuels",
        "available": False, "coming_soon": True, "category": "Projets"
    },
    "hubspot": {
        "name": "HubSpot", "icon": "🟠", "color": "#FF7A59",
        "auth_type": "oauth2", "description": "Marketing & CRM",
        "available": False, "coming_soon": True, "category": "CRM"
    },
    "github": {
        "name": "GitHub", "icon": "🐙", "color": "#333333",
        "auth_type": "oauth2", "description": "Code & Pull Requests",
        "available": False, "coming_soon": True, "category": "Dev"
    },
}


def get_sources_by_category() -> dict[str, list[Source]]:
    categories: dict[str, list[Source]] = {}
    for key, data in REGISTRY.items():
        cat = data["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(Source(key=key, **data))
    return categories


@router.get("/categories")
async def sources_by_category() -> dict[str, list[Source]]:
    return get_sources_by_category()


@router.get("/status")
async def sources_status(store: Annotated[ItemStore, Depends(get_store)]):
    """Returns each source with connection status and item count."""
    SOURCE_TYPES = {
        "gmail": SourceType.GMAIL,
        "slack": SourceType.SLACK,
        "jira":  SourceType.JIRA,
    }
    result = []
    for key, data in REGISTRY.items():
        source_type = SOURCE_TYPES.get(key)
        count = len(store.all(source=source_type, limit=10_000)) if source_type else 0
        last_sync = store.last_sync(source_type).isoformat() if (source_type and store.last_sync(source_type)) else None
        result.append({
            "key":        key,
            "name":       data["name"],
            "icon":       data["icon"],
            "color":      data["color"],
            "category":   data["category"],
            "available":  data["available"],
            "coming_soon": data.get("coming_soon", False),
            "connected":  count > 0,
            "items_count": count,
            "last_sync":  last_sync,
        })
    return result
