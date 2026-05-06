"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface Correlation {
  source_a:  string;
  source_b:  string;
  metric_a:  string;
  metric_b:  string;
  lag_days:  number;
  r:         number;
  p_value:   number;
  n_points:  number;
  strength:  "forte" | "modérée" | "faible";
  direction: "positive" | "negative";
  insight:   string;
}

interface CorrelationData {
  correlations: Correlation[];
  computed_at:  string;
  window_days:  number;
  sources:      string[];
  note?:        string;
}

const SOURCE_COLORS: Record<string, string> = {
  gmail: "#EA4335",
  jira:  "#0052CC",
  slack: "#4A154B",
};

const SOURCE_ICONS: Record<string, string> = {
  gmail: "✉️",
  jira:  "📋",
  slack: "💬",
};

const METRIC_LABELS: Record<string, string> = {
  sentiment: "Sentiment",
  volume:    "Volume",
  burnout:   "Surcharge",
};

const STRENGTH_COLORS: Record<string, string> = {
  forte:    "#ef4444",
  modérée:  "#f59e0b",
  faible:   "#748cab",
};

function CorrelationBar({ r }: { r: number }) {
  const pct   = Math.abs(r) * 100;
  const color = Math.abs(r) >= 0.7 ? "#ef4444" : Math.abs(r) >= 0.5 ? "#f59e0b" : "#748cab";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 5, borderRadius: 4, background: "rgba(62,92,118,0.1)" }}>
        <div style={{
          height: "100%", width: `${pct}%`, borderRadius: 4,
          background: color, transition: "width 0.7s ease",
        }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 42, textAlign: "right" }}>
        {r > 0 ? "+" : ""}{r.toFixed(2)}
      </span>
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const color = SOURCE_COLORS[source] ?? "#748cab";
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
      background: `${color}15`, color, border: `1px solid ${color}33`,
    }}>
      {SOURCE_ICONS[source] ?? "◈"} {source}
    </span>
  );
}

function LagBadge({ lag }: { lag: number }) {
  if (lag === 0) return (
    <span style={{ fontSize: 10, color: "#748cab", whiteSpace: "nowrap" }}>même jour</span>
  );
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
      background: "rgba(62,92,118,0.08)", color: "#3e5c76", whiteSpace: "nowrap",
    }}>
      ⏱ +{lag}j
    </span>
  );
}

export default function CorrelationPanel({ windowDays = 30 }: { windowDays?: number }) {
  const [data, setData]       = useState<CorrelationData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get(`/api/intelligence/correlations?window_days=${windowDays}`)
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [windowDays]);

  const card: React.CSSProperties = {
    background: "#fff",
    border: "1px solid rgba(62,92,118,0.12)",
    borderRadius: 16,
    padding: "1.5rem",
    marginBottom: "1.5rem",
  };

  if (loading) return (
    <div style={{ ...card, height: 80, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 20, height: 20, border: "2px solid rgba(62,92,118,0.2)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  if (!data) return null;

  return (
    <div style={card}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "#748cab", marginBottom: 2 }}>
            Corrélation cross-canal
          </div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0d1321" }}>
            Propagation des signaux entre sources
          </h2>
          <p style={{ margin: "2px 0 0", fontSize: 11, color: "#748cab" }}>
            Analyse sur {data.window_days} jours · Corrélation de Pearson avec décalage temporel
          </p>
        </div>
        <span style={{
          fontSize: 11, color: "#748cab",
          background: "rgba(62,92,118,0.06)",
          padding: "4px 12px", borderRadius: 20,
          border: "1px solid rgba(62,92,118,0.12)",
        }}>
          {data.sources?.join(" · ")}
        </span>
      </div>

      {/* Pas de données */}
      {data.note && (
        <div style={{ textAlign: "center", padding: "2rem", color: "#748cab", fontSize: 13 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>◎</div>
          {data.note}
        </div>
      )}

      {/* Aucune corrélation significative */}
      {!data.note && data.correlations.length === 0 && (
        <div style={{ textAlign: "center", padding: "2rem", color: "#22c55e", fontSize: 13 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>✓</div>
          Aucune corrélation significative détectée — les sources évoluent indépendamment.
        </div>
      )}

      {/* Liste des corrélations */}
      {data.correlations.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {data.correlations.map((c, i) => (
            <div key={i} style={{
              padding: "12px 14px",
              borderRadius: 12,
              background: i === 0 ? "rgba(239,68,68,0.04)" : "rgba(62,92,118,0.03)",
              border: `1px solid ${i === 0 ? "rgba(239,68,68,0.15)" : "rgba(62,92,118,0.08)"}`,
            }}>
              {/* Ligne 1 : sources + métriques + lag + score */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                <SourceBadge source={c.source_a} />
                <span style={{ fontSize: 11, color: "#748cab" }}>
                  {METRIC_LABELS[c.metric_a] ?? c.metric_a}
                </span>
                <span style={{ fontSize: 12, color: "#748cab" }}>→</span>
                <LagBadge lag={c.lag_days} />
                <span style={{ fontSize: 12, color: "#748cab" }}>→</span>
                <SourceBadge source={c.source_b} />
                <span style={{ fontSize: 11, color: "#748cab" }}>
                  {METRIC_LABELS[c.metric_b] ?? c.metric_b}
                </span>
                <span style={{
                  marginLeft: "auto",
                  fontSize: 10, fontWeight: 700,
                  color: STRENGTH_COLORS[c.strength],
                  textTransform: "uppercase", letterSpacing: "0.08em",
                }}>
                  {c.strength}
                </span>
              </div>

              {/* Ligne 2 : barre + insight */}
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <CorrelationBar r={c.r} />
                <p style={{ margin: 0, fontSize: 12, color: "#0d1321", flex: 1, lineHeight: 1.5 }}>
                  {c.insight}
                </p>
              </div>

              {/* Ligne 3 : métriques statistiques */}
              <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                <span style={{ fontSize: 10, color: "#748cab" }}>
                  p = <strong style={{ color: c.p_value < 0.01 ? "#22c55e" : "#f59e0b" }}>
                    {c.p_value < 0.001 ? "< 0.001" : c.p_value.toFixed(3)}
                  </strong>
                </span>
                <span style={{ fontSize: 10, color: "#748cab" }}>n = {c.n_points} jours</span>
                <span style={{ fontSize: 10, color: "#22c55e", fontWeight: 600 }}>
                  ✓ significatif (p &lt; 0.05)
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Légende */}
      <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid rgba(62,92,118,0.08)", display: "flex", gap: 16, flexWrap: "wrap" }}>
        {[
          { color: "#ef4444", label: "Forte  |r| ≥ 0.70" },
          { color: "#f59e0b", label: "Modérée  |r| ≥ 0.50" },
          { color: "#748cab", label: "Faible  |r| ≥ 0.45" },
        ].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: l.color }} />
            <span style={{ fontSize: 10, color: "#748cab" }}>{l.label}</span>
          </div>
        ))}
        <span style={{ fontSize: 10, color: "#748cab", marginLeft: "auto" }}>
          ⏱ = décalage temporel détecté
        </span>
      </div>
    </div>
  );
}
