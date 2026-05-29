/**
 * Home page — create a new interview or join an existing one.
 */

import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import styles from './Home.module.css'

export default function Home() {
  const [problems, setProblems] = useState([])
  const [selectedProblem, setSelectedProblem] = useState('')
  const [candidateName, setCandidateName] = useState('')
  const [joinId, setJoinId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.listProblems()
      .then(setProblems)
      .catch(() => setError('Could not reach backend. Is it running?'))
  }, [])

  async function handleCreate(e) {
    e.preventDefault()
    if (!selectedProblem || !candidateName.trim()) {
      setError('Please select a problem and enter your name.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const session = await api.createInterview({
        problem_id: selectedProblem,
        candidate_name: candidateName,
      })
      window.location.hash = `#/arena/${session.interview_id}`
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleJoin(e) {
    e.preventDefault()
    if (!joinId.trim()) return
    window.location.hash = `#/arena/${joinId.trim()}`
  }

  const diffColor = { hard: '#ff4757', medium: '#ff9f43', easy: '#2ed573' }

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <div className={styles.logo}>⬡ CodeArena</div>
        <p className={styles.tagline}>
          Distributed real-time coding interviews — powered by Grok AI
        </p>
      </div>

      <div className={styles.cards}>
        {/* CREATE */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Start Interview</h2>
          <form onSubmit={handleCreate} className={styles.form}>
            <label className={styles.label}>Your name</label>
            <input
              className={styles.input}
              placeholder="e.g. Alice"
              value={candidateName}
              onChange={e => setCandidateName(e.target.value)}
            />

            <label className={styles.label}>Select problem</label>
            <div className={styles.problemList}>
              {problems.map(p => (
                <div
                  key={p.id}
                  className={`${styles.problemRow} ${selectedProblem === p.id ? styles.selected : ''}`}
                  onClick={() => setSelectedProblem(p.id)}
                >
                  <span className={styles.probTitle}>{p.title}</span>
                  <span className={styles.diffTag} style={{ color: diffColor[p.difficulty] }}>
                    {p.difficulty.toUpperCase()}
                  </span>
                </div>
              ))}
              {problems.length === 0 && !error && (
                <div className={styles.loading}>Loading problems...</div>
              )}
            </div>

            {error && <div className={styles.error}>{error}</div>}

            <button className={styles.btn} type="submit" disabled={loading}>
              {loading ? 'Creating...' : '▶ Start Interview'}
            </button>
          </form>
        </div>

        {/* JOIN */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Join Session</h2>
          <p className={styles.cardSub}>Enter an interview ID to join as a collaborator or observer.</p>
          <form onSubmit={handleJoin} className={styles.form}>
            <label className={styles.label}>Interview ID</label>
            <input
              className={styles.input}
              placeholder="e.g. 3f2a1b9c-..."
              value={joinId}
              onChange={e => setJoinId(e.target.value)}
            />
            <button className={styles.btnGhost} type="submit">→ Join Room</button>
          </form>

          <div className={styles.features}>
            <div className={styles.featureItem}>🔌 WebSocket real-time sync</div>
            <div className={styles.featureItem}>🤖 Grok AI interviewer</div>
            <div className={styles.featureItem}>🛡 Sandboxed execution</div>
            <div className={styles.featureItem}>📼 Full session replay</div>
            <div className={styles.featureItem}>🔍 Plagiarism detection</div>
            <div className={styles.featureItem}>⏱ Complexity analysis</div>
          </div>
        </div>
      </div>
    </div>
  )
}
