"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import KPICard from "@/components/KPICard";
import DonutChart from "@/components/charts/DonutChart";
import LineChart from "@/components/charts/LineChart";
import BarChart from "@/components/charts/BarChart";

const SOURCE_COLORS: Record<string, string> = {
  gmail: "#EA4335", slack: "#4A154B", jira: "#0052CC",
  notion: "#333", outlook: "#0078D4",
};

const PERIOD_OPTIONS = [7, 30, 90];

export default function DashboardOverview() {
  const [sinceDays, setSinceDays] = useState(30);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    API.get(`/api/analytics/overview?since_days=${sinceDays}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  }, [sinceDays]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: 36, height: 36, border: "3px solid rgba(62,92,118,0.2)", borderTop: "3px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        <p style={{ color: "#748cab", fontSize: 13 }}>Chargement des analytics...</p>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ background: "#fef2f2", border: "1px solid #ef4444", borderRadius: 12, padding: "1.5rem", color: "#ef4444" }}>
      <strong>Erreur :</strong> {error}<br />
      <small style={{ color: "#748cab" }}>Vérifiez que le backend tourne sur http://localhost:8000</small>
    </div>
  );
  if (!data) return null;

  const sourceSlices = Object.entries(data.by_source as Record<string, number>).map(([k, v]) => ({
    label: k.charAt(0).toUpperCase() + k.slice(1),
    value: v as number,
    color: SOURCE_COLORS[k] ?? "#748cab",
  }));

  const sentimentSlices = [
    { label: "Positif",  value: data.sentiment.positive, color: "#22c55e" },
    { label: "Neutre",   value: data.sentiment.neutral,  color: "#94a3b8" },
    { label: "Négatif",  value: data.sentiment.negative, color: "#ef4444" },
  ];

  const typeSlices = Object.entries(data.by_type as Record<string, number>).map(([k, v], i) => ({
    label: k.charAt(0).toUpperCase() + k.slice(1),
    value: v as number,
    color: ["#3e5c76", "#748cab", "#1d2d44"][i] ?? "#ccc",
  }));

  const riskLevel = data.risk_index > 60 ? "high" : data.risk_index > 30 ? "medium" : "low";
  const riskLabel = riskLevel === "high" ? "Critique" : riskLevel === "medium" ? "Modéré" : "Faible";

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "2rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", marginBottom: 6 }}>
            Vue d&apos;ensemble
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 28, color: "#0d1321", letterSpacing: "-0.02em" }}>
            Executive Dashboard
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginTop: 4 }}>
            Mis à jour {new Date(data.computed_at).toLocaleString("fr-FR")}
          </p>
        </div>

        {/* Period filter */}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {PERIOD_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setSinceDays(d)}
              style={{
                padding: "6px 14px", borderRadius: 20, cursor: "pointer",
                border: `1px solid ${sinceDays === d ? "#3e5c76" : "rgba(62,92,118,0.2)"}`,
                background: sinceDays === d ? "#3e5c76" : "transparent",
                color: sinceDays === d ? "#fff" : "#748cab",
                fontSize: 12, fontWeight: sinceDays === d ? 600 : 400,
              }}
            >
              {d}j
            </button>
          ))}
        </div>
      </div>

      {/* KPI Row 1 — Vue globale */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
        <KPICard title="Total données" value={data.total_items} icon="◈"
          subtitle={`sur ${data.total_sources} sources disponibles`} />
        <KPICard title="Sources actives" value={`${data.connected_sources}/${data.total_sources}`} icon="⊕"
          accent="#22c55e" subtitle="Sources connectées" />
        <KPICard title="Alertes critiques" value={data.critical_alerts} icon="⚠"
          risk={data.critical_alerts > 5 ? "high" : data.critical_alerts > 2 ? "medium" : "low"}
          subtitle="Mots clés d'escalade détectés" />
        <KPICard title="Indice de risque" value={`${data.risk_index}/100`} icon="🎯"
          risk={riskLevel} subtitle={`Niveau : ${riskLabel}`} />
        <KPICard title="Vélocité (sem.)" value={data.velocity.this_week} icon="⚡"
          delta={Number(data.velocity.delta_pct)}
          subtitle={`Sem. passée : ${data.velocity.last_week} items`} />
        <KPICard title="Sentiment positif" value={`${data.sentiment.positive}%`} icon="◉"
          accent="#22c55e"
          subtitle={`${data.sentiment.negative}% négatif · ${data.sentiment.neutral}% neutre`} />
      </div>

      {/* Charts row 1 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
        {/* Activity timeline */}
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500 }}>Activité — 14 derniers jours</div>
          </div>
          <LineChart data={data.activity_timeline} height={130} />
        </div>

        {/* By source */}
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500 }}>Répartition par source</div>
          </div>
          <DonutChart data={sourceSlices} size={150} label="items" />
        </div>
      </div>

      {/* Charts row 2 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
        {/* Sentiment */}
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500 }}>Analyse sentimentale</div>
          </div>
          <DonutChart data={sentimentSlices} size={150} label="emails" />
        </div>

        {/* By type */}
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500 }}>Répartition par type</div>
          </div>
          <DonutChart data={typeSlices} size={150} label="items" />
        </div>
      </div>

      {/* Activity bar by source */}
      <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500 }}>Volume par source</div>
        </div>
        <BarChart
          data={Object.entries(data.by_source as Record<string, number>).map(([k, v]) => ({
            label: k.charAt(0).toUpperCase() + k.slice(1),
            value: v as number,
            color: SOURCE_COLORS[k] ?? "#748cab",
          }))}
          height={120}
        />
      </div>
    </div>
  );
}
