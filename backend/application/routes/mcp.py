"""
MCP API — interface REST pour appeler les outils MCP depuis le frontend ou Claude.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.models import User
from core.security import get_current_org_user

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class ToolCallRequest(BaseModel):
    tool: str
    args: dict = {}


@router.get("/tools")
def list_tools(current_user: User = Depends(get_current_org_user)):
    """Liste tous les outils MCP disponibles avec leur schéma."""
    from integrations.mcp_servers.manager import get_manager
    manager = get_manager()
    return {
        "tools":   manager.list_tools(),
        "servers": manager.list_servers(),
        "total":   len(manager.list_tools()),
    }


@router.post("/call")
async def call_tool(body: ToolCallRequest, current_user: User = Depends(get_current_org_user)):
    """
    Appelle un outil MCP par son nom, scopé à l'organisation de l'utilisateur
    authentifié (avant le 03/09/2026 cette route n'avait aucune auth et les
    handlers aucun filtre org — n'importe qui pouvait lire les données de
    toutes les organisations).

    Exemple :
      POST /api/mcp/call
      { "tool": "get_recent_emails", "args": { "days": 7, "urgent_only": true } }
    """
    from integrations.mcp_servers.manager import get_manager
    manager = get_manager()
    result  = await manager.call_tool(tool=body.tool, args=body.args, org_id=current_user.org_id)

    if "error" in result and "available_tools" in result:
        raise HTTPException(status_code=404, detail=result)

    return result


@router.get("/servers")
def list_servers():
    """Aperçu rapide : quels serveurs sont actifs et leurs outils."""
    from integrations.mcp_servers.manager import get_manager
    return get_manager().list_servers()
