"use client";
import { useWS, WSNotification } from "@/lib/WebSocketContext";

const SOURCE_ICONS: Record<string, string> = {
  gmail:  "✉️",
  slack:  "💬",
  jira:   "🎯",
  teams:  "👥",
  default:"🔔",
};

const LEVEL_STYLES: Record<string, { bg: string; border: string; accent: string }> = {
  critical: { bg: "#fff5f5", border: "#fca5a5", accent: "#ef4444" },
  warning:  { bg: "#fffbeb", border: "#fcd34d", accent: "#f59e0b" },
  info:     { bg: "#f0f9ff", border: "#7dd3fc", accent: "#0ea5e9" },
};

function NotifCard({ n, onClose }: { n: WSNotification; onClose: () => void }) {
  const style = LEVEL_STYLES[n.level] ?? LEVEL_STYLES.info;
  const icon  = SOURCE_ICONS[n.source ?? ""] ?? SOURCE_ICONS.default;

  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 10,
      padding: "12px 14px",
      background: style.bg,
      border: `1px solid ${style.border}`,
      borderLeft: `4px solid ${style.accent}`,
      borderRadius: 10,
      boxShadow: "0 4px 16px rgba(0,0,0,0.10)",
      maxWidth: 340,
      animation: "slideIn 0.2s ease",
    }}>
      <span style={{ fontSize: 18, flexShrink: 0, marginTop: 1 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600,
          color: style.accent,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          marginBottom: 2,
        }}>
          {n.source ?? "notification"}
        </div>
        <div style={{ fontSize: 13, color: "#1e293b", lineHeight: 1.4, wordBreak: "break-word" }}>
          {n.message}
        </div>
      </div>
      <button
        onClick={onClose}
        style={{
          background: "none", border: "none", cursor: "pointer",
          color: "#94a3b8", fontSize: 16, lineHeight: 1,
          padding: "0 2px", flexShrink: 0,
        }}
        aria-label="Fermer"
      >
        ×
      </button>
    </div>
  );
}

export default function RealtimeNotifications() {
  const { notifications, clearNotification } = useWS();

  if (notifications.length === 0) return null;

  return (
    <>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
      <div style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        pointerEvents: "none",
      }}>
        {notifications.map(n => (
          <div key={n.id} style={{ pointerEvents: "auto" }}>
            <NotifCard n={n} onClose={() => clearNotification(n.id)} />
          </div>
        ))}
      </div>
    </>
  );
}
