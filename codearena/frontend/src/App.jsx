import { useState, useCallback, useEffect, useRef } from "react";
import Editor from "./Editor";
import AIChat from "./AIChat";
import { useWebSocket } from "./useWebSocket";
import Progress from "./Progress";
import "./index.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function formatTime(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const DIFFICULTY_COLORS = {
  easy:   { bg: "rgba(46,213,115,.12)",  color: "#2ed573", border: "rgba(46,213,115,.25)"  },
  medium: { bg: "rgba(255,159,67,.12)",  color: "#ff9f43", border: "rgba(255,159,67,.25)"  },
  hard:   { bg: "rgba(255,71,87,.12)",   color: "#ff4757", border: "rgba(255,71,87,.25)"   },
};

export default function App() {
  const [roomId, setRoomId] = useState(() => {
    const match = window.location.pathname.match(/\/room\/([a-z0-9-]+)/i);
    return match ? match[1] : null;
  });
  const [userName, setUserName]     = useState("");
  const [nameInput, setNameInput]   = useState("");
  const [joined, setJoined]         = useState(false);
  const [problems, setProblems]     = useState([]);
  const [selectedProblem, setSelectedProblem] = useState(null);
  const [currentProblem, setCurrentProblem]   = useState(null);
  const [roomInput, setRoomInput]   = useState("");

  const [code, setCode]         = useState("");
  const [language, setLanguage] = useState("python");
  const [peers, setPeers]       = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [activeTab, setActiveTab]       = useState("tests");
  const [testResults, setTestResults]   = useState([]);
  const [consoleOutput, setConsoleOutput] = useState("");
  const [complexity, setComplexity]     = useState(null);
  const [originality, setOriginality]   = useState(null);
  const [timeRemaining, setTimeRemaining] = useState(45 * 60);

  const [diffFilter, setDiffFilter]     = useState("");
  const [searchQuery, setSearchQuery]   = useState("");
  const [loadingProblems, setLoadingProblems] = useState(false);
  const [totalProblems, setTotalProblems]     = useState(0);
  const [problemSkip, setProblemSkip]         = useState(0);
  const PROB_LIMIT = 50;
  const searchTimer = useRef(null);

  const loadProblems = (difficulty = "", search = "", skip = 0, append = false) => {
    setLoadingProblems(true);
    const params = new URLSearchParams();
    if (difficulty) params.set("difficulty", difficulty);
    if (search)     params.set("search", search);
    params.set("limit", PROB_LIMIT);
    params.set("skip", skip);
    fetch(`${API_URL}/problems?${params}`)
      .then(r => r.json())
      .then(data => {
        const newProbs = data.problems || [];
        setTotalProblems(data.total || newProbs.length);
        setProblemSkip(skip + newProbs.length);
        if (append) {
          setProblems(prev => [...prev, ...newProbs]);
        } else {
          setProblems(newProbs);
          if (newProbs.length && !selectedProblem) setSelectedProblem(newProbs[0].id);
        }
      })
      .catch(() => {
        if (!append) {
          const fallback = [
            { id: "two-sum",        title: "Two Sum",        difficulty: "easy",   topics: ["Array", "Hash Table"] },
            { id: "lru-cache",      title: "LRU Cache",      difficulty: "medium", topics: ["Design", "Linked List"] },
            { id: "word-search-ii", title: "Word Search II", difficulty: "hard",   topics: ["Trie", "Backtracking"] },
          ];
          setProblems(fallback);
          setTotalProblems(fallback.length);
          if (!selectedProblem) setSelectedProblem("two-sum");
        }
      })
      .finally(() => setLoadingProblems(false));
  };

  const loadMore = () => {
    if (!loadingProblems && problems.length < totalProblems) {
      loadProblems(diffFilter, searchQuery, problemSkip, true);
    }
  };

  const loadDaily = () => {
    setLoadingProblems(true);
    fetch(`${API_URL}/problems/daily`)
      .then(r => r.json())
      .then(data => {
        if (data.problem) {
          setProblems([data.problem]);
          setTotalProblems(1);
          setSelectedProblem(data.problem.id);
        }
      })
      .finally(() => setLoadingProblems(false));
  };

  const handleSearch = (q) => {
    setSearchQuery(q);
    setProblemSkip(0);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      loadProblems(diffFilter, q, 0, false);
    }, 400);
  };

  // Load on mount
  useEffect(() => { loadProblems(); }, []);

  // Fetch available languages from backend
  const [languages, setLanguages] = useState([
    { id: "python", label: "Python", available: true, version: "" },
  ]);
  useEffect(() => {
    fetch(`${API_URL}/languages`)
      .then(r => r.json())
      .then(data => {
        if (data.languages?.length) setLanguages(data.languages);
      })
      .catch(() => {});  // keep fallback on error
  }, []);

  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
      case "room_state":
        if (msg.code) setCode(msg.code);
        if (msg.language) setLanguage(msg.language);
        setPeers(msg.peers || []);
        setTimeRemaining(msg.time_remaining || 45 * 60);
        if (msg.problem) {
          setCurrentProblem(msg.problem);
          setChatMessages([{ role: "ai", text: `Welcome! I'm ArenaAI. Today's problem: **${msg.problem.title}**. ${msg.problem.interviewer_context?.split(".")[0]}.` }]);
        }
        break;
      case "code_sync":
        setCode(msg.code);
        setLanguage(msg.language);
        break;
      case "submission_saved":
        if (msg.solved) setSolvedCount(prev => prev + 1);
        break;
      case "switch_problem":
        // A peer switched the problem — fetch and update locally
        fetch(`${API_URL}/problems/${msg.problem_id}`)
          .then(r => r.json())
          .then(data => {
            if (data.problem) {
              setCurrentProblem(data.problem);
              setSelectedProblem(msg.problem_id);
              setCode(msg.code || "");
              setTestResults([]);
              setConsoleOutput("");
              setComplexity(null);
              setOriginality(null);
            }
          });
        break;
      case "cursor_sync":
        setPeers(prev => {
          const exists = prev.find(p => p.name === msg.name);
          if (exists) return prev.map(p => p.name === msg.name ? { ...p, line: msg.line, col: msg.col, color: msg.color } : p);
          return [...prev, { name: msg.name, color: msg.color, line: msg.line, col: msg.col }];
        });
        break;
      case "ai_message":
        setChatMessages(prev => [...prev, { role: "ai", text: msg.message }]);
        break;
      case "test_results":
        setTestResults(msg.results || []);
        setActiveTab("tests");
        break;
      case "run_result":
        setConsoleOutput(
          `Exit: ${msg.exit_code} | ${msg.wall_time_ms}ms\n` +
          (msg.timed_out ? "⚠️ Timed out\n" : "") +
          (msg.stdout ? `\n--- stdout ---\n${msg.stdout}` : "") +
          (msg.stderr ? `\n--- stderr ---\n${msg.stderr}` : "")
        );
        setActiveTab("console");
        break;
      case "complexity":
        setComplexity({ time: msg.time, space: msg.space, explanation: msg.explanation });
        break;
      case "originality":
        setOriginality({ score: msg.score, verdict: msg.verdict, flags: msg.flags });
        break;
      case "user_joined":
        setPeers(msg.peers || []);
        break;
      case "user_left":
        setPeers(msg.peers || []);
        break;
      case "timer":
        setTimeRemaining(msg.remaining);
        break;
      case "time_up":
        setChatMessages(prev => [...prev, { role: "ai", text: "⏰ Time is up! Please submit your final solution." }]);
        break;
      default: break;
    }
  }, []);

  const { send, connected } = useWebSocket({
    roomId: joined ? roomId : null,
    userName,
    onMessage: handleMessage,
  });

  const handleCodeChange = useCallback((newCode, newLang) => {
    setCode(newCode);
    setLanguage(newLang);
    send({ type: "code_edit", code: newCode, language: newLang });
  }, [send]);

  const handleChat = useCallback((message) => {
    setChatMessages(prev => [...prev, { role: "user", text: message }]);
    send({ type: "chat", message });
  }, [send]);

  const handleRun    = useCallback(() => send({ type: "run_code" }), [send]);
  const handleSubmit = useCallback(() => {
    send({ type: "submit_code" });
    setChatMessages(prev => [...prev, { role: "ai", text: "Running your code against the test suite..." }]);
  }, [send]);
  const handleHint = useCallback(() => send({ type: "get_hint" }), [send]);

  const switchProblem = async (problemId) => {
    if (problemId === (currentProblem?.id || selectedProblem)) {
      setSwitcherOpen(false);
      return;
    }
    setSwitchingTo(problemId);
    try {
      const res = await fetch(`${API_URL}/problems/${problemId}`);
      if (!res.ok) throw new Error("Failed to fetch problem");
      const data = await res.json();
      const prob = data.problem;
      if (!prob) throw new Error("No problem data");
      // Update local state
      setCurrentProblem(prob);
      setSelectedProblem(problemId);
      const starterCode = prob.starter_code?.python || "class Solution:\n    def solve(self):\n        pass\n";
      setCode(starterCode);
      setTestResults([]);
      setConsoleOutput("");
      setComplexity(null);
      setOriginality(null);
      // Broadcast to all peers
      send({ type: "switch_problem", problem_id: problemId, code: starterCode });
      setChatMessages(prev => [...prev, {
        role: "ai",
        text: `Switched to: **${prob.title}** (${prob.difficulty}). ${prob.interviewer_context?.split(".")[0] || "Good luck!"}.`
      }]);
      setSwitcherOpen(false);
    } catch (err) {
      console.error("switchProblem error:", err);
    } finally {
      setSwitchingTo(null);
    }
  };

  const [creating, setCreating] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [solvedCount, setSolvedCount] = useState(0);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [switcherFilter, setSwitcherFilter] = useState("");
  const [switchingTo, setSwitchingTo] = useState(null);
  const [createError, setCreateError] = useState("");

  const createRoom = async () => {
    if (!selectedProblem) { setCreateError("Pick a problem first."); return; }
    setCreating(true);
    setCreateError("");
    try {
      const res = await fetch(`${API_URL}/rooms?problem_id=${selectedProblem}`, { method: "POST" });
      if (!res.ok) throw new Error(`Server returned ${res.status}: ${await res.text()}`);
      const data = await res.json();
      if (!data.room_id) throw new Error("No room_id in response: " + JSON.stringify(data));
      setRoomId(data.room_id);
      window.history.pushState({}, "", `/room/${data.room_id}`);
    } catch (err) {
      setCreateError(`Could not create room: ${err.message}. Is the backend running on port 8000?`);
      console.error("createRoom error:", err);
    } finally {
      setCreating(false);
    }
  };

  const joinRoom = () => {
    if (!nameInput.trim()) return;
    setUserName(nameInput.trim());
    // Set initial chat greeting
    const prob = problems.find(p => p.id === selectedProblem);
    setChatMessages([{
      role: "ai",
      text: `Welcome! I'm ArenaAI, your technical interviewer. Today's problem: **${prob?.title || "coding challenge"}**. Before you start — can you explain your high-level approach?`
    }]);
    setJoined(true);
  };

  // --- LOBBY ---
  if (!joined) {
    return (
      <div className="lobby">
        <div className="lobby-card">
          <div className="lobby-logo">⬡ CodeArena</div>
          <p className="lobby-sub">Distributed Real-Time Interview Platform</p>

          {!roomId ? (
            <>
              {/* Filters */}
              <div className="filter-row">
                <div className="picker-label" style={{margin:0}}>Problems from LeetCode</div>
                <div style={{display:"flex",gap:4}}>
                  {["","easy","medium","hard"].map(d => (
                    <button key={d} className={`filter-btn ${diffFilter===d?"filter-active":""}`}
                      onClick={() => { setDiffFilter(d); setProblemSkip(0); loadProblems(d, searchQuery, 0, false); }}>
                      {d || "All"}
                    </button>
                  ))}
                  <button className="filter-btn filter-daily" onClick={loadDaily}>⚡ Daily</button>
                </div>
              </div>

              {/* Problem picker */}
              <input className="lobby-input" style={{marginBottom:6,fontSize:12}}
                placeholder="Search problems..."
                value={searchQuery}
                onChange={e => handleSearch(e.target.value)}
              />
              <div className="problem-picker">
                {loadingProblems && problems.length === 0
                  ? <div className="loading-hint">Fetching from LeetCode...</div>
                  : null}
                {problems.map(p => {
                  const dc = DIFFICULTY_COLORS[p.difficulty] || DIFFICULTY_COLORS.medium;
                  return (
                    <div
                      key={p.id}
                      className={`prob-option ${selectedProblem === p.id ? "prob-selected" : ""}`}
                      onClick={() => setSelectedProblem(p.id)}
                    >
                      <div className="prob-opt-left">
                        <span className="prob-opt-title">{p.title}</span>
                        <div className="prob-opt-tags">
                          {p.topics.map(t => <span key={t} className="opt-tag">{t}</span>)}
                        </div>
                      </div>
                      <span className="prob-opt-diff" style={{ color: dc.color, background: dc.bg, border: `1px solid ${dc.border}` }}>
                        {p.difficulty.toUpperCase()}
                      </span>
                    </div>
                  );
                })}
                {problems.length < totalProblems && (
                    <button className="load-more-btn" style={{margin:"6px 0"}}
                      onClick={loadMore} disabled={loadingProblems}>
                      {loadingProblems ? "Loading..." : `Load ${Math.min(50, totalProblems - problems.length)} more...`}
                    </button>
                  )}
              </div>

              {createError && <div className="create-error">{createError}</div>}
              <button className="btn btn-primary lobby-btn" onClick={createRoom} disabled={!selectedProblem || creating}>
                {creating ? "Creating..." : "Create Room →"}
              </button>
              <div className="lobby-divider">or join existing room</div>
              <div style={{ display: "flex", gap: 8 }}>
                <input className="lobby-input" style={{ marginBottom: 0, flex: 1 }} placeholder="Room ID"
                  value={roomInput} onChange={e => setRoomInput(e.target.value)} />
                <button className="btn btn-ghost" onClick={() => {
                  setRoomId(roomInput.trim());
                  window.history.pushState({}, "", `/room/${roomInput.trim()}`);
                }}>Join</button>
              </div>
            </>
          ) : (
            <>
              <div className="room-id-display">
                Room: <code>{roomId}</code>
                <button className="copy-btn" onClick={() => navigator.clipboard.writeText(window.location.href)}>
                  Copy Link
                </button>
              </div>
              <input className="lobby-input" placeholder="Your name" value={nameInput}
                onChange={e => setNameInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && joinRoom()} autoFocus />
              <button className="btn btn-primary lobby-btn" onClick={joinRoom}>
                Join Interview →
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  // --- ARENA ---
  const timerDanger = timeRemaining < 5 * 60;
  const myPeers = peers.filter(p => p.name !== userName);
  const prob = currentProblem || problems.find(p => p.id === selectedProblem);

  return (
    <div className="app">
      <nav className="topnav">
        <span className="nav-logo">⬡ CodeArena</span>
        <div className="nav-center">
          <span className="room-label">Room: <code>{roomId}</code></span>
          {prob && (
            <span className="problem-nav-title">
              {prob.title}
              {prob.difficulty && (
                <span className="prob-nav-diff" style={{ color: DIFFICULTY_COLORS[prob.difficulty]?.color }}>
                  {" "}· {prob.difficulty}
                </span>
              )}
            </span>
          )}
          <div className="peer-list">
            {peers.map(p => <span key={p.name} className="peer-dot" style={{ background: p.color }} title={p.name} />)}
          </div>
        </div>
        <div className="nav-right">
          <span className={`timer ${timerDanger ? "timer-danger" : ""}`}>{formatTime(timeRemaining)}</span>
          <button className="btn btn-ghost" style={{fontSize:11,padding:"4px 10px"}} onClick={() => setShowProgress(true)}>
            📊 Progress{solvedCount > 0 ? ` · ${solvedCount} solved` : ""}
          </button>
          <span className={`ws-badge ${connected ? "ws-on" : "ws-off"}`}>
            {connected ? "● Live" : "○ Offline"}
          </span>
        </div>
      </nav>

      <div className="arena">
        {/* Left: problem statement + switcher */}
        <aside className="problem-panel">
          {/* Switcher toggle button */}
          <button className="switcher-toggle" onClick={() => setSwitcherOpen(o => !o)}>
            {switcherOpen ? "← Back to Problem" : "⇄ Switch Problem"}
          </button>

          {switcherOpen ? (
            /* ---- PROBLEM SWITCHER ---- */
            <div className="switcher-panel">
              {/* Search bar */}
              <input
                className="switcher-search"
                placeholder="Search problems..."
                value={searchQuery}
                onChange={e => handleSearch(e.target.value)}
                autoFocus
              />
              {/* Filters */}
              <div className="filter-row" style={{marginBottom:6}}>
                <span style={{fontSize:10,color:"var(--text3)"}}>
                  {totalProblems > 0 ? `${totalProblems.toLocaleString()} problems` : ""}
                </span>
                <div style={{display:"flex",gap:3}}>
                  {["","easy","medium","hard"].map(d => (
                    <button key={d}
                      className={`filter-btn ${switcherFilter===d?"filter-active":""}`}
                      onClick={() => {
                        setSwitcherFilter(d);
                        setProblemSkip(0);
                        loadProblems(d, searchQuery, 0, false);
                      }}>
                      {d || "All"}
                    </button>
                  ))}
                  <button className="filter-btn filter-daily" onClick={() => { loadDaily(); setSwitcherFilter("daily"); }}>⚡</button>
                </div>
              </div>
              {/* Problem list */}
              <div className="switcher-list">
                {problems.map(p => {
                  const dc = DIFFICULTY_COLORS[p.difficulty] || DIFFICULTY_COLORS.medium;
                  const isCurrent = p.id === (currentProblem?.id || selectedProblem);
                  const isLoading = switchingTo === p.id;
                  return (
                    <div key={p.id}
                      className={`prob-option ${isCurrent ? "prob-selected" : ""}`}
                      onClick={() => !isLoading && switchProblem(p.id)}
                      style={{opacity: switchingTo && !isLoading ? 0.5 : 1}}
                    >
                      <div className="prob-opt-left">
                        <span className="prob-opt-title">{isLoading ? "Loading..." : p.title}</span>
                        <div className="prob-opt-tags">
                          {(p.topics||[]).map(t => <span key={t} className="opt-tag">{t}</span>)}
                        </div>
                      </div>
                      <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:4}}>
                        <span className="prob-opt-diff" style={{color:dc.color,background:dc.bg,border:`1px solid ${dc.border}`}}>
                          {p.difficulty?.toUpperCase()}
                        </span>
                        {isCurrent && <span style={{fontSize:9,color:"var(--success)"}}>● active</span>}
                      </div>
                    </div>
                  );
                })}
                {/* Load more */}
                {problems.length < totalProblems && (
                  <button className="load-more-btn" onClick={loadMore} disabled={loadingProblems}>
                    {loadingProblems ? "Loading..." : `Load more (${(totalProblems - problems.length).toLocaleString()} remaining)`}
                  </button>
                )}
                {loadingProblems && problems.length === 0 && (
                  <div className="loading-hint">Fetching from LeetCode...</div>
                )}
              </div>
            </div>
          ) : prob ? (
            /* ---- PROBLEM STATEMENT ---- */
            <>
              <div className="problem-title">{prob.title}</div>
              <div className="prob-tags">
                {prob.difficulty && (
                  <span className="tag" style={{
                    background: DIFFICULTY_COLORS[prob.difficulty]?.bg,
                    color: DIFFICULTY_COLORS[prob.difficulty]?.color,
                    border: `1px solid ${DIFFICULTY_COLORS[prob.difficulty]?.border}`,
                  }}>{prob.difficulty.toUpperCase()}</span>
                )}
                {(prob.topics || []).map(t => <span key={t} className="tag tag-topic">{t}</span>)}
              </div>
              <div className="prob-desc" dangerouslySetInnerHTML={{
                __html: (prob.description || "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\*(.*?)\*/g, "<em>$1</em>")
              }} />
              {prob.examples && (
                <div className="example-box">
                  <div className="ex-label">Example</div>
                  <pre className="ex-code">{prob.examples}</pre>
                </div>
              )}
              {prob.constraints?.length > 0 && (
                <div className="constraints">
                  <div className="con-title">Constraints</div>
                  {prob.constraints.map(([k, v], i) => (
                    <div key={i} className="con-row"><span>{k}</span><code>{v}</code></div>
                  ))}
                </div>
              )}
              {prob.hints?.length > 0 && (
                <details className="hints-section">
                  <summary className="hints-toggle">💡 Hints ({prob.hints.length})</summary>
                  {prob.hints.map((h, i) => (
                    <div key={i} className="hint-item">{h}</div>
                  ))}
                </details>
              )}
              {prob.leetcode_url && (
                <a href={prob.leetcode_url} target="_blank" rel="noreferrer" className="lc-link">
                  View on LeetCode ↗
                </a>
              )}
            </>
          ) : (
            <div style={{color:"var(--text3)",fontSize:12,padding:"8px 0"}}>Loading problem...</div>
          )}
        </aside>

        {/* Center: editor + output */}
        <main className="center">
          <Editor
            code={code} language={language}
            onCodeChange={handleCodeChange}
            onRun={handleRun} onSubmit={handleSubmit} onHint={handleHint}
            peers={myPeers} languages={languages}
          />
          <div className="output-panel">
            <div className="output-tabs">
              {["tests", "console", "sandbox"].map(tab => (
                <button key={tab} className={`otab ${activeTab === tab ? "otab-active" : ""}`}
                  onClick={() => setActiveTab(tab)}>
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>
            <div className="output-body">
              {activeTab === "tests" && (
                testResults.length === 0
                  ? <p className="out-hint">Submit your code to run the test suite.</p>
                  : testResults.map((t, i) => (
                    <div key={i} className="test-row">
                      <span className={`test-dot ${t.pass ? "dot-pass" : "dot-fail"}`} />
                      <span className={t.pass ? "out-pass" : "out-fail"}>{t.name}</span>
                      <span className="out-time">{t.time}</span>
                      <span className={`test-label ${t.pass ? "out-pass" : "out-fail"}`}>{t.pass ? "PASS" : "FAIL"}</span>
                    </div>
                  ))
              )}
              {activeTab === "console" && (
                <pre className="console-output">{consoleOutput || "Run your code to see output."}</pre>
              )}
              {activeTab === "sandbox" && (
                <div className="sandbox-info">
                  <div className="si-row"><span className="si-key">Isolation</span><span className="si-val">subprocess + resource limits</span></div>
                  <div className="si-row"><span className="si-key">Timeout</span><span className="si-val">10 seconds</span></div>
                  <div className="si-row"><span className="si-key">Memory cap</span><span className="si-val">256 MB</span></div>
                  <div className="si-row"><span className="si-key">Network</span><span className="si-val">blocked</span></div>
                  <p className="si-note">Production: Docker --network=none + seccomp + cgroup v2</p>
                </div>
              )}
            </div>
          </div>
        </main>

        {/* Right: AI interviewer */}
        <aside className="right-panel">
          <AIChat messages={chatMessages} onSend={handleChat} complexity={complexity} originality={originality} />
        </aside>
      </div>
      {showProgress && (
        <Progress userName={userName} onClose={() => setShowProgress(false)} />
      )}
    </div>
  );
}
