/**
 * useWebSocket — real-time collaboration hook
 *
 * Connects to the FastAPI WebSocket server.
 * Handles: auto-reconnect, message dispatch, ping/pong keepalive.
 *
 * Usage:
 *   const { send, connected, participants, ping } = useWebSocket(roomId, userId, name, color, onMessage)
 */

import { useEffect, useRef, useState, useCallback } from 'react'

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
const RECONNECT_DELAY_MS = 2000
const PING_INTERVAL_MS = 15000

export function useWebSocket(roomId, userId, name, color, onMessage) {
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [participants, setParticipants] = useState([])
  const [ping, setPing] = useState(null)
  const pingRef = useRef(null)
  const pingTimestamp = useRef(null)
  const reconnectTimer = useRef(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!roomId || !userId) return

    const url = `${WS_BASE}/${roomId}?user_id=${encodeURIComponent(userId)}&name=${encodeURIComponent(name)}&color=${encodeURIComponent(color)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setConnected(true)
      console.log(`[WS] Connected to room ${roomId}`)

      // Start ping/pong keepalive
      pingRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          pingTimestamp.current = performance.now()
          ws.send(JSON.stringify({ type: 'PING' }))
        }
      }, PING_INTERVAL_MS)
    }

    ws.onmessage = (event) => {
      if (!mountedRef.current) return
      try {
        const msg = JSON.parse(event.data)

        // Handle pong latency measurement
        if (msg.type === 'PONG' && pingTimestamp.current) {
          setPing(Math.round(performance.now() - pingTimestamp.current))
        }

        // Update participant list on join/leave
        if (msg.type === 'USER_JOINED' || msg.type === 'USER_LEFT' || msg.type === 'INIT') {
          if (msg.participants) setParticipants(msg.participants)
        }

        onMessage?.(msg)
      } catch (e) {
        console.error('[WS] Parse error:', e)
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      clearInterval(pingRef.current)
      console.log('[WS] Disconnected — reconnecting...')
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
    }

    ws.onerror = (err) => {
      console.error('[WS] Error:', err)
      ws.close()
    }
  }, [roomId, userId, name, color, onMessage])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearInterval(pingRef.current)
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }, [])

  return { send, connected, participants, ping }
}
