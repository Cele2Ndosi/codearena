/**
 * Progress.jsx — User progress dashboard.
 *
 * Shows: problems solved, solve rate, recent submissions,
 * solved problem list, and the global leaderboard.
 * Fetched live from /progress/{username} and /leaderboard.
 */

import { useState, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function formatTime(secs) {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function timeAgo(unix) {
  if (!unix) return "—";
  const diff = Date.now() / 1000 - unix;
  if (diff < 60)   return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function Progress({ userName, onClose }) {
  const [progress, setProgress]       = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [activeTab, setActiveTab]     = useState("overview");
  const [loading, setLoading]         = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/progress/${encodeURIComponent(userName)}`).then(r => r.json()),
      fetch(`${API_URL}/leaderboard`).then(r => r.json()),
    ]).then(([prog, lb]) => {
      setProgress(prog);
      setLeaderboard(lb.leaderboard || []);
    }).finally(() => setLoading(false));
  }, [userName]);

  const solveRate = progress?.solve_rate ?? 0;
  const solved    = progress?.problems_solved ?? 0;
  const attempted = progress?.problems_attempted ?? 0;

  return (
    <div className="progress-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="progress-modal">
        {/* Header */}
        <div className="prog-header">
          <div>
            <div className="prog-title">📊 Progress</div>
            <div className="prog-sub">{userName}</div>
          </div>
          <button className="prog-close" onClick={onClose}>✕</button>
        </div>

        {/* Tabs */}
        <div className="prog-tabs">
          {["overview", "solved", "recent", "leaderboard"].map(t => (
            <button key={t} className={`prog-tab ${activeTab === t ? "prog-tab-active" : ""}`}
              onClick={() => setActiveTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        <div className="prog-body">
          {loading ? (
            <div className="prog-loading">Loading...</div>
          ) : activeTab === "overview" ? (
            <div className="prog-overview">
              {/* Stat cards */}
              <div className="stat-grid">
                <div className="stat-card">
                  <div className="stat-val" style={{color:"var(--success)"}}>{solved}</div>
                  <div className="stat-label">Solved</div>
                </div>
                <div className="stat-card">
                  <div className="stat-val" style={{color:"var(--accent)"}}>{attempted}</div>
                  <div className="stat-label">Attempted</div>
                </div>
                <div className="stat-card">
                  <div className="stat-val" style={{color:"var(--warn)"}}>{solveRate}%</div>
                  <div className="stat-label">Solve Rate</div>
                </div>
                <div className="stat-card">
                  <div className="stat-val" style={{color:"var(--accent2)"}}>{progress?.total_submissions ?? 0}</div>
                  <div className="stat-label">Submissions</div>
                </div>
              </div>

              {/* Solve rate bar */}
              <div className="prog-section">
                <div className="prog-section-label">Overall Progress</div>
                <div className="prog-bar-bg">
                  <div className="prog-bar-fill" style={{width:`${solveRate}%`}} />
                </div>
                <div style={{display:"flex",justifyContent:"space-between",fontSize:11,color:"var(--text3)",marginTop:4}}>
                  <span>{solved} solved</span>
                  <span>{attempted} attempted</span>
                </div>
              </div>

              {/* Avg time */}
              {progress?.avg_solve_time_s > 0 && (
                <div className="prog-section">
                  <div className="prog-section-label">Avg solve time</div>
                  <div style={{fontSize:20,fontFamily:"var(--mono)",fontWeight:700,color:"var(--text)"}}>
                    {formatTime(progress.avg_solve_time_s)}
                  </div>
                </div>
              )}

              {solved === 0 && (
                <div className="prog-empty">No problems solved yet. Submit a solution to start tracking!</div>
              )}
            </div>

          ) : activeTab === "solved" ? (
            <div className="prog-list">
              {progress?.solved_problems?.length === 0
                ? <div className="prog-empty">No solved problems yet.</div>
                : progress?.solved_problems?.map((p, i) => (
                  <div key={p.problem_id} className="prog-row">
                    <div className="prog-row-left">
                      <span className="prog-rank">#{i + 1}</span>
                      <div>
                        <div className="prog-row-title">{p.problem_title || p.problem_id}</div>
                        <div className="prog-row-meta">
                          {p.language} · best time {formatTime(p.best_time_s)}
                          {p.complexity_time && ` · ${p.complexity_time}`}
                        </div>
                      </div>
                    </div>
                    <div style={{textAlign:"right"}}>
                      <div style={{fontSize:10,color:"var(--success)",fontWeight:700}}>✓ SOLVED</div>
                      <div style={{fontSize:10,color:"var(--text3)"}}>{timeAgo(p.last_solved)}</div>
                    </div>
                  </div>
                ))
              }
            </div>

          ) : activeTab === "recent" ? (
            <div className="prog-list">
              {progress?.recent_submissions?.length === 0
                ? <div className="prog-empty">No submissions yet.</div>
                : progress?.recent_submissions?.map((s, i) => (
                  <div key={i} className="prog-row">
                    <div className="prog-row-left">
                      <span className={`sub-dot ${s.passed ? "dot-pass" : "dot-fail"}`} />
                      <div>
                        <div className="prog-row-title">{s.problem_title || s.problem_id}</div>
                        <div className="prog-row-meta">{s.language} · {s.tests} tests · {formatTime(s.time_s)}</div>
                      </div>
                    </div>
                    <div style={{textAlign:"right"}}>
                      <div style={{fontSize:10,fontWeight:700,color: s.passed ? "var(--success)" : "var(--danger)"}}>
                        {s.passed ? "PASS" : "FAIL"}
                      </div>
                      <div style={{fontSize:10,color:"var(--text3)"}}>{timeAgo(s.submitted_at)}</div>
                    </div>
                  </div>
                ))
              }
            </div>

          ) : activeTab === "leaderboard" ? (
            <div className="prog-list">
              {leaderboard.length === 0
                ? <div className="prog-empty">No submissions yet. Be the first!</div>
                : leaderboard.map(entry => (
                  <div key={entry.user_name}
                    className={`prog-row ${entry.user_name === userName ? "prog-row-me" : ""}`}>
                    <div className="prog-row-left">
                      <span className="prog-rank" style={{
                        color: entry.rank === 1 ? "#ffd700" : entry.rank === 2 ? "#c0c0c0" : entry.rank === 3 ? "#cd7f32" : "var(--text3)"
                      }}>
                        {entry.rank === 1 ? "🥇" : entry.rank === 2 ? "🥈" : entry.rank === 3 ? "🥉" : `#${entry.rank}`}
                      </span>
                      <div>
                        <div className="prog-row-title">
                          {entry.user_name}
                          {entry.user_name === userName && <span style={{color:"var(--accent)",fontSize:10,marginLeft:6}}>you</span>}
                        </div>
                        <div className="prog-row-meta">{entry.attempted} attempted · {entry.submissions} submissions</div>
                      </div>
                    </div>
                    <div style={{textAlign:"right"}}>
                      <div style={{fontSize:16,fontFamily:"var(--mono)",fontWeight:700,color:"var(--success)"}}>{entry.solved}</div>
                      <div style={{fontSize:10,color:"var(--text3)"}}>solved</div>
                    </div>
                  </div>
                ))
              }
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
