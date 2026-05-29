"""
Grok AI Service
Powers:
  - AI Interviewer (conversational, adaptive questioning)
  - Code hints (Socratic — doesn't give away the answer)
  - Time/space complexity analysis
  - Plagiarism detection (semantic similarity check)
  - Solution evaluation
"""

import json
from typing import AsyncGenerator, List, Optional
from openai import AsyncOpenAI   # Grok is OpenAI-compatible

from core.config import settings


# Grok client (xAI's API is OpenAI-compatible)
client = AsyncOpenAI(
    api_key=settings.GROK_API_KEY,
    base_url=settings.GROK_BASE_URL,
)

INTERVIEWER_SYSTEM_PROMPT = """You are a senior software engineer conducting a technical coding interview at a top-tier tech company (think Google, Jane Street, DeepMind). 

Your role:
- Ask probing follow-up questions about the candidate's code and design choices
- Focus on: time/space complexity, edge cases, concurrency bugs, scalability
- Be Socratic — guide with questions, never give away solutions
- Vary your difficulty: if they're doing well, push harder
- Keep responses concise (2-4 sentences max per message)
- Occasionally ask about real-world tradeoffs (e.g. "How would this behave under 10M concurrent users?")
- Cover CS fundamentals: memory models, cache coherency, ABA problem, linearizability

Tone: Professional, intellectually challenging, but fair. Like a brilliant colleague, not a gatekeeper."""


HINT_SYSTEM_PROMPT = """You are a coding mentor. A student is stuck on a problem.

Rules:
- NEVER give the solution directly
- Ask one leading question that points them in the right direction
- Reference what they've written so far
- Keep it to 1-2 sentences
- If they're very stuck, give a tiny conceptual nudge, not code"""


COMPLEXITY_SYSTEM_PROMPT = """You are an algorithms expert. Analyze the given code and return ONLY valid JSON.

Return exactly this structure:
{
  "time_complexity": "O(...)",
  "space_complexity": "O(...)",
  "time_explanation": "one sentence",
  "space_explanation": "one sentence",
  "is_optimal": true/false,
  "optimization_hint": "one sentence or null"
}"""


PLAGIARISM_SYSTEM_PROMPT = """You are a plagiarism detection system for coding interviews. 
Analyze the code and return ONLY valid JSON.

Evaluate:
- Is this clearly a standard textbook implementation? (common = expected, not plagiarism)
- Does it show signs of being copy-pasted from a specific known source?
- Is the style consistent with someone who wrote it themselves?

Return exactly:
{
  "originality_score": 0-100,
  "is_original": true/false,
  "flags": ["list of concerns if any"],
  "verdict": "Original" | "Likely original" | "Suspicious" | "Likely copied"
}"""


async def chat_with_interviewer(
    conversation_history: List[dict],
    code: str,
    problem_title: str,
    language: str,
) -> str:
    """
    Main AI interviewer conversation turn.
    conversation_history: [{role: "user"|"assistant", content: "..."}]
    """
    # Inject current code state into the system context
    system = INTERVIEWER_SYSTEM_PROMPT + f"""

Current problem: {problem_title}
Language: {language}
Current candidate code:
```{language}
{code[:3000]}  
```

React to their latest message AND their code. If they haven't responded to your last question, gently press them."""

    messages = [{"role": "system", "content": system}] + conversation_history

    response = await client.chat.completions.create(
        model=settings.GROK_MODEL,
        messages=messages,
        max_tokens=300,
        temperature=0.7,
    )
    return response.choices[0].message.content


async def stream_interviewer(
    conversation_history: List[dict],
    code: str,
    problem_title: str,
    language: str,
) -> AsyncGenerator[str, None]:
    """Streaming version — yields text chunks as they arrive from Grok."""
    system = INTERVIEWER_SYSTEM_PROMPT + f"""

Problem: {problem_title} | Language: {language}
Code:
```{language}
{code[:3000]}
```"""

    messages = [{"role": "system", "content": system}] + conversation_history

    stream = await client.chat.completions.create(
        model=settings.GROK_MODEL,
        messages=messages,
        max_tokens=300,
        temperature=0.7,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


async def get_hint(code: str, problem: str, language: str, user_question: str) -> str:
    """Socratic hint — guides without giving away."""
    response = await client.chat.completions.create(
        model=settings.GROK_MODEL,
        messages=[
            {"role": "system", "content": HINT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Problem: {problem}\nLanguage: {language}\nCode so far:\n```\n{code[:2000]}\n```\nStudent asks: {user_question}"},
        ],
        max_tokens=150,
        temperature=0.5,
    )
    return response.choices[0].message.content


async def analyze_complexity(code: str, language: str) -> dict:
    """Returns time/space complexity as structured JSON."""
    try:
        response = await client.chat.completions.create(
            model=settings.GROK_MODEL,
            messages=[
                {"role": "system", "content": COMPLEXITY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Language: {language}\n\nCode:\n```{language}\n{code[:3000]}\n```"},
            ],
            max_tokens=200,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        return {
            "time_complexity": "O(?)",
            "space_complexity": "O(?)",
            "time_explanation": "Could not analyze",
            "space_explanation": "Could not analyze",
            "is_optimal": None,
            "optimization_hint": str(e),
        }


async def check_plagiarism(code: str, language: str, problem: str) -> dict:
    """Semantic originality check via Grok."""
    try:
        response = await client.chat.completions.create(
            model=settings.GROK_MODEL,
            messages=[
                {"role": "system", "content": PLAGIARISM_SYSTEM_PROMPT},
                {"role": "user", "content": f"Problem: {problem}\nLanguage: {language}\n\nCode:\n```\n{code[:3000]}\n```"},
            ],
            max_tokens=200,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        return {"originality_score": 0, "is_original": None, "flags": [str(e)], "verdict": "Error"}


async def evaluate_solution(code: str, language: str, problem: str, test_results: list) -> str:
    """Final solution evaluation — overall feedback after submission."""
    response = await client.chat.completions.create(
        model=settings.GROK_MODEL,
        messages=[
            {"role": "system", "content": "You are a senior engineer evaluating a coding interview submission. Give structured feedback: correctness, code quality, complexity, what was done well, what to improve. Be honest but constructive. Max 150 words."},
            {"role": "user", "content": f"Problem: {problem}\nLanguage: {language}\nTest results: {test_results}\n\nCode:\n```\n{code[:3000]}\n```"},
        ],
        max_tokens=250,
        temperature=0.4,
    )
    return response.choices[0].message.content
