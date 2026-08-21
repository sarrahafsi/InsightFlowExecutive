"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

const LABEL_META: Record<string, { color: string; icon: string }> = {
  Blocked:  { color: "#ef4444", icon: "🚫" },
  Urgent:   { color: "#f97316", icon: "🚨" },
  Risk:     { color: "#f59e0b", icon: "⚠️" },
  Conflict: { color: "#8b5cf6", icon: "⚔️" },
  Overload: { color: "#ec4899", icon: "💥" },
};

const SOURCE_ICON: Record<string, string> = {
  gmail: "✉️", jira: "📋", slack: "💬", outlook: "📨", teams: "🟣", clickup: "⬆️",
};

function timeAgo(iso: string): string {
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000);
  if (h < 1) return "< 1h";
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}j`;
}

export default function PriorityMessages({ sinceDays = 7 }: { sinceDays?: number }) {
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    API.get(`/api/analytics/priority-messages?since_days=${sinceDays}&limit=3`)
      .then(r => setMessages(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sinceDays]);

  if (loading) return (
    <div style={{ padding: "1.5rem", textAlign: "center", color: "#748cab", fontSize: 13 }}>
      Chargement...
    </div>
  );

  if (!messages.length) return (
    <div style={{ padding: "1.5rem", textAlign: "center" }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
      <div style={{ fontSize: 13, color: "#748cab" }}>Aucun message critique à lire</div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {messages.map((msg, i) => {
        const meta = LABEL_META[msg.business_label] ?? { color: "#748cab", icon: "◈" };
        return (
          <div key={msg.id ?? i} style={{
            display: "flex", alignItems: "flex-start", gap: 12,
            padding: "12px 14px", borderRadius: 12,
            background: `${meta.color}08`,
            border: `1px solid ${meta.color}25`,
            borderLeft: `4px solid ${meta.color}`,
          }}>
            <div style={{ fontSize: 22, flexShrink: 0, marginTop: 1 }}>{meta.icon}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", marginBottom: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {msg.title || "(Sans titre)"}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <span style={{ fontSize: 10, background: `${meta.color}18`, color: meta.color, borderRadius: 6, padding: "2px 8px", fontWeight: 700 }}>
                  {msg.business_label}
                </span>
                {msg.author && (
                  <span style={{ fontSize: 11, color: "#748cab" }}>
                    {SOURCE_ICON[msg.source] ?? "◈"} {msg.author}
                  </span>
                )}
                <span style={{ fontSize: 10, color: "#94a3b8" }}>{timeAgo(msg.timestamp)}</span>
              </div>
              {msg.business_reason && (
                <div style={{ fontSize: 11, color: "#748cab", marginTop: 4, fontStyle: "italic" }}>
                  {msg.business_reason.slice(0, 90)}
                </div>
              )}
            </div>
            {msg.url && (
              <a href={msg.url} target="_blank" rel="noopener noreferrer" style={{
                fontSize: 11, color: meta.color, textDecoration: "none",
                background: `${meta.color}12`, padding: "4px 10px", borderRadius: 8,
                whiteSpace: "nowrap", flexShrink: 0,
              }}>
                Ouvrir →
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}
