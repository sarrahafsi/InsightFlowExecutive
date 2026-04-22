"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface BlockedItem {
  id: string;
  title: string;
  author: string;
  source: string;
  business_label: string;
  timestamp: string;
  snippet?: string;
}

const LABEL_COLORS: Record<string, string> = {
  Blocked:  "#ef4444",
  Urgent:   "#f97316",
  Risk:     "#f59e0b",
  Conflict: "#8b5cf6",
  Overload: "#ec4899",
};

const SOURCE_ICONS: Record<string, string> = {
  gmail: "✉️", slack: "💬", jira: "📋", notion: "📝", outlook: "📧",
};

export default function BlockedItems({ sinceDays = 30 }: { sinceDays?: number }) {
  const [items, setItems]   = useState<BlockedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter]   = useState<string>("all");

  useEffect(() => {
    setLoading(true);
    API.get(`/api/search/priority?since_days=${sinceDays}&limit=100`)
      .then(r => {
        const blocked = (r.data.items ?? []).filter((i: any) =>
          ["Blocked", "Urgent", "Risk", "Conflict", "Overload"].includes(i.business_label)
        );
        setItems(blocked);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sinceDays]);

  const labels = ["all", ...Array.from(new Set(items.map(i => i.business_label)))];
  const filtered = filter === "all" ? items : items.filter(i => i.business_label === filter);

  return (
    <div style={{ background: "#fff", borderRadius: 20, padding: "1.5rem 1.75rem", boxShadow: "0 2px 20px rgba(13,19,33,0.07)", border: "1px solid rgba(239,68,68,0.12)", marginBottom: "1.5rem" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#ef4444", fontWeight: 600, marginBottom: 4 }}>
            Points bloquants
          </div>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>
            Signaux critiques détectés
            {items.length > 0 && (
              <span style={{ marginLeft: 10, fontSize: 12, background: "#fef2f2", color: "#ef4444", border: "1px solid #fecaca", borderRadius: 20, padding: "2px 10px", fontFamily: "DM Sans, sans-serif" }}>
                {items.length} message{items.length > 1 ? "s" : ""}
              </span>
            )}
          </h2>
        </div>

        {/* Filtres par label */}
        {labels.length > 1 && (
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
            {labels.map(l => (
              <button key={l} onClick={() => setFilter(l)} style={{
                padding: "4px 12px", borderRadius: 20, border: `1px solid ${l === "all" ? "rgba(62,92,118,0.25)" : (LABEL_COLORS[l] ?? "#748cab") + "50"}`,
                background: filter === l ? (l === "all" ? "#3e5c76" : LABEL_COLORS[l] ?? "#748cab") : "transparent",
                color: filter === l ? "#fff" : (l === "all" ? "#748cab" : LABEL_COLORS[l] ?? "#748cab"),
                fontSize: 11, fontWeight: 600, cursor: "pointer",
              }}>
                {l === "all" ? "Tous" : l}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <p style={{ color: "#748cab", fontSize: 13, textAlign: "center", padding: "1.5rem" }}>Analyse en cours...</p>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem", color: "#22c55e" }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>✓</div>
          <p style={{ fontSize: 13, fontWeight: 600 }}>Aucun point bloquant détecté</p>
          <p style={{ fontSize: 12, color: "#748cab", marginTop: 4 }}>Les communications semblent fluides</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {filtered.map((item, i) => {
            const color = LABEL_COLORS[item.business_label] ?? "#748cab";
            return (
              <div key={item.id} style={{
                display: "flex", alignItems: "flex-start", gap: 12,
                padding: "11px 0",
                borderBottom: i < filtered.length - 1 ? "1px solid rgba(62,92,118,0.07)" : "none",
              }}>
                <div style={{ width: 3, alignSelf: "stretch", borderRadius: 4, background: color, flexShrink: 0, minHeight: 40 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                      {item.business_label}
                    </span>
                    <span style={{ fontSize: 11, color: "#748cab" }}>
                      {SOURCE_ICONS[item.source] ?? "·"} {item.source}
                    </span>
                    <span style={{ fontSize: 11, color: "#94a3b8", marginLeft: "auto" }}>
                      {new Date(item.timestamp).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", marginBottom: 2 }}>
                    {item.title}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>
                    {item.author && <span>{item.author}</span>}
                    {item.snippet && <span style={{ marginLeft: 8, color: "#94a3b8" }}>· {item.snippet.slice(0, 80)}…</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
