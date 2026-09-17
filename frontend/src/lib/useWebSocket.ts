"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getToken, getUser } from "./auth";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

// Close codes sent by the backend when the WS handshake is refused —
// never auto-reconnect on these, the account is unauthenticated or plan-locked.
const NO_RECONNECT_CODES = new Set([4401, 4403]);

export interface WSEvent {
  type: string;
  [key: string]: unknown;
}

export function useWebSocket(onEvent: (event: WSEvent) => void) {
  const wsRef            = useRef<WebSocket | null>(null);
  const reconnectRef     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef       = useRef(onEvent);
  const [connected, setConnected] = useState(false);
  const [locked, setLocked]       = useState(false);

  // Keep onEvent ref fresh without recreating connect
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const token = getToken();
    if (!token) return; // pas de session — inutile de tenter la connexion
    if (getUser()?.org_plan === "free") { setLocked(true); return; } // fonctionnalité Pro

    const socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token)}`);

    socket.onopen = () => {
      setConnected(true);
      setLocked(false);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      // Keep-alive ping every 25s
      const ping = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "ping" }));
        } else {
          clearInterval(ping);
        }
      }, 25_000);
      (socket as WebSocket & { _ping?: ReturnType<typeof setInterval> })._ping = ping;
    };

    socket.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WSEvent;
        onEventRef.current(event);
      } catch { /* ignore malformed messages */ }
    };

    socket.onclose = (event) => {
      setConnected(false);
      wsRef.current = null;
      if (NO_RECONNECT_CODES.has(event.code)) {
        setLocked(true);
        return; // plan-gated ou non authentifié — ne pas boucler
      }
      // Reconnect after 3s
      reconnectRef.current = setTimeout(connect, 3_000);
    };

    socket.onerror = () => socket.close();

    wsRef.current = socket;
  }, []); // stable — no deps needed

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, locked };
}
