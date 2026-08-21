import json
import logging
from typing import List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    """Singleton WebSocket connection manager — broadcast to all connected clients."""

    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("[WS] Client connecté — total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("[WS] Client déconnecté — total: %d", len(self._connections))

    async def broadcast(self, event: dict) -> None:
        if not self._connections:
            return
        msg = json.dumps(event, default=str)
        dead: List[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, event: dict) -> None:
        try:
            await ws.send_text(json.dumps(event, default=str))
        except Exception:
            self.disconnect(ws)

    @property
    def connected_count(self) -> int:
        return len(self._connections)


ws_manager = WSManager()
