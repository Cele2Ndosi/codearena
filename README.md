# ⬡ CodeArena — Real-Time Collaborative Coding Interview Platform

A full-stack coding interview platform with real-time collaboration, an AI-powered technical interviewer (Groq / LLaMA 3.3), sandboxed multi-language code execution, LeetCode problem integration, and persistent submission tracking.

---

## Architecture

```
browser ──WebSocket──▶ FastAPI (main.py)
                            │
              ┌─────────────┼──────────────────┐
              │             │                  │
           rooms.py      grok.py          sandbox.py
          (session     (Groq AI          (multi-language
           state)       client)           code exec)
              │             │                  │
           database.py  problems.py        (subprocess +
          (SQLite:       (LeetCode          resource limits)
           users,        GraphQL API,
           submissions,  in-memory cache)
           problem_stats)
```

**WebSocket message protocol** — see `backend/main.py` docstring for the full list of message types (`code_edit`, `cursor_move`, `chat`, `run_code`, `submit_code`, ...).

**CRDT note**: The current implementation uses last-write-wins for code sync. For true conflict-free merging under simultaneous edits, integrate [Yjs](https://yjs.dev/) (JavaScript) or [diamond-types](https://github.com/josephg/diamond-types) (Rust).

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

# Set your Groq API key
cp .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_...

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

### 3. Get your Groq API key

1. Go to [console.groq.com](https://console.groq.com)
2. Create an API key
3. Paste it into `backend/.env` as `GROQ_API_KEY=gsk_...`

> **Note**: CodeArena uses the [Groq](https://groq.com) API (not Grok/xAI) to run **LLaMA 3.3 70B** for the AI interviewer, complexity analysis, and originality checking.

---

## Features

| Feature | File | How it works |
|---|---|---|
| Real-time collab | `main.py` + `useWebSocket.js` | WebSocket broadcast to all room peers |
| AI Interviewer | `grok.py` | Groq API (LLaMA 3.3 70B) with system prompt + code context |
| Complexity analysis | `grok.py` → `analyse_complexity()` | LLM returns JSON `{time, space, explanation}` |
| Originality check | `grok.py` → `check_originality()` | LLM scores originality 0–100 with verdict |
| Code execution | `sandbox.py` | subprocess + `RLIMIT_CPU` + asyncio timeout |
| Multi-language support | `sandbox.py` | Detects installed runtimes at startup; Python, JS, and more |
| LeetCode problems | `problems.py` | GraphQL API with in-memory 10-min cache |
| Daily challenge | `problems.py` → `fetch_daily_challenge()` | Today's LeetCode daily via GraphQL |
| Submission tracking | `database.py` | SQLite: users, submissions, per-problem stats |
| Leaderboard | `database.py` + `main.py` | Ranked by problems solved |
| Progress dashboard | `database.py` + `Progress.jsx` | Per-user solve history and stats |
| Room management | `rooms.py` | In-memory dict (swap for Redis in production) |
| Cursor sync | `main.py` cursor_move/cursor_sync | Broadcast to all peers except sender |
| Timer | `main.py` → `timer_task()` | asyncio background task, broadcasts every 5 s |

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/languages` | Supported languages + availability |
| `GET` | `/problems` | Paginated LeetCode problems (`?difficulty=&tags=&search=`) |
| `GET` | `/problems/daily` | Today's LeetCode daily challenge |
| `GET` | `/problems/{slug}` | Full problem detail by title slug |
| `POST` | `/rooms` | Create a new interview room |
| `GET` | `/rooms/{room_id}` | Room info (peers, language, time remaining) |
| `GET` | `/progress/{user_name}` | User's submission history and stats |
| `GET` | `/leaderboard` | Global leaderboard (top N users) |
| `GET` | `/stats/{problem_id}` | Solve rate and average time for a problem |

---

## WebSocket Message Protocol

### Client → Server
```json
{ "type": "join",           "name": "Alice" }
{ "type": "code_edit",      "code": "...", "language": "python" }
{ "type": "cursor_move",    "line": 5, "col": 12 }
{ "type": "chat",           "message": "How do I handle ABA?" }
{ "type": "run_code" }
{ "type": "submit_code" }
{ "type": "get_hint" }
{ "type": "switch_problem", "problem_id": "...", "code": "..." }
```

### Server → Client
```json
{ "type": "room_state",      "code": "...", "language": "...", "peers": [...], "time_remaining": 2700 }
{ "type": "code_sync",       "code": "...", "from": "Alice", "color": "#4f8eff" }
{ "type": "cursor_sync",     "name": "Alice", "color": "...", "line": 5, "col": 12 }
{ "type": "ai_message",      "message": "..." }
{ "type": "run_result",      "stdout": "...", "stderr": "...", "exit_code": 0, "wall_time_ms": 42 }
{ "type": "test_results",    "results": [{ "name": "...", "pass": true, "time": "1ms" }] }
{ "type": "complexity",      "time": "O(1)", "space": "O(n)", "explanation": "..." }
{ "type": "originality",     "score": 96, "verdict": "original", "flags": [] }
{ "type": "submission_saved","submission_id": 7, "solved": true, "tests_passed": 3, "tests_total": 3 }
{ "type": "user_joined",     "name": "Alice", "color": "...", "peers": [...] }
{ "type": "user_left",       "name": "Alice", "peers": [...] }
{ "type": "timer",           "remaining": 2062 }
{ "type": "time_up",         "message": "Interview time is up!" }
{ "type": "switch_problem",  "problem_id": "...", "code": "...", "switched_by": "Alice" }
```

---

## Project Structure

```
codearena/
├── backend/
│   ├── main.py              # FastAPI app, WebSocket handler, REST endpoints
│   ├── rooms.py             # In-memory room and client state
│   ├── grok.py              # Groq AI client (interviewer, complexity, originality)
│   ├── sandbox.py           # Multi-language code execution with resource limits
│   ├── problems.py          # LeetCode GraphQL fetcher with caching
│   ├── database.py          # SQLite persistence (submissions, leaderboard)
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Environment variable template
│   ├── core/
│   │   └── config.py
│   ├── routers/
│   │   ├── ai_interviewer.py
│   │   ├── execution.py
│   │   ├── interview.py
│   │   └── websocket.py
│   └── services/
│       ├── grok_service.py
│       ├── sandbox.py
│       └── ws_manager.py
└── frontend/
    ├── src/
    │   ├── App.jsx           # Main app shell and routing
    │   ├── Editor.jsx        # Code editor component
    │   ├── AIChat.jsx        # AI interviewer chat panel
    │   ├── Progress.jsx      # User progress dashboard
    │   ├── useWebSocket.js   # WebSocket hook
    │   ├── hooks/
    │   ├── lib/
    │   │   └── api.js        # REST API helpers
    │   └── pages/
    │       ├── Home.jsx
    │       └── Arena.jsx
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in:

```env
GROQ_API_KEY=gsk_...   # Required — get from console.groq.com
```

---

## Production Upgrades

- **CRDT**: Replace last-write-wins with Yjs for true conflict-free merges
- **Sandbox**: Swap subprocess for Docker (`--network=none`, seccomp, cgroup v2) or gVisor
- **Persistence**: Replace in-memory rooms dict with Redis (room state, pub/sub for horizontal scaling)
- **Database**: Swap SQLite for PostgreSQL using the same interface
- **Auth**: Add JWT-based room ownership and candidate/interviewer roles
- **Monaco Editor**: Replace the textarea with Monaco (VS Code's editor) for syntax highlighting and LSP support
- **Replay**: Store WebSocket events to the database; stream them back on demand

---

## Interview Prep Questions

Be ready to answer:
- Why WebSockets over HTTP polling? (bi-directional, low latency, no repeated handshakes)
- What is the ABA problem in lock-free programming?
- How does the sandbox prevent infinite loops? (`RLIMIT_CPU` + asyncio timeout)
- What is linearizability? (each operation appears to take effect atomically at a single point in time)
- What would a CRDT-based merge look like? (operational transforms or state-based CRDT)
- How would you scale this to 10,000 rooms? (Redis pub/sub, horizontal FastAPI workers behind a load balancer)
