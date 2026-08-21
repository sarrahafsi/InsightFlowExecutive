"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import MessageDetailModal from "./MessageDetailModal";
import { useI18n } from "@/lib/i18n";
import { useWS } from "@/lib/WebSocketContext";

const LABEL_COLORS: Record<string, string> = {
  Blocked: "#ef4444", Urgent: "#f97316", Risk: "#f59e0b",
  Conflict: "#8b5cf6", Overload: "#ec4899", Concern: "#eab308",
  Progress: "#22c55e", "Neutral Update": "#94a3b8",
};
const SCORE_COLOR = (s: number) => s >= 20 ? "#ef4444" : s >= 10 ? "#f59e0b" : "#22c55e";

export default function PriorityInbox({ sinceDays = 7, source }: { sinceDays?: number; source?: string }) {
  const { t } = useI18n();
  const { refreshSignal } = useWS();
  const [items, setItems]     = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail]   = useState<any | null>(null);

  useEffect(() => {
    setLoading(true);
    const sourceParam = source ? `&source=${source}` : "";
    API.get(`/api/search/priority?since_days=${sinceDays}&limit=8${sourceParam}`)
      .then(r => setItems(r.data.items ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sinceDays, source, refreshSignal]);

  return (
    <div style={{ background: "#fff", borderRadius: 20, padding: "1.5rem 1.75rem", boxShadow: "0 2px 20px rgba(13,19,33,0.07)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>{t.priority_badge}</div>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>{t.priority_title}</h2>
        </div>
        <span style={{ fontSize: 11, color: "#748cab" }}>{t.priority_sub}</span>
      </div>

      {loading ? (
        <p style={{ color: "#748cab", fontSize: 13, textAlign: "center", padding: "1rem" }}>{t.priority_loading}</p>
      ) : items.length === 0 ? (
        <p style={{ color: "#748cab", fontSize: 13, textAlign: "center", padding: "1rem" }}>{t.priority_empty}</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((item, idx) => {
            const bl = item.business_label || "Neutral Update";
            const blColor = LABEL_COLORS[bl] ?? "#94a3b8";
            return (
              <div key={item.id}
                onClick={() => setDetail(item)}
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderRadius: 12, cursor: "pointer", border: "1px solid rgba(62,92,118,0.1)", background: idx === 0 ? "#fefce8" : "#f8f9fa", transition: "all 0.15s" }}
                onMouseEnter={e => (e.currentTarget.style.background = "#f0f4f8")}
                onMouseLeave={e => (e.currentTarget.style.background = idx === 0 ? "#fefce8" : "#f8f9fa")}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: "#748cab", width: 20, textAlign: "center", flexShrink: 0 }}>#{idx + 1}</div>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: blColor, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {item.title}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>
                    {item.author} · {new Date(item.timestamp).toLocaleDateString("fr-FR")}
                    {item.is_after_hours && <span style={{ marginLeft: 6 }}>🌙</span>}
                    {item.is_weekend && <span style={{ marginLeft: 4 }}>📅</span>}
                  </div>
                </div>
                <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 20, background: `${blColor}18`, color: blColor, flexShrink: 0 }}>{bl}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: SCORE_COLOR(item.priority_score), flexShrink: 0, width: 28, textAlign: "right" }}>{item.priority_score}</span>
              </div>
            );
          })}
        </div>
      )}

      {detail && (
        <MessageDetailModal
          item={{ ...detail, snippet: detail.snippet }}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}
