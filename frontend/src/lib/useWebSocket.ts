"use client";
import { useCallback, useEffect, useRef, useState } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

export interface WSEvent {
  type: string;
  [key: string]: unknown;
}

export function useWebSocket(onEvent: (event: WSEvent) => void) {
  const wsRef            = useRef<WebSocket | null>(null);
  const reconnectRef     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef       = useRef(onEvent);
  const [connected, setConnected] = useState(false);

  // Keep onEvent ref fresh without recreating connect
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      setConnected(true);
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

    socket.onclose = () => {
      setConnected(false);
      wsRef.current = null;
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

  return { connected };
}
