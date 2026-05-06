"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface Dimension {
  key: string;
  label: string;
  score: number;
  weight: number;
}

interface ProjectOHSData {
  project_id:    string;
  project_name:  string;
  score:         number;
  label:         string;
  color:         string;
  linked_msgs:   number;
  signals_tasks: number;
  computed_at:   string;
  breakdown:     Dimension[];
}

function MiniGauge({ score, color }: { score: number; color: string }) {
  const size = 96;
  const sw   = 8;
  const r    = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;

  return (
    <svg width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke="rgba(62,92,118,0.1)" strokeWidth={sw} />
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={`${filled} ${circ - filled}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      <text x={size / 2} y={size / 2 + 2}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={24} fontWeight={700} fill={color}
        fontFamily="DM Serif Display, serif">
        {score}
      </text>
      <text x={size / 2} y={size / 2 + 17}
        textAnchor="middle" fontSize={9} fill="#748cab">
        / 100
      </text>
    </svg>
  );
}

function DimBar({ dim }: { dim: Dimension }) {
  const barColor =
    dim.score >= 70 ? "#22c55e" :
    dim.score >= 40 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3, color: "#0d1321" }}>
        <span style={{ color: "#748cab" }}>{dim.label}</span>
        <span style={{ color: barColor, fontWeight: 600 }}>{Math.round(dim.score)}</span>
      </div>
      <div style={{ height: 4, borderRadius: 4, background: "rgba(62,92,118,0.1)", overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${dim.score}%`, borderRadius: 4,
          background: barColor,
          transition: "width 0.7s ease",
        }} />
      </div>
    </div>
  );
}

export default function ProjectOHSCard({ projectId }: { projectId: string }) {
  const [data, setData]       = useState<ProjectOHSData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);

  useEffect(() => {
    API.get(`/api/projects/${projectId}/ohs`)
      .then(r => setData(r.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [projectId]);

  const card: React.CSSProperties = {
    background: "#fff",
    border: "1px solid rgba(62,92,118,0.09)",
    borderRadius: 14,
    padding: "1.25rem 1.5rem",
    boxShadow: "0 1px 6px rgba(13,19,33,0.04)",
  };

  if (loading) return (
    <div style={{ ...card, display: "flex", alignItems: "center", justifyContent: "center", height: 80 }}>
      <div style={{ width: 18, height: 18, border: "2px solid rgba(62,92,118,0.2)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
    </div>
  );

  if (error || !data) return null;

  return (
    <div style={{ ...card, borderColor: `${data.color}22`, background: `linear-gradient(135deg, ${data.color}06 0%, transparent 60%), #fff` }}>
      {/* Header */}
      <div style={{ marginBottom: "1rem" }}>
        <div style={{ fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "#748cab", marginBottom: 2 }}>
          Score de santé du projet
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#0d1321" }}>
            Santé organisationnelle
          </h3>
          <span style={{
            background: `${data.color}18`, color: data.color,
            fontSize: 11, fontWeight: 700,
            padding: "3px 10px", borderRadius: 20,
            border: `1px solid ${data.color}33`,
          }}>
            {data.label}
          </span>
        </div>
      </div>

      {/* Body: gauge + bars */}
      <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
        {/* Gauge */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <MiniGauge score={data.score} color={data.color} />
          <div style={{ fontSize: 10, color: "#748cab", textAlign: "center", lineHeight: 1.4 }}>
            {data.linked_msgs} msg · {data.signals_tasks} tâches
          </div>
        </div>

        {/* Dimension bars */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {data.breakdown.map(d => <DimBar key={d.key} dim={d} />)}
        </div>
      </div>

      {/* Footer */}
      <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid rgba(62,92,118,0.07)", fontSize: 10, color: "#a0b4c4" }}>
        Calculé à partir des signaux croisés · {new Date(data.computed_at).toLocaleString("fr-FR")}
      </div>
    </div>
  );
}
