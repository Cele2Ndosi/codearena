/**
 * Editor.jsx — Collaborative code editor with remote cursors.
 *
 * Features:
 * - Textarea-based editor (swap for CodeMirror/Monaco in production)
 * - Sends code_edit messages on every keystroke (debounced 200ms)
 * - Receives code_sync from peers and updates without moving cursor
 * - Shows remote cursors as coloured markers
 * - Tab key inserts 2 spaces instead of jumping focus
 */

import { useState, useRef, useEffect, useCallback } from "react";

const DEBOUNCE_MS = 200;

export default function Editor({
  code,
  language,
  onCodeChange,   // (code, language) => void — sends WS message
  onRun,
  onSubmit,
  onHint,
  peers,          // [{ name, color, line, col }]
  languages,
}) {
  const [localCode, setLocalCode] = useState(code);
  const [localLang, setLocalLang] = useState(language || "python");
  const debounceRef = useRef(null);
  const taRef = useRef(null);

  // Sync incoming code from peers (don't override if user is actively typing)
  useEffect(() => {
    if (code !== localCode) {
      setLocalCode(code);
    }
  }, [code]); // eslint-disable-line

  const handleChange = (e) => {
    const newCode = e.target.value;
    setLocalCode(newCode);

    // Debounce the WS broadcast
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onCodeChange(newCode, localLang);
    }, DEBOUNCE_MS);
  };

  const handleTab = (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const ta = taRef.current;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newCode =
        localCode.substring(0, start) + "  " + localCode.substring(end);
      setLocalCode(newCode);
      // Restore cursor after state update
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
  };

  const handleLangChange = (e) => {
    setLocalLang(e.target.value);
    onCodeChange(localCode, e.target.value);
  };

  const lineCount = localCode.split("\n").length;

  return (
    <div className="editor-wrapper">
      {/* Toolbar */}
      <div className="editor-toolbar">
        <div className="toolbar-left">
          <select
            className="lang-select"
            value={localLang}
            onChange={handleLangChange}
            title="Language — only installed runtimes can Run/Submit"
          >
            {languages.map((l) => (
              <option
                key={l.id || l.value}
                value={l.id || l.value}
                disabled={l.available === false}
                style={l.available === false ? {color:"#525d70"} : {}}
              >
                {l.available === false ? "✗ " : ""}
                {l.label}
                {l.version ? ` (${l.version.split(" ").slice(-1)[0]})` : ""}
                {l.available === false ? " — not installed" : ""}
              </option>
            ))}
          </select>

          {/* Live peer indicators */}
          <div className="peer-cursors">
            {peers.map((p) => (
              <span
                key={p.name}
                className="peer-badge"
                style={{ background: p.color + "22", border: `1px solid ${p.color}`, color: p.color }}
              >
                ● {p.name}
              </span>
            ))}
          </div>
        </div>

        <div className="toolbar-right">
          <button className="btn btn-ghost" onClick={onHint}>✦ Hint</button>
          <button className="btn btn-ghost" onClick={onRun}>▶ Run</button>
          <button className="btn btn-submit" onClick={onSubmit}>✓ Submit</button>
        </div>
      </div>

      {/* Editor body */}
      <div className="editor-body">
        {/* Line numbers */}
        <div className="line-numbers" aria-hidden="true">
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} className="line-num">{i + 1}</div>
          ))}
        </div>

        {/* Code textarea */}
        <div className="code-area">
          <textarea
            ref={taRef}
            className="code-textarea"
            value={localCode}
            onChange={handleChange}
            onKeyDown={handleTab}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
        </div>
      </div>
    </div>
  );
}
