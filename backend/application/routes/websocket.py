import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from core.database import get_db
from core.plans import get_plan_features
from core.security import get_current_user_ws
from core.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    token = websocket.query_params.get("token")
    user = get_current_user_ws(token, db)
    if user is None:
        # accept() d'abord — sinon le rejet se fait au niveau du handshake HTTP et le
        # navigateur ne relaie PAS le code custom (il verra un générique 1006).
        await websocket.accept()
        await websocket.close(code=4401)
        return

    from core.models import Organisation
    org = db.query(Organisation).filter(Organisation.id == user.org_id).first() if user.org_id else None
    plan = org.plan if org else "free"
    if not get_plan_features(plan).get("websocket", False):
        await websocket.accept()
        await websocket.close(code=4403)
        return

    await ws_manager.connect(websocket, org_id=user.org_id)
    await ws_manager.send_to(websocket, {
        "type": "connected",
        "message": "Connecté à InsightFlow temps réel",
        "timestamp": datetime.utcnow().isoformat(),
        "clients": ws_manager.connected_count,
    })
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_to(websocket, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
            except json.JSONDecodeError:
                pass
    except (WebSocketDisconnect, RuntimeError):
        ws_manager.disconnect(websocket)


@router.get("/api/ws/status", tags=["websocket"])
async def ws_status():
    return {
        "connected_clients": ws_manager.connected_count,
        "status": "ok",
    }
