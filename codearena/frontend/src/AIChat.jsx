/**
 * AIChat.jsx — AI Interviewer chat panel.
 *
 * Displays the conversation with Grok (via the backend).
 * Sends messages through the parent's `send` WebSocket function.
 */

import { useState, useRef, useEffect } from "react";

export default function AIChat({ messages, onSend, complexity, originality }) {
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    onSend(text);
    setInput("");
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const origColor =
    originality?.score >= 90
      ? "#2ed573"
      : originality?.score >= 70
      ? "#ff9f43"
      : "#ff4757";

  return (
    <div className="ai-panel">
      {/* Header */}
      <div className="ai-header">
        <div className="ai-avatar">🤖<div className="ai-pulse" /></div>
        <div>
          <div className="ai-name">ArenaAI</div>
          <div className="ai-sub">Powered by Groq · Technical Interviewer</div>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg msg-${m.role}`}>
            <div className={`bubble ${m.role === "ai" ? "bubble-ai" : "bubble-user"}`}>
              {m.text}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Reply to the interviewer..."
          rows={2}
        />
        <button className="send-btn" onClick={handleSend}>→</button>
      </div>

      {/* Complexity */}
      {complexity && (
        <div className="info-section">
          <div className="section-label">Complexity Analysis</div>
          <div className="complexity-grid">
            <div className="comp-box">
              <div className="comp-label">Time</div>
              <div className="comp-val">{complexity.time}</div>
            </div>
            <div className="comp-box">
              <div className="comp-label">Space</div>
              <div className="comp-val">{complexity.space}</div>
            </div>
          </div>
          {complexity.explanation && (
            <div className="comp-explanation">{complexity.explanation}</div>
          )}
        </div>
      )}

      {/* Originality */}
      {originality && (
        <div className="info-section">
          <div className="section-label">Originality Score</div>
          <div className="orig-row">
            <span className="orig-score" style={{ color: origColor }}>
              {originality.score}%
            </span>
            <span className="orig-verdict">{originality.verdict}</span>
          </div>
          <div className="orig-bar-bg">
            <div
              className="orig-bar-fill"
              style={{ width: `${originality.score}%`, background: origColor }}
            />
          </div>
          {originality.flags?.length > 0 && (
            <ul className="orig-flags">
              {originality.flags.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
