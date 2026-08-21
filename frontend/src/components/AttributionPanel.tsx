"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

const SOURCE_ICON: Record<string, string> = {
  gmail: "✉️", jira: "📋", slack: "💬", outlook: "📨", teams: "🟣", clickup: "⬆️",
};

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span style={{ fontSize: 10, background: `${color}14`, color, borderRadius: 6, padding: "2px 8px", fontWeight: 600 }}>
      {label}
    </span>
  );
}

export default function AttributionPanel({ sinceDays = 7 }: { sinceDays?: number }) {
  const [data, setData]     = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get(`/api/analytics/attribution?since_days=${sinceDays}`)
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sinceDays]);

  if (loading) return (
    <div style={{ padding: "1.5rem", textAlign: "center", color: "#748cab", fontSize: 13 }}>
      Chargement...
    </div>
  );

  if (!data.length) return (
    <div style={{ padding: "1.5rem", textAlign: "center" }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
      <div style={{ fontSize: 13, color: "#748cab" }}>Aucune alerte sur cette période</div>
    </div>
  );

  const maxAlerts = Math.max(...data.map(d => d.total_alerts), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {data.map((person, i) => {
        const hue = (i * 67) % 360;
        const alertColor = person.blocked > 0 ? "#ef4444" : person.urgent > 0 ? "#f97316" : "#f59e0b";
        return (
          <div key={person.author} style={{ padding: "12px 14px", borderRadius: 12, background: "#f8fafc", border: "1px solid rgba(62,92,118,0.1)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <div style={{
                width: 32, height: 32, borderRadius: "50%",
                background: `hsl(${hue}, 55%, 90%)`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 700, color: `hsl(${hue}, 55%, 35%)`,
                flexShrink: 0,
              }}>
                {(person.author || "?")[0].toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {person.author || "Inconnu"}
                </div>
                <div style={{ fontSize: 10, color: "#748cab" }}>
                  {person.sources.map((s: string) => SOURCE_ICON[s] ?? "◈").join(" ")}
                  {" · "}{person.total_alerts} alerte{person.total_alerts > 1 ? "s" : ""}
                </div>
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: alertColor }}>
                {person.total_alerts}
              </div>
            </div>
            <div style={{ height: 5, background: "rgba(62,92,118,0.1)", borderRadius: 3, overflow: "hidden", marginBottom: 8 }}>
              <div style={{
                height: "100%", borderRadius: 3,
                width: `${(person.total_alerts / maxAlerts) * 100}%`,
                background: alertColor,
                transition: "width 0.6s ease",
              }} />
            </div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {person.blocked  > 0 && <Chip label={`🚫 ${person.blocked} Bloqué`}    color="#ef4444" />}
              {person.urgent   > 0 && <Chip label={`🚨 ${person.urgent} Urgent`}     color="#f97316" />}
              {person.risk     > 0 && <Chip label={`⚠️ ${person.risk} Risque`}       color="#f59e0b" />}
              {person.overload > 0 && <Chip label={`💥 ${person.overload} Surcharge`} color="#ec4899" />}
              {person.conflict > 0 && <Chip label={`⚔️ ${person.conflict} Conflit`}  color="#8b5cf6" />}
            </div>
          </div>
        );
      })}
    </div>
  );
}
