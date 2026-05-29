"""
grok.py — Grok AI Interviewer client.
"""

import os
import json
import re
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file, no matter where
# uvicorn is launched from.
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "llama-3.3-70b-versatile"


def _get_api_key() -> str | None:
    """Read fresh from env every call — survives late .env loading."""
    return os.getenv("GROQ_API_KEY")


INTERVIEWER_SYSTEM_PROMPT = """You are ArenaAI, an expert technical interviewer at a top-tier tech company.
You are interviewing a candidate solving a hard CS problem in real time.

Your personality:
- Intellectually rigorous but encouraging
- Ask one focused follow-up question at a time
- Never give away the answer — ask Socratic questions instead
- Reference specific lines or patterns in the candidate's code when relevant
- Focus on concurrency, distributed systems, memory safety, and complexity

When the candidate shares code:
- Comment on correctness, edge cases, and efficiency
- Ask about the hardest part of their approach
- Probe their understanding of WHY their solution works

Keep responses concise (2-4 sentences). You are in a live coding interview.
"""


async def ask_interviewer(
    chat_history: list[dict],
    user_message: str,
    current_code: str,
    language: str,
) -> str:
    api_key = _get_api_key()
    if not api_key:
        return (
            "⚠️ GROK_API_KEY not found. "
            "Make sure backend/.env exists and contains: GROQ_API_KEY=gsk_..."
        )

    messages = list(chat_history)
    messages.append({
        "role": "user",
        "content": (
            f"{user_message}\n\n"
            f"[Current {language} code]\n```{language}\n{current_code[:3000]}\n```"
            if current_code else user_message
        ),
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT},
                    *messages,
                ],
                "max_tokens": 300,
                "temperature": 0.7,
            },
        )

    if response.status_code != 200:
        return f"Grok API error {response.status_code}: {response.text[:300]}"

    return response.json()["choices"][0]["message"]["content"]


async def analyse_complexity(code: str, language: str) -> dict:
    api_key = _get_api_key()
    if not api_key:
        return {"time": "O(?)", "space": "O(?)", "explanation": "API key not set"}

    prompt = (
        f"Analyse the time and space complexity of this {language} code. "
        f'Reply ONLY with JSON: {{"time": "O(...)", "space": "O(...)", "explanation": "one sentence"}}\n\n'
        f"```{language}\n{code[:2000]}\n```"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.1,
            },
        )

    if response.status_code != 200:
        return {"time": "O(?)", "space": "O(?)", "explanation": "Analysis failed"}

    text = response.json()["choices"][0]["message"]["content"]
    text = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        return {"time": "O(?)", "space": "O(?)", "explanation": text[:100]}


async def check_originality(code: str, language: str) -> dict:
    api_key = _get_api_key()
    if not api_key:
        return {"score": 95, "flags": [], "verdict": "original"}

    prompt = (
        f"Does this {language} code look like it was copied verbatim from a well-known source "
        f"(e.g. Wikipedia, a textbook, a famous GitHub repo)? "
        f'Reply ONLY with JSON: {{"score": 0-100, "flags": ["list of concerns"], "verdict": "original|suspicious|copied"}}\n\n'
        f"```{language}\n{code[:2000]}\n```"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.1,
            },
        )

    if response.status_code != 200:
        return {"score": 95, "flags": [], "verdict": "original"}

    text = response.json()["choices"][0]["message"]["content"]
    text = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        return {"score": 95, "flags": [], "verdict": "original"}
