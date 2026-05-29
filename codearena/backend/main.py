"""
main.py — FastAPI app with WebSocket server.

WebSocket message protocol:
  Client → Server:
    { "type": "join",        "name": "Alice" }
    { "type": "code_edit",   "code": "...", "language": "python" }
    { "type": "cursor_move", "line": 5, "col": 12 }
    { "type": "chat",        "message": "How do I handle ABA?" }
    { "type": "run_code" }
    { "type": "submit_code" }
    { "type": "get_hint" }

  Server → Client (broadcast to room):
    { "type": "code_sync",   "code": "...", "language": "python",
                              "from": "Alice", "color": "#4f8eff" }
    { "type": "cursor_sync", "name": "Alice", "color": "...",
                              "line": 5, "col": 12 }
    { "type": "ai_message",  "message": "..." }
    { "type": "test_results","results": [...] }
    { "type": "complexity",  "time": "O(1)", "space": "O(n)",
                              "explanation": "..." }
    { "type": "originality", "score": 96, "verdict": "original" }
    { "type": "user_joined", "name": "Alice", "color": "...", "peers": [...] }
    { "type": "user_left",   "name": "Alice", "peers": [...] }
    { "type": "timer",       "remaining": 2062 }
    { "type": "error",       "message": "..." }
"""

import asyncio
import json
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rooms import get_or_create_room, get_room, assign_color, Client
from grok import ask_interviewer, analyse_complexity, check_originality
from sandbox import execute_code, run_test_suite, detect_available_languages, resolve_lang
from problems import list_problems, get_problem, fetch_daily_challenge, FALLBACK_PROBLEMS
from database import init_db, save_submission, get_user_progress, get_leaderboard, get_problem_stats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("codearena")


# --- Timer broadcast task ---
async def timer_task(room_id: str):
    """Broadcast the remaining time every 5 seconds to all clients in a room."""
    while True:
        await asyncio.sleep(5)
        room = get_room(room_id)
        if room is None:
            break
        remaining = room.time_remaining()
        await room.broadcast_all({"type": "timer", "remaining": remaining})
        if remaining == 0:
            await room.broadcast_all({"type": "time_up", "message": "Interview time is up!"})
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("CodeArena backend starting up")
    yield
    log.info("CodeArena backend shutting down")


app = FastAPI(title="CodeArena API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite + CRA
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- REST endpoints ---

@app.get("/")
def root():
    return {"status": "ok", "service": "CodeArena", "version": "1.0.0"}


@app.get("/languages")
def get_languages():
    """
    Return all supported languages with availability status.
    Frontend uses this to populate the language selector and grey out
    languages whose runtimes aren't installed on this server.
    """
    langs = detect_available_languages()
    return {
        "languages": sorted(langs.values(), key=lambda x: (not x["available"], x["label"])),
        "available_count": sum(1 for v in langs.values() if v["available"]),
        "total_count": len(langs),
    }


@app.get("/problems")
async def get_problems(
    difficulty: str = "",
    tags: str = "",
    search: str = "",
    limit: int = 50,
    skip: int = 0,
):
    """
    Return problems from LeetCode with full pagination + search.
    ?difficulty=hard&search=tree&limit=50&skip=100
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    result = await list_problems(
        difficulty=difficulty,
        tags=tag_list or None,
        search=search,
        limit=min(limit, 100),   # cap at 100 per page
        skip=skip,
    )
    return {**result, "source": "leetcode"}


@app.get("/problems/daily")
async def get_daily_problem():
    """Return today's LeetCode daily challenge."""
    problem = await fetch_daily_challenge()
    if not problem:
        return {"problem": None, "error": "Could not fetch daily challenge"}
    return {"problem": problem}


@app.get("/problems/{problem_id}")
async def get_problem_detail(problem_id: str):
    """Return full details for a specific problem by its LeetCode title slug."""
    problem = await get_problem(problem_id)
    if not problem:
        raise HTTPException(404, f"Problem '{problem_id}' not found")
    return {"problem": problem}


@app.post("/rooms")
async def create_room(problem_id: str = "two-sum"):
    """Create a new interview room. problem_id is a LeetCode title slug."""
    room_id = str(uuid.uuid4())[:8]
    problem = await get_problem(problem_id)
    if not problem:
        # Use first fallback if LeetCode is unreachable
        problem = FALLBACK_PROBLEMS[0]
        problem["starter_code"] = {"python": "class Solution:\n    def solve(self, *args):\n        pass\n"}
    room = get_or_create_room(room_id)
    room.problem_id = problem["id"]
    room.code = problem.get("starter_code", {}).get("python", "# Write your solution here\n")
    return {
        "room_id": room_id,
        "problem_id": problem["id"],
        "problem_title": problem.get("title", ""),
        "join_url": f"ws://localhost:8000/ws/{room_id}",
    }


@app.get("/rooms/{room_id}")
def room_info(room_id: str):
    room = get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return {
        "room_id": room_id,
        "peers": [{"name": c.name, "color": c.color} for c in room.clients],
        "language": room.language,
        "time_remaining": room.time_remaining(),
    }


# --- WebSocket endpoint ---

@app.get("/progress/{user_name}")
def user_progress(user_name: str):
    """Return a user's full progress — solved problems, stats, recent submissions."""
    return get_user_progress(user_name)


@app.get("/leaderboard")
def leaderboard(limit: int = 20):
    """Global leaderboard ranked by problems solved."""
    return {"leaderboard": get_leaderboard(limit)}


@app.get("/stats/{problem_id:path}")
def problem_statistics(problem_id: str):
    """Solve rate and average time for a specific problem."""
    stats = get_problem_stats(problem_id)
    if not stats:
        return {"problem_id": problem_id, "total_attempts": 0, "total_solved": 0, "solve_rate": 0}
    return stats


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    room = get_or_create_room(room_id)
    client: Client | None = None

    # Start timer task for this room (idempotent — only one runs per room)
    asyncio.create_task(timer_task(room_id))

    try:
        # First message must be a "join"
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("type") != "join":
            await websocket.send_text(json.dumps(
                {"type": "error", "message": "First message must be {type: 'join', name: '...'}"}
            ))
            await websocket.close()
            return

        name = msg.get("name", "Anonymous")[:32]
        color = assign_color(room)
        client = Client(websocket=websocket, name=name, color=color)
        room.add_client(client)

        peers = [{"name": c.name, "color": c.color} for c in room.clients]

        # Tell the new user about the room state
        await websocket.send_text(json.dumps({
            "type": "room_state",
            "code": room.code,
            "language": room.language,
            "peers": peers,
            "color": color,
            "time_remaining": room.time_remaining(),
        }))

        # Tell everyone else someone joined
        await room.broadcast({
            "type": "user_joined",
            "name": name,
            "color": color,
            "peers": peers,
        }, exclude=websocket)

        log.info(f"[{room_id}] {name} joined ({len(room.clients)} peers)")

        # --- Main message loop ---
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")
            log.info(f"[{room_id}] ← {msg_type} from {name}")

            # --- Code edit: sync to all peers ---
            if msg_type == "code_edit":
                room.code = msg.get("code", "")
                room.language = msg.get("language", room.language)
                await room.broadcast({
                    "type": "code_sync",
                    "code": room.code,
                    "language": room.language,
                    "from": name,
                    "color": color,
                }, exclude=websocket)

            # --- Cursor move ---
            elif msg_type == "cursor_move":
                await room.broadcast({
                    "type": "cursor_sync",
                    "name": name,
                    "color": color,
                    "line": msg.get("line", 0),
                    "col": msg.get("col", 0),
                }, exclude=websocket)

            # --- Chat with AI interviewer ---
            elif msg_type == "chat":
                user_message = msg.get("message", "").strip()
                if not user_message:
                    continue

                # Add to history for context
                room.chat_history.append({"role": "user", "content": user_message})

                # Keep last 20 messages as context (token budget)
                context = room.chat_history[-20:]

                # Call Grok
                ai_reply = await ask_interviewer(
                    chat_history=context[:-1],  # history without latest
                    user_message=user_message,
                    current_code=room.code,
                    language=room.language,
                )

                room.chat_history.append({"role": "assistant", "content": ai_reply})

                # Broadcast AI reply to ALL peers in the room
                await room.broadcast_all({
                    "type": "ai_message",
                    "message": ai_reply,
                })

            # --- Run code in sandbox ---
            elif msg_type == "run_code":
                result = await execute_code(room.code, room.language)
                await websocket.send_text(json.dumps({
                    "type": "run_result",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "wall_time_ms": result.wall_time_ms,
                }))

            # --- Submit: run tests + complexity + plagiarism ---
            elif msg_type == "submit_code":
                log.info(f"[{room_id}] submit_code received, lang={room.language}, code_len={len(room.code)}")

                # Run each task independently so one failure doesn't kill the others
                problem_id = getattr(room, "problem_id", "lock-free-queue")
                try:
                    tests = await run_test_suite(room.code, room.language, problem_id)
                    log.info(f"[{room_id}] test_suite done: {tests}")
                except Exception as e:
                    log.exception(f"[{room_id}] run_test_suite failed: {e}")
                    tests = [{"name": f"Test runner error: {e}", "pass": False, "time": "0ms"}]

                try:
                    complexity = await analyse_complexity(room.code, room.language)
                    log.info(f"[{room_id}] complexity done: {complexity}")
                except Exception as e:
                    log.exception(f"[{room_id}] analyse_complexity failed: {e}")
                    complexity = {"time": "O(?)", "space": "O(?)", "explanation": str(e)}

                try:
                    originality = await check_originality(room.code, room.language)
                    log.info(f"[{room_id}] originality done: {originality}")
                except Exception as e:
                    log.exception(f"[{room_id}] check_originality failed: {e}")
                    originality = {"score": 0, "flags": [str(e)], "verdict": "unknown"}

                # Send results back
                log.info(f"[{room_id}] broadcasting results...")
                await room.broadcast_all({"type": "test_results", "results": tests})
                await room.broadcast_all({"type": "complexity", **complexity})
                await room.broadcast_all({"type": "originality", **originality})

                # Persist to database
                try:
                    problem_title = getattr(room, "problem_title", problem_id)
                    time_taken = 45 * 60 - room.time_remaining()
                    sub_id = save_submission(
                        user_name=name,
                        room_id=room_id,
                        problem_id=problem_id,
                        problem_title=problem_title,
                        language=room.language,
                        code=room.code,
                        test_results=tests,
                        time_taken_s=time_taken,
                        complexity=complexity,
                        originality=originality,
                    )
                    # Broadcast progress update so UI can refresh
                    tests_passed = sum(1 for t in tests if t.get("pass"))
                    solved = tests_passed == len(tests) and len(tests) > 0
                    await room.broadcast_all({
                        "type": "submission_saved",
                        "submission_id": sub_id,
                        "user_name": name,
                        "solved": solved,
                        "tests_passed": tests_passed,
                        "tests_total": len(tests),
                    })
                    log.info(f"[{room_id}] submission #{sub_id} saved (solved={solved})")
                except Exception as e:
                    log.exception(f"[{room_id}] Failed to save submission: {e}")

                log.info(f"[{room_id}] submit_code complete")

            # --- Switch problem (broadcast to all peers) ---
            elif msg_type == "switch_problem":
                problem_id = msg.get("problem_id", "")
                new_code   = msg.get("code", "")
                room.problem_id = problem_id
                room.problem_title = msg.get('problem_title', problem_id)
                room.code = new_code
                log.info(f"[{room_id}] {name} switched problem → {problem_id}")
                await room.broadcast({
                    "type": "switch_problem",
                    "problem_id": problem_id,
                    "code": new_code,
                    "switched_by": name,
                }, exclude=websocket)

            # --- AI hint ---
            elif msg_type == "get_hint":
                hint = await ask_interviewer(
                    chat_history=room.chat_history[-10:],
                    user_message="Give me a hint without revealing the answer.",
                    current_code=room.code,
                    language=room.language,
                )
                await room.broadcast_all({"type": "ai_message", "message": hint})

            else:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                ))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception(f"[{room_id}] WebSocket error: {e}")
    finally:
        if client and room:
            room.remove_client(websocket)
            peers = [{"name": c.name, "color": c.color} for c in room.clients]
            await room.broadcast({
                "type": "user_left",
                "name": client.name,
                "peers": peers,
            })
            log.info(f"[{room_id}] {client.name if client else '?'} left")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
