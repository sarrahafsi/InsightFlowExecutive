"use client";
import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  ReactNode,
} from "react";
import { useWebSocket, WSEvent } from "./useWebSocket";

export interface WSNotification {
  id: string;
  type: string;
  level: "info" | "warning" | "critical";
  source?: string;
  message: string;
  timestamp: string;
  item_id?: string;
}

interface WSContextValue {
  connected: boolean;
  lastEvent: WSEvent | null;
  notifications: WSNotification[];
  clearNotification: (id: string) => void;
  /** Incrémenté après nlp_complete — utilise comme dépendance useEffect pour rafraîchir la Priority Inbox */
  refreshSignal: number;
  /** Incrémenté après sync_complete — utilise comme dépendance useEffect pour rafraîchir le dashboard */
  syncSignal: number;
}

const WSContext = createContext<WSContextValue>({
  connected: false,
  lastEvent: null,
  notifications: [],
  clearNotification: () => {},
  refreshSignal: 0,
  syncSignal: 0,
});

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [lastEvent, setLastEvent]         = useState<WSEvent | null>(null);
  const [notifications, setNotifications] = useState<WSNotification[]>([]);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [syncSignal, setSyncSignal]       = useState(0);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const clearNotification = useCallback((id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
    const t = timersRef.current.get(id);
    if (t) { clearTimeout(t); timersRef.current.delete(id); }
  }, []);

  const handleEvent = useCallback((event: WSEvent) => {
    setLastEvent(event);

    if (event.type === "nlp_complete") {
      setRefreshSignal(s => s + 1);
    }
    if (event.type === "sync_complete") {
      setSyncSignal(s => s + 1);
    }

    if (event.type === "notification" || event.type === "new_messages") {
      const count = (event.count as number | undefined) ?? 1;
      const source = (event.source as string | undefined) ?? "";
      const defaultMsg = count === 1
        ? `Nouveau message de ${source}`
        : `${count} nouveaux messages (${source})`;

      const notif: WSNotification = {
        id:        `${Date.now()}-${Math.random()}`,
        type:      event.type,
        level:     (event.level as WSNotification["level"]) || "info",
        source:    source,
        message:   (event.message as string) || defaultMsg,
        timestamp: (event.timestamp as string) || new Date().toISOString(),
        item_id:   event.item_id as string | undefined,
      };

      setNotifications(prev => [notif, ...prev].slice(0, 6));

      // Auto-dismiss after 8s
      const timer = setTimeout(() => clearNotification(notif.id), 8_000);
      timersRef.current.set(notif.id, timer);
    }
  }, [clearNotification]);

  const { connected } = useWebSocket(handleEvent);

  return (
    <WSContext.Provider value={{ connected, lastEvent, notifications, clearNotification, refreshSignal, syncSignal }}>
      {children}
    </WSContext.Provider>
  );
}

export const useWS = () => useContext(WSContext);
