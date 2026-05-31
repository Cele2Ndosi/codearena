"""
WebSocket Router
Endpoint: ws://localhost:8000/ws/{room_id}?user_id=...&name=...&color=...
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from services.ws_manager import manager

router = APIRouter()


@router.websocket("/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    user_id: str = Query(...),
    name: str = Query("Anonymous"),
    color: str = Query("#4f8eff"),
):
    """
    Main WebSocket connection.
    Each message is JSON with a 'type' field:
      - EDIT_PATCH   : document changed (CRDT patch + full doc)
      - CURSOR_MOVE  : cursor position update
      - LANG_CHANGE  : language switched
      - PING         : keep-alive heartbeat
    """
    room = await manager.connect(websocket, room_id, user_id, name, color)

    try:
        while True:
            raw = await websocket.receive_text()
            await manager.handle_message(room_id, user_id, raw)
    except WebSocketDisconnect:
        await manager.disconnect(room_id, user_id)
    except Exception as e:
        print(f"[WS Error] room={room_id} user={user_id}: {e}")
        await manager.disconnect(room_id, user_id)
