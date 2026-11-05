import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[Dict[str, Any]] = []

    async def connect(self, websocket: WebSocket, camera_code: Optional[str] = None):
        await websocket.accept()
        self.active_connections.append({
            "ws": websocket,
            "camera_code": camera_code,
        })

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [
            conn for conn in self.active_connections if conn["ws"] != websocket
        ]

    async def broadcast(self, message: dict, camera_code: Optional[str] = None):
        """Broadcast message to connected clients, respecting optional camera_code filter."""
        data = json.dumps(message)
        dead_connections = []
        for conn in list(self.active_connections):
            client_cam = conn.get("camera_code")
            # If client requested specific camera_code, only send if matches or message has no camera_code
            if client_cam and camera_code and client_cam != camera_code:
                continue
            try:
                await conn["ws"].send_text(data)
            except Exception as e:
                logger.debug("Failed sending WS frame: %s", e)
                dead_connections.append(conn["ws"])

        for ws in dead_connections:
            self.disconnect(ws)


ws_manager = ConnectionManager()
