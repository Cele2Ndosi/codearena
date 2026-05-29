/**
 * API client — wraps all backend REST calls
 * Base URL from VITE_API_URL env var (default: localhost:8000)
 */

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API error ${res.status}: ${err}`)
  }
  return res.json()
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}

// ── Interviews ──────────────────────────────────────────────────────────────

export const api = {
  // Problems
  listProblems: () => get('/api/interviews/problems'),
  getProblem: (id) => get(`/api/interviews/problems/${id}`),

  // Sessions
  createInterview: (body) => post('/api/interviews/', body),
  getInterview: (id) => get(`/api/interviews/${id}`),
  getReplay: (id) => get(`/api/interviews/${id}/replay`),

  // Code execution
  runCode: (code, language, stdin = '') =>
    post('/api/execute/run', { code, language, stdin }),

  runTests: (code, language, testCases) =>
    post('/api/execute/test', { code, language, test_cases: testCases }),

  // AI Interviewer
  aiChat: (conversation, code, problemTitle, language) =>
    post('/api/ai/chat', { conversation, code, problem_title: problemTitle, language }),

  aiHint: (code, problem, language, question) =>
    post('/api/ai/hint', { code, problem, language, question }),

  aiComplexity: (code, language) =>
    post('/api/ai/complexity', { code, language }),

  aiPlagiarism: (code, language, problem) =>
    post('/api/ai/plagiarism', { code, language, problem }),

  aiEvaluate: (code, language, problem, testResults) =>
    post('/api/ai/evaluate', { code, language, problem, test_results: testResults }),

  // Streaming AI chat — returns a ReadableStream
  aiChatStream: async (conversation, code, problemTitle, language) => {
    const res = await fetch(`${BASE}/api/ai/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation,
        code,
        problem_title: problemTitle,
        language,
      }),
    })
    if (!res.ok) throw new Error(`Stream error ${res.status}`)
    return res.body.getReader()
  },
}
