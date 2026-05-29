"""
AI Interviewer Router
All endpoints that call Grok / xAI.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from services.grok_service import (
    chat_with_interviewer,
    stream_interviewer,
    get_hint,
    analyze_complexity,
    check_plagiarism,
    evaluate_solution,
)

router = APIRouter()


# ── Request / Response models ───────────────────────────────────────────────

class Message(BaseModel):
    role: str    # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    conversation: List[Message]
    code: str
    problem_title: str
    language: str

class HintRequest(BaseModel):
    code: str
    problem: str
    language: str
    question: str

class ComplexityRequest(BaseModel):
    code: str
    language: str

class PlagiarismRequest(BaseModel):
    code: str
    language: str
    problem: str

class EvaluateRequest(BaseModel):
    code: str
    language: str
    problem: str
    test_results: list


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/chat")
async def ai_chat(req: ChatRequest):
    """Single-turn AI interviewer response (non-streaming)."""
    history = [{"role": m.role, "content": m.content} for m in req.conversation]
    reply = await chat_with_interviewer(history, req.code, req.problem_title, req.language)
    return {"reply": reply}


@router.post("/chat/stream")
async def ai_chat_stream(req: ChatRequest):
    """Streaming AI interviewer — text chunks arrive token-by-token."""
    history = [{"role": m.role, "content": m.content} for m in req.conversation]

    async def generate():
        async for chunk in stream_interviewer(history, req.code, req.problem_title, req.language):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/hint")
async def ai_hint(req: HintRequest):
    """Socratic hint — points in the right direction without solving."""
    hint = await get_hint(req.code, req.problem, req.language, req.question)
    return {"hint": hint}


@router.post("/complexity")
async def ai_complexity(req: ComplexityRequest):
    """Analyze time + space complexity of submitted code."""
    result = await analyze_complexity(req.code, req.language)
    return result


@router.post("/plagiarism")
async def ai_plagiarism(req: PlagiarismRequest):
    """Semantic plagiarism / originality check."""
    result = await check_plagiarism(req.code, req.language, req.problem)
    return result


@router.post("/evaluate")
async def ai_evaluate(req: EvaluateRequest):
    """Post-submission holistic evaluation."""
    feedback = await evaluate_solution(req.code, req.language, req.problem, req.test_results)
    return {"feedback": feedback}
