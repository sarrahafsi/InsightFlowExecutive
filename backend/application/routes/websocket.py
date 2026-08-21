import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
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
