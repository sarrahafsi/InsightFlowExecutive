"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface Person {
  author:           string;
  total_msgs:       number;
  avg_burnout:      number;
  burnout_pct:      number;
  after_hours_msgs: number;
  weekend_msgs:     number;
  level:            "high" | "medium" | "low";
}

interface OverloadData {
  people:     Person[];
  since_days: number;
}

const LEVEL_META = {
  high:   { color: "#ef4444", bg: "#fef2f2", label: "Élevé",   icon: "🔴" },
  medium: { color: "#f59e0b", bg: "#fffbeb", label: "Modéré",  icon: "🟡" },
  low:    { color: "#22c55e", bg: "#f0fdf4", label: "Faible",  icon: "🟢" },
};

function initials(name: string) {
  return name.split(/[\s@._-]/).filter(Boolean).slice(0, 2)
    .map(p => p[0].toUpperCase()).join("");
}

export default function TeamOverloadCard({ sinceDays = 7 }: { sinceDays?: number }) {
  const [data, setData]       = useState<OverloadData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get(`/api/analytics/team/overload?since_days=${sinceDays}&limit=8`)
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sinceDays]);

  const card: React.CSSProperties = {
    background: "#fff",
    border: "1px solid rgba(62,92,118,0.12)",
    borderRadius: 16,
    padding: "1.5rem",
  };

  if (loading) return (
    <div style={{ ...card, height: 80, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 20, height: 20, border: "2px solid rgba(62,92,118,0.2)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  if (!data || data.people.length === 0) return (
    <div style={{ ...card, textAlign: "center", padding: "2rem", color: "#22c55e" }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>🧘</div>
      <div style={{ fontWeight: 600, fontSize: 14 }}>Aucune surcharge détectée</div>
      <div style={{ fontSize: 12, color: "#748cab", marginTop: 4 }}>L'équipe opère normalement sur {sinceDays} jours</div>
    </div>
  );

  return (
    <div style={card}>
      {/* Header */}
      <div style={{ marginBottom: "1.25rem" }}>
        <div style={{ fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "#748cab", marginBottom: 2 }}>
          Bien-être individuel
        </div>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0d1321" }}>
          Personnes les plus surchargées
        </h2>
        <p style={{ margin: "2px 0 0", fontSize: 11, color: "#748cab" }}>
          Classées par score de surcharge moyen · {sinceDays} derniers jours
        </p>
      </div>

      {/* Liste */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {data.people.map((p, i) => {
          const meta = LEVEL_META[p.level];
          return (
            <div key={p.author} style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "10px 12px", borderRadius: 12,
              background: i === 0 ? meta.bg : "rgba(62,92,118,0.03)",
              border: `1px solid ${i === 0 ? meta.color + "30" : "rgba(62,92,118,0.08)"}`,
            }}>
              {/* Rang */}
              <span style={{ fontSize: 11, color: "#748cab", minWidth: 18, textAlign: "center", fontWeight: 600 }}>
                #{i + 1}
              </span>

              {/* Avatar */}
              <div style={{
                width: 34, height: 34, borderRadius: "50%", flexShrink: 0,
                background: `${meta.color}20`, color: meta.color,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 700,
              }}>
                {initials(p.author)}
              </div>

              {/* Nom + signaux */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {p.author}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 2, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 10, color: "#748cab" }}>{p.total_msgs} msgs</span>
                  {p.after_hours_msgs > 0 && (
                    <span style={{ fontSize: 10, color: "#f59e0b" }}>🌙 {p.after_hours_msgs} hors-horaires</span>
                  )}
                  {p.weekend_msgs > 0 && (
                    <span style={{ fontSize: 10, color: "#8b5cf6" }}>📅 {p.weekend_msgs} week-end</span>
                  )}
                </div>
              </div>

              {/* Score burnout */}
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: meta.color }}>
                  {p.burnout_pct}%
                </div>
                <div style={{ fontSize: 9, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  {meta.label}
                </div>
              </div>

              {/* Barre */}
              <div style={{ width: 60, flexShrink: 0 }}>
                <div style={{ height: 5, borderRadius: 4, background: "rgba(62,92,118,0.1)" }}>
                  <div style={{
                    height: "100%", borderRadius: 4,
                    width: `${Math.min(p.burnout_pct, 100)}%`,
                    background: meta.color,
                    transition: "width 0.7s ease",
                  }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Légende */}
      <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid rgba(62,92,118,0.08)", display: "flex", gap: 16, flexWrap: "wrap" }}>
        {Object.entries(LEVEL_META).map(([k, v]) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: v.color }} />
            <span style={{ fontSize: 10, color: "#748cab" }}>{v.label} ≥ {k === "high" ? "50" : k === "medium" ? "25" : "0"}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
