/**
 * useWebSocket.js — Custom React hook for the CodeArena WebSocket connection.
 *
 * Handles:
 * - Connection lifecycle (connect, disconnect, reconnect)
 * - Sending typed messages
 * - Dispatching incoming messages to the right state updaters
 */

import { useEffect, useRef, useCallback, useState } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

export function useWebSocket({ roomId, userName, onMessage }) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [latencyMs, setLatencyMs] = useState(null);
  const pingInterval = useRef(null);
  const pingTime = useRef(null);

  const send = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    if (!roomId || !userName) return;

    const ws = new WebSocket(`${WS_URL}/${roomId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // First message must always be a join
      ws.send(JSON.stringify({ type: "join", name: userName }));

      // Measure round-trip latency every 5s
      pingInterval.current = setInterval(() => {
        pingTime.current = Date.now();
        ws.send(JSON.stringify({ type: "ping" }));
      }, 5000);
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      // Handle pong here, pass everything else up
      if (msg.type === "pong") {
        setLatencyMs(Date.now() - pingTime.current);
        return;
      }

      onMessage(msg);
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    ws.onclose = () => {
      setConnected(false);
      clearInterval(pingInterval.current);
    };

    return () => {
      clearInterval(pingInterval.current);
      ws.close();
    };
  }, [roomId, userName]); // eslint-disable-line

  return { send, connected, latencyMs };
}
