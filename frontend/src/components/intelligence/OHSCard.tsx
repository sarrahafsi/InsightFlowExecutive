"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface Dimension {
  key: string;
  label: string;
  score: number;
  weight: number;
}

interface SentimentTrend {
  delta:      number;
  direction:  "improving" | "degrading" | "stable";
  first_half: number;
  last_half:  number;
}

interface OHSData {
  score:           number;
  label:           string;
  color:           string;
  trend:           number;
  sentiment_trend: SentimentTrend;
  window_days:     number;
  computed_at:     string;
  breakdown:       Dimension[];
}

function CircularGauge({ score, color }: { score: number; color: string }) {
  const size = 148;
  const sw = 10;
  const r = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;

  return (
    <svg width={size} height={size} style={{ display: "block" }}>
      {/* Background track */}
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke="rgba(62,92,118,0.1)" strokeWidth={sw} />
      {/* Score arc */}
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={`${filled} ${circ - filled}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      {/* Score number */}
      <text x={size / 2} y={size / 2 + 2}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={34} fontWeight={700} fill={color}
        fontFamily="DM Serif Display, serif">
        {score}
      </text>
      <text x={size / 2} y={size / 2 + 22}
        textAnchor="middle" fontSize={10} fill="#748cab">
        / 100
      </text>
    </svg>
  );
}

function DimensionBar({ dim }: { dim: Dimension }) {
  const barColor =
    dim.score >= 70 ? "#22c55e" :
    dim.score >= 40 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3, color: "#0d1321" }}>
        <span>{dim.label}</span>
        <span style={{ color: barColor, fontWeight: 600 }}>{Math.round(dim.score)}</span>
      </div>
      <div style={{ height: 5, borderRadius: 4, background: "rgba(62,92,118,0.1)", overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${dim.score}%`, borderRadius: 4,
          background: barColor,
          transition: "width 0.7s ease",
        }} />
      </div>
    </div>
  );
}

export default function OHSCard() {
  const [data, setData] = useState<OHSData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get("/api/health/ohs?window_days=7")
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const cardStyle: React.CSSProperties = {
    background: "#fff",
    border: "1px solid rgba(62,92,118,0.12)",
    borderRadius: 16,
    padding: "1.5rem",
    marginBottom: "2rem",
  };

  if (loading) return (
    <div style={{ ...cardStyle, height: 80, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 20, height: 20, border: "2px solid rgba(62,92,118,0.2)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  if (!data) return null;

  const trendColor = data.trend > 0 ? "#22c55e" : data.trend < 0 ? "#ef4444" : "#748cab";
  const trendSign  = data.trend > 0 ? "+" : "";
  const bgGradient = `linear-gradient(135deg, ${data.color}08 0%, transparent 60%)`;

  const st = data.sentiment_trend;
  const stIcon  = st?.direction === "improving" ? "↗" : st?.direction === "degrading" ? "↘" : "→";
  const stColor = st?.direction === "improving" ? "#22c55e" : st?.direction === "degrading" ? "#ef4444" : "#748cab";
  const stLabel = st?.direction === "improving" ? "Sentiment en amélioration"
                : st?.direction === "degrading"  ? "Sentiment en dégradation"
                : "Sentiment stable";

  return (
    <div style={{ ...cardStyle, background: `${bgGradient}, #fff`, borderColor: `${data.color}22` }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "#748cab", marginBottom: 2 }}>
            Score de Santé Organisationnelle
          </div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0d1321" }}>
            État global de l'organisation
          </h2>
          <p style={{ margin: "2px 0 0", fontSize: 11, color: "#748cab" }}>
            Analyse sur les 7 derniers jours · 5 dimensions
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            background: `${data.color}18`, color: data.color,
            fontSize: 11, fontWeight: 700,
            padding: "3px 10px", borderRadius: 20,
            border: `1px solid ${data.color}33`,
          }}>
            {data.label}
          </span>
          {data.trend !== 0 && (
            <span style={{ fontSize: 11, color: trendColor, fontWeight: 600 }}>
              {trendSign}{data.trend} pts vs sem. passée
            </span>
          )}
        </div>
      </div>

      {/* Sentiment trend banner */}
      {st && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 14px", borderRadius: 10, marginBottom: "1rem",
          background: `${stColor}10`, border: `1px solid ${stColor}25`,
        }}>
          <span style={{ fontSize: 18, color: stColor }}>{stIcon}</span>
          <span style={{ fontSize: 12, color: stColor, fontWeight: 600 }}>{stLabel}</span>
          <span style={{ fontSize: 11, color: "#748cab", marginLeft: "auto" }}>
            {Math.round(st.first_half * 100)}% → {Math.round(st.last_half * 100)}% positif
          </span>
        </div>
      )}

      {/* Body: gauge + breakdown */}
      <div style={{ display: "flex", gap: "2rem", alignItems: "center", flexWrap: "wrap" }}>
        {/* Left: circular gauge */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
          <CircularGauge score={data.score} color={data.color} />
          <p style={{ margin: "8px 0 0", fontSize: 11, color: "#748cab", textAlign: "center" }}>
            {data.score >= 70
              ? "Organisation en bonne santé"
              : data.score >= 40
              ? "Tensions détectées"
              : "Situation critique — action requise"}
          </p>
        </div>

        {/* Right: dimension breakdown */}
        <div style={{ flex: 1, minWidth: 220 }}>
          {data.breakdown.map(dim => (
            <DimensionBar key={dim.key} dim={dim} />
          ))}
        </div>
      </div>
    </div>
  );
}
