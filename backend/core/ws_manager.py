import json
import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    """
    Singleton WebSocket connection manager — connexions groupées par org_id.
    org_id=None regroupe les connexions "globales" (diffusions non-scopées, ex: tâches
    de fond / webhooks qui ne peuvent pas résoudre d'organisation aujourd'hui).
    """

    def __init__(self):
        self._connections: Dict[Optional[str], List[WebSocket]] = {}
        self._ws_org: Dict[WebSocket, Optional[str]] = {}

    async def connect(self, ws: WebSocket, org_id: Optional[str] = None) -> None:
        await ws.accept()
        self._connections.setdefault(org_id, []).append(ws)
        self._ws_org[ws] = org_id
        logger.info("[WS] Client connecté (org=%s) — total: %d", org_id, self.connected_count)

    def disconnect(self, ws: WebSocket) -> None:
        org_id = self._ws_org.pop(ws, None)
        bucket = self._connections.get(org_id)
        if bucket and ws in bucket:
            bucket.remove(ws)
        logger.info("[WS] Client déconnecté (org=%s) — total: %d", org_id, self.connected_count)

    async def broadcast(self, event: dict, org_id: Optional[str] = None) -> None:
        """org_id=None diffuse à TOUTES les connexions (tous buckets) ; sinon uniquement à l'org donnée."""
        targets: List[WebSocket] = (
            [ws for bucket in self._connections.values() for ws in bucket]
            if org_id is None
            else list(self._connections.get(org_id, []))
        )
        if not targets:
            return
        msg = json.dumps(event, default=str)
        dead: List[WebSocket] = []
        for ws in targets:
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
        return sum(len(bucket) for bucket in self._connections.values())


ws_manager = WSManager()
