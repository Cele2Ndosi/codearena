"""
WebSocket Connection Manager
Handles:
  - Room-based sessions (each interview = one room)
  - Real-time CRDT patch broadcasting
  - Cursor position sync
  - Participant tracking
  - Replay event recording
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import WebSocket


class Participant:
    def __init__(self, ws: WebSocket, user_id: str, name: str, color: str):
        self.ws = ws
        self.user_id = user_id
        self.name = name
        self.color = color
        self.cursor_line: int = 0
        self.cursor_col: int = 0
        self.connected_at = datetime.utcnow()


class Room:
    """One interview session = one room."""

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.participants: Dict[str, Participant] = {}
        self.created_at = datetime.utcnow()
        # Replay log: every event is recorded for full session replay
        self.replay_log: List[dict] = []
        # Shared document state (last known full code)
        self.document: str = ""
        self.language: str = "python"

    def add(self, participant: Participant):
        self.participants[participant.user_id] = participant

    def remove(self, user_id: str):
        self.participants.pop(user_id, None)

    def is_empty(self) -> bool:
        return len(self.participants) == 0

    def record_event(self, event: dict):
        """Append to replay log with timestamp."""
        self.replay_log.append({
            **event,
            "ts": datetime.utcnow().isoformat(),
        })

    async def broadcast(self, message: dict, exclude_id: Optional[str] = None):
        """Send a message to all participants in this room."""
        payload = json.dumps(message)
        dead = []
        for uid, participant in self.participants.items():
            if uid == exclude_id:
                continue
            try:
                await participant.ws.send_text(payload)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.remove(uid)

    async def broadcast_all(self, message: dict):
        """Broadcast to everyone including sender."""
        await self.broadcast(message, exclude_id=None)

    def participant_list(self) -> List[dict]:
        return [
            {
                "user_id": p.user_id,
                "name": p.name,
                "color": p.color,
                "cursor_line": p.cursor_line,
                "cursor_col": p.cursor_col,
            }
            for p in self.participants.values()
        ]


class ConnectionManager:
    """Global manager for all active rooms."""

    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def get_or_create_room(self, room_id: str) -> Room:
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(room_id)
        return self.rooms[room_id]

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def cleanup_empty_rooms(self):
        empty = [rid for rid, room in self.rooms.items() if room.is_empty()]
        for rid in empty:
            del self.rooms[rid]

    async def connect(
        self,
        ws: WebSocket,
        room_id: str,
        user_id: str,
        name: str,
        color: str,
    ) -> Room:
        await ws.accept()
        room = self.get_or_create_room(room_id)

        participant = Participant(ws, user_id, name, color)
        room.add(participant)

        # Notify existing participants
        await room.broadcast(
            {
                "type": "USER_JOINED",
                "user_id": user_id,
                "name": name,
                "color": color,
                "participants": room.participant_list(),
            },
            exclude_id=user_id,
        )

        # Send current document state to the new joiner
        await ws.send_text(json.dumps({
            "type": "INIT",
            "document": room.document,
            "language": room.language,
            "participants": room.participant_list(),
            "room_id": room_id,
        }))

        room.record_event({"type": "USER_JOINED", "user_id": user_id, "name": name})
        return room

    async def disconnect(self, room_id: str, user_id: str):
        room = self.get_room(room_id)
        if not room:
            return
        room.remove(user_id)
        room.record_event({"type": "USER_LEFT", "user_id": user_id})
        await room.broadcast({
            "type": "USER_LEFT",
            "user_id": user_id,
            "participants": room.participant_list(),
        })
        self.cleanup_empty_rooms()

    async def handle_message(self, room_id: str, user_id: str, raw: str):
        """Route incoming WebSocket messages to the right handler."""
        room = self.get_room(room_id)
        if not room:
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")

        # --- CRDT patch: a user edited the document ---
        if msg_type == "EDIT_PATCH":
            room.document = msg.get("document", room.document)
            room.record_event({"type": "EDIT_PATCH", "user_id": user_id, "patch": msg.get("patch")})
            await room.broadcast(
                {"type": "EDIT_PATCH", "user_id": user_id, "patch": msg.get("patch"), "document": room.document},
                exclude_id=user_id,
            )

        # --- Cursor moved ---
        elif msg_type == "CURSOR_MOVE":
            participant = room.participants.get(user_id)
            if participant:
                participant.cursor_line = msg.get("line", 0)
                participant.cursor_col = msg.get("col", 0)
            room.record_event({"type": "CURSOR_MOVE", "user_id": user_id, "line": msg.get("line"), "col": msg.get("col")})
            await room.broadcast(
                {"type": "CURSOR_MOVE", "user_id": user_id, "name": room.participants[user_id].name,
                 "color": room.participants[user_id].color, "line": msg.get("line"), "col": msg.get("col")},
                exclude_id=user_id,
            )

        # --- Language changed ---
        elif msg_type == "LANG_CHANGE":
            room.language = msg.get("language", room.language)
            room.record_event({"type": "LANG_CHANGE", "user_id": user_id, "language": room.language})
            await room.broadcast(
                {"type": "LANG_CHANGE", "user_id": user_id, "language": room.language},
                exclude_id=user_id,
            )

        # --- Heartbeat / ping ---
        elif msg_type == "PING":
            participant = room.participants.get(user_id)
            if participant:
                await participant.ws.send_text(json.dumps({"type": "PONG", "ts": datetime.utcnow().isoformat()}))


# Singleton — imported by routers
manager = ConnectionManager()
