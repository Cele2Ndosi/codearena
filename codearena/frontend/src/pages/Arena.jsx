/**
 * Arena.jsx — The main interview workspace
 * Wires together: editor, WebSocket sync, AI interviewer, sandbox execution
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../lib/api'
import { useWebSocket } from '../hooks/useWebSocket'
import AIChat from '../components/AIChat'
import CodeEditor from '../components/CodeEditor'
import OutputPanel from '../components/OutputPanel'
import ProblemPanel from '../components/ProblemPanel'
import styles from './Arena.module.css'

const USER_ID = `user-${Math.random().toString(36).slice(2, 8)}`
const USER_NAME = 'You'
const USER_COLOR = '#4f8eff'

export default function Arena({ interviewId }) {
  const [session, setSession] = useState(null)
  const [code, setCode] = useState('# Loading...')
  const [language, setLanguage] = useState('python')
  const [remoteCursors, setRemoteCursors] = useState({})
  const [outputTab, setOutputTab] = useState('tests')
  const [testResults, setTestResults] = useState([])
  const [consoleOutput, setConsoleOutput] = useState('')
  const [wsLog, setWsLog] = useState([])
  const [complexity, setComplexity] = useState({ time_complexity: '?', space_complexity: '?' })
  const [plagiarism, setPlagiarism] = useState({ originality_score: null, verdict: '...' })
  const [running, setRunning] = useState(false)
  const [replayPos, setReplayPos] = useState(0)
  const [error, setError] = useState('')
  const sendRef = useRef(null)

  // Load session
  useEffect(() => {
    api.getInterview(interviewId)
      .then(s => {
        setSession(s)
        setLanguage(s.problem?.test_cases ? 'python' : 'python')
      })
      .catch(() => setError('Interview not found. Check the ID.'))
  }, [interviewId])

  // WebSocket message handler
  const handleWsMessage = useCallback((msg) => {
    const ts = new Date().toISOString().slice(11, 23)
    setWsLog(prev => [...prev.slice(-49), { ts, type: msg.type, payload: JSON.stringify(msg).slice(0, 60) }])

    if (msg.type === 'INIT') {
      if (msg.document) setCode(msg.document)
      if (msg.language) setLanguage(msg.language)
    }
    if (msg.type === 'EDIT_PATCH') {
      setCode(msg.document)
    }
    if (msg.type === 'CURSOR_MOVE') {
      setRemoteCursors(prev => ({ ...prev, [msg.user_id]: msg }))
    }
    if (msg.type === 'LANG_CHANGE') {
      setLanguage(msg.language)
    }
  }, [])

  const roomId = session?.room_id
  const { send, connected, participants, ping } = useWebSocket(
    roomId, USER_ID, USER_NAME, USER_COLOR, handleWsMessage
  )
  sendRef.current = send

  // Broadcast code edits
  function handleCodeChange(newCode) {
    setCode(newCode)
    sendRef.current?.({ type: 'EDIT_PATCH', document: newCode, patch: null })
  }

  // Broadcast cursor position
  function handleCursorMove(line, col) {
    sendRef.current?.({ type: 'CURSOR_MOVE', line, col })
  }

  // Language change
  function handleLangChange(lang) {
    setLanguage(lang)
    sendRef.current?.({ type: 'LANG_CHANGE', language: lang })
  }

  // Run code
  async function handleRun() {
    setRunning(true)
    setOutputTab('console')
    try {
      const result = await api.runCode(code, language)
      setConsoleOutput(result.stdout || result.stderr || 'No output')
      setWsLog(prev => [...prev, { ts: new Date().toISOString().slice(11,23), type: 'EXEC_RESULT', payload: `exit:${result.exit_code} ${result.execution_time_ms}ms` }])
    } catch (e) {
      setConsoleOutput(`Error: ${e.message}`)
    }
    setRunning(false)
  }

  // Run test cases
  async function handleTest() {
    if (!session?.problem?.test_cases?.length) {
      setConsoleOutput('No test cases defined for this problem.')
      setOutputTab('console')
      return
    }
    setRunning(true)
    setOutputTab('tests')
    try {
      const result = await api.runTests(code, language, session.problem.test_cases)
      setTestResults(result.test_results)
    } catch (e) {
      setConsoleOutput(`Error: ${e.message}`)
      setOutputTab('console')
    }
    setRunning(false)
  }

  // AI complexity analysis
  async function handleComplexity() {
    try {
      const result = await api.aiComplexity(code, language)
      setComplexity(result)
    } catch (e) {
      console.error('Complexity error:', e)
    }
  }

  // Plagiarism check
  async function handlePlagiarism() {
    try {
      const result = await api.aiPlagiarism(code, language, session?.problem?.title || '')
      setPlagiarism(result)
    } catch (e) {
      console.error('Plagiarism error:', e)
    }
  }

  // Submit
  async function handleSubmit() {
    await handleTest()
    await handleComplexity()
    await handlePlagiarism()
  }

  if (error) {
    return (
      <div className={styles.errorPage}>
        <div className={styles.errorBox}>
          <div className={styles.logo}>⬡ CodeArena</div>
          <p>{error}</p>
          <button className={styles.backBtn} onClick={() => window.location.hash = '#/'}>← Back to Home</button>
        </div>
      </div>
    )
  }

  if (!session) {
    return <div className={styles.loading}>Loading interview session...</div>
  }

  return (
    <div className={styles.layout}>
      {/* NAV */}
      <nav className={styles.nav}>
        <div className={styles.logo}>⬡ CodeArena</div>
        <div className={styles.navMeta}>
          <span className={styles.roomId}>Room: {session.room_id}</span>
          <span className={`${styles.badge} ${connected ? styles.badgeLive : styles.badgeOff}`}>
            {connected ? `● Live · ${ping ?? '—'}ms` : '○ Reconnecting...'}
          </span>
          <div className={styles.avatars}>
            {participants.map(p => (
              <div key={p.user_id} className={styles.av} style={{ background: p.color }} title={p.name}>
                {p.name[0].toUpperCase()}
              </div>
            ))}
          </div>
        </div>
      </nav>

      {/* ARENA */}
      <div className={styles.arena}>
        {/* LEFT */}
        <ProblemPanel problem={session.problem} />

        {/* CENTER */}
        <div className={styles.center}>
          <CodeEditor
            code={code}
            language={language}
            remoteCursors={Object.values(remoteCursors)}
            onChange={handleCodeChange}
            onCursorMove={handleCursorMove}
            onLangChange={handleLangChange}
            onRun={handleRun}
            onSubmit={handleSubmit}
            running={running}
          />
          <OutputPanel
            tab={outputTab}
            onTabChange={setOutputTab}
            testResults={testResults}
            consoleOutput={consoleOutput}
            wsLog={wsLog}
          />
        </div>

        {/* RIGHT */}
        <AIChat
          session={session}
          code={code}
          language={language}
          complexity={complexity}
          plagiarism={plagiarism}
          replayPos={replayPos}
          onReplayPos={setReplayPos}
          onRequestComplexity={handleComplexity}
          onRequestPlagiarism={handlePlagiarism}
        />
      </div>
    </div>
  )
}
