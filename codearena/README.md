# ⬡ CodeArena — Distributed Real-Time Coding Interview Platform

A full-stack coding interview platform with real-time collaboration,
AI-powered technical interviewing (Grok), sandboxed code execution,
and session replay.

---

## Architecture

```
browser ──WebSocket──▶ FastAPI (main.py)
                            │
                    ┌───────┼────────────┐
                    │       │            │
                 rooms.py  grok.py   sandbox.py
                (session  (Grok AI  (code exec)
                 state)   client)
```

**WebSocket message protocol** — see `backend/main.py` docstring for the full
list of message types (code_edit, cursor_move, chat, run_code, submit_code...).

**CRDT note**: The current implementation uses last-write-wins for code sync.
For true conflict-free merging under simultaneous edits, integrate
[Yjs](https://yjs.dev/) (JavaScript) or [diamond-types](https://github.com/josephg/diamond-types) (Rust).

---

## Quick Start

### 1. Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your Grok API key
cp .env.example .env
# Edit .env and set GROK_API_KEY=xai-...

# Run the server (auto-reloads on save)
python main.py
# or: uvicorn main:app --reload --port 8000
```

Server starts at `http://localhost:8000`
WebSocket at `ws://localhost:8000/ws/{room_id}`

### 2. Frontend

```bash
cd frontend

npm install
npm run dev
```

Frontend starts at `http://localhost:5173`

### 3. Get your Grok API key

1. Go to [console.x.ai](https://console.x.ai)
2. Create an API key
3. Paste it into `backend/.env` as `GROK_API_KEY=xai-...`

---

## Features

| Feature | File | How it works |
|---|---|---|
| Real-time collab | `main.py` + `useWebSocket.js` | WebSocket broadcast to all room peers |
| AI Interviewer | `grok.py` | Grok API with system prompt + code context |
| Code execution | `sandbox.py` | subprocess + resource limits (timeout, memory) |
| Complexity analysis | `grok.py` → `analyse_complexity()` | Grok returns JSON `{time, space, explanation}` |
| Plagiarism check | `grok.py` → `check_originality()` | Grok scores originality 0–100 |
| Room management | `rooms.py` | In-memory dict (swap for Redis in production) |
| Cursor sync | `main.py` cursor_move/cursor_sync | Broadcast to all peers except sender |
| Timer | `main.py` → `timer_task()` | asyncio background task, broadcasts every 5s |

---

## WebSocket Message Protocol

### Client → Server
```json
{ "type": "join",        "name": "Alice" }
{ "type": "code_edit",   "code": "...", "language": "python" }
{ "type": "cursor_move", "line": 5, "col": 12 }
{ "type": "chat",        "message": "How do I handle ABA?" }
{ "type": "run_code" }
{ "type": "submit_code" }
{ "type": "get_hint" }
```

### Server → Client
```json
{ "type": "room_state",  "code": "...", "language": "...", "peers": [...] }
{ "type": "code_sync",   "code": "...", "from": "Alice", "color": "#4f8eff" }
{ "type": "ai_message",  "message": "..." }
{ "type": "test_results","results": [{"name":"...", "pass": true, "time":"1ms"}] }
{ "type": "complexity",  "time": "O(1)", "space": "O(n)", "explanation": "..." }
{ "type": "originality", "score": 96, "verdict": "original", "flags": [] }
```

---

## Production Upgrades (for your portfolio writeup)

- **CRDT**: Replace last-write-wins with Yjs for true conflict-free merges
- **Sandbox**: Swap subprocess for Docker (`--network=none`, seccomp, cgroup v2) or gVisor
- **Persistence**: Replace in-memory rooms dict with Redis (room state, replay storage)
- **Replay**: Store WebSocket events to a database; stream them back on demand
- **Auth**: Add JWT-based room ownership and candidate/interviewer roles
- **Monaco Editor**: Replace the textarea with Monaco (VS Code's editor) for syntax highlighting

---

## Explaining this to Cambridge admissions

Be ready to answer:
- Why WebSockets over HTTP polling? (bi-directional, low latency, no repeated handshakes)
- What is the ABA problem in lock-free programming?
- How does the sandbox prevent infinite loops? (RLIMIT_CPU + asyncio timeout)
- What is linearizability? (each operation appears to take effect atomically at a single point in time)
- What would a CRDT-based merge look like? (operational transforms or state-based CRDT)
- How would you scale this to 10,000 rooms? (Redis pub/sub, horizontal FastAPI workers)
