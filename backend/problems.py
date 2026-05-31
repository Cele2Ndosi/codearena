"""
problems.py — Live problem fetcher from LeetCode's public GraphQL API.

LeetCode exposes a public GraphQL endpoint (no auth required) that we use to:
- Fetch a random daily challenge
- Search problems by topic/difficulty
- Get full problem details (description, examples, constraints)

We cache results in memory for 10 minutes to avoid hammering the API.
"""

import asyncio
import time
import re
import httpx

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com",
    "User-Agent": "Mozilla/5.0 (compatible; CodeArena/1.0)",
}

# In-memory cache: {cache_key: (timestamp, data)}
_cache: dict[str, tuple[float, any]] = {}
CACHE_TTL = 600  # 10 minutes


def _cached(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def _set_cache(key: str, data):
    _cache[key] = (time.time(), data)


# --- GraphQL queries ---

DAILY_CHALLENGE_QUERY = """
query questionOfToday {
  activeDailyCodingChallengeQuestion {
    date
    link
    question {
      questionId
      title
      titleSlug
      difficulty
      topicTags { name }
      content
      exampleTestcases
      hints
    }
  }
}
"""

PROBLEM_DETAIL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    titleSlug
    difficulty
    topicTags { name }
    content
    exampleTestcases
    hints
    stats
    similarQuestions
  }
}
"""

PROBLEM_LIST_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      questionId
      title
      titleSlug
      difficulty
      topicTags { name }
      status
      isFavor
    }
  }
}
"""


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities for plain display."""
    if not html:
        return ""
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", html)
    text = re.sub(r"<sub>(.*?)</sub>", r"_\1", text)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_problem(q: dict) -> dict:
    """Normalise a raw LeetCode question dict into our app's format."""
    content = _strip_html(q.get("content") or "")
    # Split content into description + examples + constraints sections
    desc = content
    examples = q.get("exampleTestcases") or ""
    constraints = []

    # Try to extract constraints block
    if "Constraints:" in content:
        parts = content.split("Constraints:", 1)
        desc = parts[0].strip()
        raw_constraints = parts[1].strip()
        for line in raw_constraints.splitlines():
            line = line.strip()
            if line:
                constraints.append(("", line))

    # Extract examples from description
    if "Example 1:" in desc:
        parts = desc.split("Example 1:", 1)
        desc = parts[0].strip()
        examples = "Example 1:" + parts[1].split("Example 2:")[0] if "Example 2:" in parts[1] else "Example 1:" + parts[1]
        examples = examples.strip()

    tags = [t["name"] for t in (q.get("topicTags") or [])]
    difficulty = (q.get("difficulty") or "Medium").lower()

    return {
        "id": q.get("titleSlug", "unknown"),
        "title": q.get("title", "Untitled"),
        "difficulty": difficulty,
        "topics": tags[:4],  # cap at 4 tags for UI
        "description": desc[:1200],
        "examples": examples[:800],
        "constraints": constraints[:6],
        "hints": q.get("hints") or [],
        "leetcode_url": f"https://leetcode.com/problems/{q.get('titleSlug', '')}",
        "starter_code": {
            "python": _generate_starter(q.get("title", ""), tags),
        },
        "test_harness": _generic_test_harness(),
        "interviewer_context": (
            f"The candidate is solving '{q.get('title')}' (LeetCode, {difficulty}). "
            f"Topics: {', '.join(tags[:3])}. "
            "Probe their understanding of time/space complexity, edge cases, and alternative approaches."
        ),
    }


def _generate_starter(title: str, tags: list[str]) -> str:
    """Generate a basic Python starter stub based on the problem title."""
    class_name = "Solution"
    return (
        f"class {class_name}:\n"
        f'    """\n'
        f"    {title}\n"
        f"    Topics: {', '.join(tags[:3]) if tags else 'General'}\n"
        f'    """\n\n'
        f"    def solve(self, *args):\n"
        f"        # TODO: implement your solution here\n"
        f"        pass\n\n\n"
        f"# Test your solution\n"
        f"sol = Solution()\n"
        f"# print(sol.solve(...))\n"
    )


def _generic_test_harness() -> str:
    """
    A generic test harness for LeetCode problems.
    Since we don't know the method signature, we run the user's code
    and just check it doesn't crash, then let the AI evaluate correctness.
    """
    return '''
def run_tests(SolutionClass):
    results = []

    # Test 1: Class instantiates without error
    try:
        sol = SolutionClass()
        results.append(("Solution class instantiates", True, "0.0ms"))
    except Exception as e:
        results.append(("Solution class instantiates", False, str(e)[:60]))
        return results

    # Test 2: Has at least one method beyond __init__
    try:
        methods = [m for m in dir(sol) if not m.startswith("_")]
        assert len(methods) > 0, "No public methods found"
        results.append((f"Has method: {methods[0]}", True, "0.0ms"))
    except Exception as e:
        results.append(("Has public method", False, str(e)[:60]))

    return results
'''


# --- Public API ---

async def fetch_daily_challenge() -> dict | None:
    """Fetch today's LeetCode daily challenge."""
    cached = _cached("daily")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.post(
                LEETCODE_GRAPHQL,
                json={"query": DAILY_CHALLENGE_QUERY},
            )
        data = resp.json()
        q = data["data"]["activeDailyCodingChallengeQuestion"]["question"]
        result = _format_problem(q)
        _set_cache("daily", result)
        return result
    except Exception as e:
        print(f"[problems] fetch_daily_challenge failed: {e}")
        return None


async def fetch_problem(title_slug: str) -> dict | None:
    """Fetch a specific problem by its title slug."""
    cache_key = f"problem:{title_slug}"
    cached = _cached(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.post(
                LEETCODE_GRAPHQL,
                json={
                    "query": PROBLEM_DETAIL_QUERY,
                    "variables": {"titleSlug": title_slug},
                },
            )
        data = resp.json()
        q = data["data"]["question"]
        if not q:
            return None
        result = _format_problem(q)
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"[problems] fetch_problem({title_slug}) failed: {e}")
        return None


async def fetch_problem_list(
    difficulty: str = "",
    tags: list[str] | None = None,
    search: str = "",
    limit: int = 50,
    skip: int = 0,
) -> dict:
    """
    Fetch a paginated, filtered list of problems from LeetCode.
    Returns {"problems": [...], "total": N, "skip": N, "limit": N}
    """
    cache_key = f"list:{difficulty}:{','.join(tags or [])}:{search}:{skip}:{limit}"
    cached = _cached(cache_key)
    if cached:
        return cached

    filters = {}
    if difficulty:
        filters["difficulty"] = difficulty.upper()
    if tags:
        filters["tags"] = tags
    if search:
        filters["searchKeywords"] = search

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
            resp = await client.post(
                LEETCODE_GRAPHQL,
                json={
                    "query": PROBLEM_LIST_QUERY,
                    "variables": {
                        "categorySlug": "",
                        "limit": limit,
                        "skip": skip,
                        "filters": filters,
                    },
                },
            )
        data = resp.json()
        plist = data["data"]["problemsetQuestionList"]
        total = plist.get("total", 0)
        questions = plist.get("questions", [])
        problems = [
            {
                "id": q["titleSlug"],
                "title": q["title"],
                "difficulty": q["difficulty"].lower(),
                "topics": [t["name"] for t in (q.get("topicTags") or [])][:4],
            }
            for q in questions
        ]
        result = {"problems": problems, "total": total, "skip": skip, "limit": limit}
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"[problems] fetch_problem_list failed: {e}")
        return {"problems": [], "total": 0, "skip": skip, "limit": limit}


# Fallback list when LeetCode is unreachable
FALLBACK_PROBLEMS = [
    {"id": "two-sum",                   "title": "Two Sum",                   "difficulty": "easy",   "topics": ["Array", "Hash Table"]},
    {"id": "lru-cache",                 "title": "LRU Cache",                 "difficulty": "medium", "topics": ["Hash Table", "Linked List", "Design"]},
    {"id": "median-of-two-sorted-arrays","title": "Median of Two Sorted Arrays","difficulty": "hard",   "topics": ["Array", "Binary Search"]},
    {"id": "design-twitter",            "title": "Design Twitter",            "difficulty": "medium", "topics": ["Hash Table", "Heap", "Design"]},
    {"id": "word-search-ii",            "title": "Word Search II",            "difficulty": "hard",   "topics": ["Trie", "Backtracking"]},
]


async def list_problems(
    difficulty: str = "",
    tags: list[str] | None = None,
    search: str = "",
    limit: int = 50,
    skip: int = 0,
) -> dict:
    """Return paginated problems from LeetCode with fallback."""
    result = await fetch_problem_list(
        difficulty=difficulty, tags=tags, search=search, limit=limit, skip=skip
    )
    if not result["problems"]:
        return {"problems": FALLBACK_PROBLEMS, "total": len(FALLBACK_PROBLEMS), "skip": 0, "limit": limit}
    return result


async def get_problem(problem_id: str) -> dict | None:
    """Get full problem details by title slug."""
    return await fetch_problem(problem_id)
