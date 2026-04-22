"use client";
import { useEffect, useRef, useState } from "react";
import API from "@/lib/api";

interface Alert {
  id: string;
  title: string;
  author: string;
  business_label: string;
  timestamp: string;
}

const LABEL_COLORS: Record<string, string> = {
  Blocked: "#ef4444", Urgent: "#f97316", Risk: "#f59e0b",
  Conflict: "#8b5cf6", Overload: "#ec4899",
};

export default function AlertToast() {
  const [toasts, setToasts] = useState<Alert[]>([]);
  const seen = useRef<Set<string>>(new Set());
  const RISK_LABELS = new Set(["Blocked", "Urgent", "Risk", "Conflict", "Overload"]);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await API.get("/api/search/priority?since_days=1&limit=20");
        const items: any[] = r.data.items ?? [];
        const newAlerts = items.filter(
          i => RISK_LABELS.has(i.business_label) && !seen.current.has(i.id)
        );
        if (newAlerts.length > 0) {
          newAlerts.forEach(a => seen.current.add(a.id));
          setToasts(prev => [...newAlerts.slice(0, 3), ...prev].slice(0, 5));
        }
      } catch {}
    };

    // Premier check immédiat, puis toutes les 2 minutes
    check();
    const interval = setInterval(check, 120_000);
    return () => clearInterval(interval);
  }, []);

  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));

  if (toasts.length === 0) return null;

  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 500, display: "flex", flexDirection: "column", gap: 10, maxWidth: 340 }}>
      {toasts.map(toast => {
        const color = LABEL_COLORS[toast.business_label] ?? "#ef4444";
        return (
          <div key={toast.id} style={{
            background: "#fff", borderRadius: 14, padding: "12px 16px",
            boxShadow: "0 8px 32px rgba(13,19,33,0.18)",
            border: `1px solid ${color}40`,
            borderLeft: `4px solid ${color}`,
            animation: "slideIn 0.3s ease",
          }}>
            <style>{`@keyframes slideIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}`}</style>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  ⚠ {toast.business_label}
                </span>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", marginTop: 2, lineHeight: 1.4 }}>
                  {toast.title}
                </div>
                <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>
                  {toast.author} · {new Date(toast.timestamp).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                </div>
              </div>
              <button onClick={() => dismiss(toast.id)} style={{ background: "none", border: "none", color: "#748cab", cursor: "pointer", fontSize: 14, padding: "0 2px", flexShrink: 0 }}>✕</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
