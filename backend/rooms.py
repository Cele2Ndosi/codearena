"""
rooms.py — Interview room & session management.

Each room has:
- A unique ID
- A list of connected WebSocket clients
- Shared code state (last known value, for late joiners)
- Chat history (for AI context)
- A timer
"""

from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass, field
from fastapi import WebSocket


@dataclass
class Client:
    websocket: WebSocket
    name: str
    color: str  # for cursor display


@dataclass
class Room:
    room_id: str
    clients: list[Client] = field(default_factory=list)
    code: str = ""
    language: str = "python"
    chat_history: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    duration_seconds: int = 45 * 60  # 45 minute interview

    def time_remaining(self) -> int:
        elapsed = time.time() - self.created_at
        return max(0, self.duration_seconds - int(elapsed))

    def add_client(self, client: Client):
        self.clients.append(client)

    def remove_client(self, websocket: WebSocket):
        self.clients = [c for c in self.clients if c.websocket is not websocket]

    def get_client(self, websocket: WebSocket) -> Client | None:
        return next((c for c in self.clients if c.websocket is websocket), None)

    async def broadcast(self, message: dict, exclude: WebSocket | None = None):
        """Send a message to all connected clients in this room."""
        dead = []
        for client in self.clients:
            if client.websocket is exclude:
                continue
            try:
                await client.websocket.send_text(json.dumps(message))
            except Exception:
                dead.append(client.websocket)
        # Clean up disconnected clients
        for ws in dead:
            self.remove_client(ws)

    async def broadcast_all(self, message: dict):
        """Send to everyone including sender (e.g. AI messages)."""
        await self.broadcast(message, exclude=None)


# In-memory store — in production use Redis
_rooms: dict[str, Room] = {}

CURSOR_COLORS = ["#4f8eff", "#00d4aa", "#ff9f43", "#ff4757", "#7c5cff", "#2ed573"]


def get_or_create_room(room_id: str) -> Room:
    if room_id not in _rooms:
        _rooms[room_id] = Room(room_id=room_id)
    return _rooms[room_id]


def get_room(room_id: str) -> Room | None:
    return _rooms.get(room_id)


def assign_color(room: Room) -> str:
    used = {c.color for c in room.clients}
    for color in CURSOR_COLORS:
        if color not in used:
            return color
    return CURSOR_COLORS[len(room.clients) % len(CURSOR_COLORS)]
