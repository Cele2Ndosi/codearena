# ⬡ CodeArena — Distributed Real-Time Coding Interview Platform

A full-stack coding interview platform with real-time collaboration,
AI-powered technical interviewing (Groq / llama-3.3-70b), live LeetCode
problem fetching, sandboxed multi-language code execution, progress
tracking, and session replay.

---

## Project Structure

```
codearena/
├── backend/
│   ├── main.py          # FastAPI app + WebSocket server
│   ├── grok.py          # Groq AI interviewer client
│   ├── sandbox.py       # Multi-language code execution sandbox
│   ├── rooms.py         # In-memory room & session management
│   ├── problems.py      # Live LeetCode GraphQL fetcher + cache
│   ├── database.py      # SQLite persistence (submissions, progress, leaderboard)
│   ├── requirements.txt
│   ├── .env             # Your API keys (never commit this)
│   └── codearena.db     # Auto-created SQLite database on first run
└── frontend/
    ├── src/
    │   ├── App.jsx          # Root component, WebSocket wiring
    │   ├── Editor.jsx       # Collaborative code editor
    │   ├── AIChat.jsx       # Groq AI interviewer chat panel
    │   ├── Progress.jsx     # Progress dashboard + leaderboard
    │   ├── useWebSocket.js  # WebSocket connection hook
    │   └── index.css        # Global styles
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## Quick Start

### Prerequisites

- Python 3.10+ 
- Node.js 18+
- A free [Groq API key](https://console.groq.com) (starts with `gsk_`)

### 1. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Linux / macOS:
source venv/bin/activate

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# If you get a scripts-disabled error on Windows, run first:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install dependencies
pip install -r requirements.txt

# Set your Groq API key
# Create a file called .env in the backend folder containing:
# GROQ_API_KEY=gsk_your_key_here

# Start the server
python main.py
```

Server runs at `http://localhost:8000`  
WebSocket at `ws://localhost:8000/ws/{room_id}`

### 2. Frontend

```bash
cd frontend

# Windows — use npm.cmd instead of npm if PowerShell blocks scripts:
npm install          # or: npm.cmd install
npm run dev          # or: npm.cmd run dev
```

Frontend runs at `http://localhost:5173`

### 3. Get a Groq API Key (free)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up → API Keys → Create Key
3. Paste into `backend/.env` as `GROQ_API_KEY=gsk_...`

---

## Features

| Feature | How it works |
|---|---|
| Real-time collaboration | WebSocket broadcast to all peers in the room |
| AI Interviewer | Groq API (llama-3.3-70b) with code context injected |
| Live problems | LeetCode public GraphQL API — 3,400+ problems, no auth needed |
| Problem search | Filter by difficulty, keyword search, daily challenge |
| In-room switcher | Switch problems mid-session; change broadcasts to all peers |
| Code execution | subprocess + RLIMIT_CPU + asyncio timeout |
| 26 languages | Auto-detects installed runtimes at startup |
| Complexity analysis | Groq analyses time/space complexity on submit |
| Originality check | Groq scores how original the code looks (0–100) |
| Progress tracking | SQLite stores every submission; `/progress/{name}` endpoint |
| Leaderboard | Global ranking by problems solved |
| Session timer | 45-minute countdown, broadcasts every 5s via WebSocket |
| Cursor sync | Real-time peer cursor positions via WebSocket |

---

## API Endpoints

### Rooms
```
POST /rooms?problem_id=two-sum     Create a room with a specific problem
GET  /rooms/{room_id}              Room info and peer list
```

### Problems (live from LeetCode)
```
GET /problems                      List problems (paginated, 50/page)
GET /problems?difficulty=hard      Filter by easy / medium / hard
GET /problems?search=tree          Keyword search
GET /problems?skip=50              Next page
GET /problems/daily                Today's LeetCode daily challenge
GET /problems/{slug}               Full problem details (e.g. /problems/two-sum)
```

### Languages
```
GET /languages                     All 26 languages with availability status
```

### Progress & Leaderboard
```
GET /progress/{username}           Full progress for a user
GET /leaderboard                   Global leaderboard (top 20)
GET /stats/{problem_id}            Solve rate + avg time for a problem
```

### WebSocket
```
ws://localhost:8000/ws/{room_id}
```

**Client → Server messages:**
```json
{ "type": "join",          "name": "Alice" }
{ "type": "code_edit",     "code": "...", "language": "python" }
{ "type": "cursor_move",   "line": 5, "col": 12 }
{ "type": "chat",          "message": "How do I handle ABA?" }
{ "type": "run_code" }
{ "type": "submit_code" }
{ "type": "get_hint" }
{ "type": "switch_problem","problem_id": "lru-cache", "code": "..." }
```

**Server → Client messages:**
```json
{ "type": "room_state",      "code": "...", "language": "python", "peers": [...] }
{ "type": "code_sync",       "code": "...", "from": "Alice", "color": "#4f8eff" }
{ "type": "cursor_sync",     "name": "Alice", "line": 5, "col": 12 }
{ "type": "ai_message",      "message": "..." }
{ "type": "test_results",    "results": [{"name":"...", "pass": true}] }
{ "type": "complexity",      "time": "O(1)", "space": "O(n)" }
{ "type": "originality",     "score": 96, "verdict": "original" }
{ "type": "submission_saved","submission_id": 42, "solved": true }
{ "type": "switch_problem",  "problem_id": "...", "code": "..." }
{ "type": "timer",           "remaining": 2062 }
```

---

## Supported Languages

All 26 languages are defined in `sandbox.py`. The backend auto-detects
which runtimes are installed at startup — install any runtime and restart
to enable it.

**Currently detected on a fresh Ubuntu 24.04:**

| Installed by default | Install separately |
|---|---|
| Python 3, Bash, C (GCC), C++ (G++), Perl | Go, Rust, Ruby, PHP, Lua |
| Java (if JDK installed), Node.js (if installed) | Swift, Kotlin, Dart, Elixir |
| | Julia, Haskell, Nim, Zig, Scala, Groovy |

**To add more languages (Ubuntu/Debian):**
```bash
sudo apt install golang-go rustc ruby-full php-cli lua5.4
# Then restart the backend — they appear automatically
```

---

## Database

SQLite database is auto-created at `backend/codearena.db` on first startup.

**Tables:**
- `submissions` — every attempt: user, problem, code, test results, time taken, complexity, originality
- `problem_stats` — aggregated solve rate and average time per problem
- `users` — user names and join timestamps

**Backup:**
```bash
cp backend/codearena.db backup/codearena_$(date +%Y%m%d).db
```

**For production** — swap SQLite for PostgreSQL by changing the connection
in `database.py`. The rest of the code stays the same.

---

## Windows-Specific Notes

PowerShell may block script execution. If `npm` gives a security error:

```powershell
# Option 1: use npm.cmd directly
npm.cmd install
npm.cmd run dev

# Option 2: allow scripts for current user
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

The backend sandbox uses `RLIMIT_CPU` which is Linux-only. On Windows,
only the asyncio timeout (10s wall-clock) applies. For production
isolation on any OS, use Docker.

---

## Production Checklist

- [ ] Swap `rooms.py` in-memory dict for **Redis** (room state + pub/sub for scaling)
- [ ] Replace subprocess sandbox with **Docker** (`--network=none`, seccomp, cgroup v2)
- [ ] Swap SQLite for **PostgreSQL**
- [ ] Add **JWT authentication** for room ownership and interviewer/candidate roles
- [ ] Replace `<textarea>` editor with **Monaco Editor** (VS Code's editor engine)
- [ ] Add **CRDT** (Yjs) for true conflict-free collaborative editing
- [ ] Store WebSocket events to DB for full **session replay**
- [ ] Deploy backend with **gunicorn + uvicorn workers** behind nginx
- [ ] Deploy frontend with `npm run build` → static files on CDN

---