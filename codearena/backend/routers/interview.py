"""
Interview Router
Manages interview sessions, problems, and replay data.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

router = APIRouter()

# In-memory store (swap for PostgreSQL/Redis in production)
_interviews: dict = {}
_problems: dict = {
    "lock-free-queue": {
        "id": "lock-free-queue",
        "title": "Concurrent Lock-Free Queue",
        "difficulty": "hard",
        "topics": ["Concurrency", "Distributed", "Lock-Free"],
        "description": "Implement a lock-free MPMC queue using atomic CAS operations. The queue must be linearizable and ABA-safe.",
        "examples": [
            {"input": "enqueue(42), enqueue(17), dequeue()", "output": "42"},
        ],
        "constraints": {
            "threads": "up to 1024",
            "ops_per_sec": "10^8",
            "memory": "O(n)",
            "aba_safe": True,
        },
        "test_cases": [
            {"input": "", "expected_output": "PASS", "description": "Basic enqueue/dequeue"},
            {"input": "", "expected_output": "PASS", "description": "FIFO ordering"},
        ],
        "time_limit_minutes": 45,
    },
    "distributed-consensus": {
        "id": "distributed-consensus",
        "title": "Raft Consensus — Leader Election",
        "difficulty": "hard",
        "topics": ["Distributed Systems", "Consensus", "Raft"],
        "description": "Implement the leader election phase of the Raft consensus algorithm. Nodes must elect a leader even with up to (N-1)/2 failures.",
        "examples": [],
        "constraints": {"nodes": "3-9", "failures": "(N-1)/2"},
        "test_cases": [],
        "time_limit_minutes": 60,
    },
    "lru-cache": {
        "id": "lru-cache",
        "title": "Thread-Safe LRU Cache",
        "difficulty": "medium",
        "topics": ["Concurrency", "Data Structures", "Design"],
        "description": "Design a thread-safe LRU cache with O(1) get and put. Support concurrent reads with RW locks.",
        "examples": [],
        "constraints": {"capacity": "up to 10^6"},
        "test_cases": [],
        "time_limit_minutes": 30,
    },
}


class CreateInterviewRequest(BaseModel):
    problem_id: str
    candidate_name: str
    interviewer_name: Optional[str] = "ArenaAI"
    duration_minutes: Optional[int] = 45


@router.get("/problems")
async def list_problems():
    """All available interview problems."""
    return list(_problems.values())


@router.get("/problems/{problem_id}")
async def get_problem(problem_id: str):
    """Get a specific problem by ID."""
    problem = _problems.get(problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


@router.post("/")
async def create_interview(req: CreateInterviewRequest):
    """Create a new interview session. Returns room_id for WebSocket."""
    problem = _problems.get(req.problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail=f"Problem '{req.problem_id}' not found")

    interview_id = str(uuid.uuid4())
    room_id = f"room-{interview_id[:8]}"

    _interviews[interview_id] = {
        "id": interview_id,
        "room_id": room_id,
        "problem": problem,
        "candidate_name": req.candidate_name,
        "interviewer_name": req.interviewer_name,
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
        "duration_minutes": req.duration_minutes or problem.get("time_limit_minutes", 45),
        "submissions": [],
    }

    return {
        "interview_id": interview_id,
        "room_id": room_id,
        "websocket_url": f"/ws/{room_id}",
        "problem": problem,
    }


@router.get("/{interview_id}")
async def get_interview(interview_id: str):
    interview = _interviews.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.get("/{interview_id}/replay")
async def get_replay(interview_id: str):
    """Return the full event log for session replay."""
    from services.ws_manager import manager
    interview = _interviews.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    room = manager.get_room(interview["room_id"])
    replay_log = room.replay_log if room else []
    return {
        "interview_id": interview_id,
        "events": replay_log,
        "total_events": len(replay_log),
    }


@router.post("/{interview_id}/submit")
async def submit_solution(interview_id: str, code: str, language: str):
    """Record a final submission."""
    interview = _interviews.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    submission = {
        "submitted_at": datetime.utcnow().isoformat(),
        "language": language,
        "code_length": len(code),
    }
    interview["submissions"].append(submission)
    interview["status"] = "submitted"
    return {"message": "Submission recorded", "submission": submission}
