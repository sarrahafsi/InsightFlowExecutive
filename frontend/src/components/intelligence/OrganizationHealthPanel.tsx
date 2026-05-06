"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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
  breakdown:       Dimension[];
}

function CircularGauge({ score, color }: { score: number; color: string }) {
  const size = 136;
  const sw = 9;
  const r = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;

  return (
    <svg width={size} height={size} style={{ display: "block", margin: "0 auto" }}>
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke="rgba(240,235,216,0.12)" strokeWidth={sw} />
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={`${filled} ${circ - filled}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      <text x={size / 2} y={size / 2 + 2}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={30} fontWeight={700} fill={color}
        fontFamily="DM Serif Display, serif">
        {score}
      </text>
      <text x={size / 2} y={size / 2 + 20}
        textAnchor="middle" fontSize={10} fill="rgba(240,235,216,0.5)">
        / 100
      </text>
    </svg>
  );
}

function DimBar({ dim }: { dim: Dimension }) {
  const color =
    dim.score >= 70 ? "#4ade80" :
    dim.score >= 40 ? "#fbbf24" : "#f87171";

  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3, color: "rgba(240,235,216,0.75)" }}>
        <span>{dim.label}</span>
        <span style={{ color, fontWeight: 600 }}>{Math.round(dim.score)}</span>
      </div>
      <div style={{ height: 4, borderRadius: 4, background: "rgba(240,235,216,0.1)" }}>
        <div style={{
          height: "100%", width: `${dim.score}%`, borderRadius: 4,
          background: color, transition: "width 0.7s ease",
        }} />
      </div>
    </div>
  );
}

export default function OrganizationHealthPanel({ sinceDays = 7 }: { sinceDays?: number }) {
  const { t, locale } = useI18n();
  const [ohs, setOhs]         = useState<OHSData | null>(null);
  const [ohsLoading, setOhsL] = useState(true);
  const [brief, setBrief]     = useState<any | null>(null);
  const [generating, setGen]  = useState(false);
  const [genError, setGenErr] = useState<string | null>(null);

  const generate = async () => {
    setGen(true);
    setGenErr(null);
    try {
      const r = await API.get(`/api/brief/weekly?since_days=${sinceDays}`);
      setBrief(r.data);
    } catch (e: any) {
      setGenErr(e.message);
    } finally {
      setGen(false);
    }
  };

  useEffect(() => {
    API.get("/api/health/ohs?window_days=7")
      .then(r => setOhs(r.data))
      .catch(() => {})
      .finally(() => setOhsL(false));

    generate();
  }, []);

  const trendColor  = !ohs ? "#f0ebd8" : ohs.trend > 0 ? "#4ade80" : ohs.trend < 0 ? "#f87171" : "rgba(240,235,216,0.5)";
  const trendSign   = ohs && ohs.trend > 0 ? "+" : "";

  return (
    <div style={{
      background: "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)",
      borderRadius: 20, padding: "1.75rem 2rem",
      marginBottom: "1.5rem", color: "#f0ebd8",
    }}>
      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(240,235,216,0.5)", marginBottom: 3 }}>
            Tableau de bord exécutif
          </div>
          <h2 style={{ margin: 0, fontSize: 20, fontFamily: "DM Serif Display, serif" }}>
            État de l'organisation
          </h2>
        </div>
        <button
          onClick={generate}
          disabled={generating}
          style={{
            padding: "9px 20px", borderRadius: 12,
            border: "1px solid rgba(240,235,216,0.25)",
            background: generating ? "rgba(240,235,216,0.08)" : "rgba(240,235,216,0.14)",
            color: "#f0ebd8", fontSize: 13, fontWeight: 600,
            cursor: generating ? "not-allowed" : "pointer",
          }}
        >
          {generating ? "Génération..." : brief ? "↻ Régénérer" : "✦ Générer le résumé"}
        </button>
      </div>

      {/* ── Body: 2 columns ── */}
      <div style={{ display: "flex", gap: "2rem", alignItems: "flex-start", flexWrap: "wrap" }}>

        {/* ── Left: OHS ── */}
        <div style={{
          width: 200, flexShrink: 0,
          borderRight: "1px solid rgba(240,235,216,0.12)",
          paddingRight: "2rem",
        }}>
          {ohsLoading ? (
            <div style={{ height: 136, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ width: 18, height: 18, border: "2px solid rgba(240,235,216,0.2)", borderTop: "2px solid #f0ebd8", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          ) : ohs ? (
            <>
              <CircularGauge score={ohs.score} color={ohs.color} />

              {/* Label + trend */}
              <div style={{ textAlign: "center", margin: "10px 0 10px" }}>
                <span style={{
                  background: `${ohs.color}28`, color: ohs.color,
                  fontSize: 11, fontWeight: 700,
                  padding: "3px 10px", borderRadius: 20,
                  border: `1px solid ${ohs.color}44`,
                }}>{ohs.label}</span>
                {ohs.trend !== 0 && (
                  <div style={{ fontSize: 10, color: trendColor, marginTop: 5 }}>
                    {trendSign}{ohs.trend} pts vs sem. passée
                  </div>
                )}
              </div>

              {/* Sentiment trend */}
              {ohs.sentiment_trend && (() => {
                const st = ohs.sentiment_trend;
                const icon  = st.direction === "improving" ? "↗" : st.direction === "degrading" ? "↘" : "→";
                const color = st.direction === "improving" ? "#4ade80" : st.direction === "degrading" ? "#f87171" : "rgba(240,235,216,0.5)";
                const label = st.direction === "improving" ? "Sentiment ↗" : st.direction === "degrading" ? "Sentiment ↘" : "Sentiment →";
                return (
                  <div style={{
                    textAlign: "center", marginBottom: 12,
                    padding: "4px 10px", borderRadius: 8,
                    background: `${color}18`, border: `1px solid ${color}33`,
                  }}>
                    <span style={{ fontSize: 11, color, fontWeight: 600 }}>{icon} {label}</span>
                    <div style={{ fontSize: 9, color: "rgba(240,235,216,0.5)", marginTop: 2 }}>
                      {Math.round(st.first_half * 100)}% → {Math.round(st.last_half * 100)}%
                    </div>
                  </div>
                );
              })()}

              {/* Dimension bars */}
              <div>
                {ohs.breakdown.map(d => <DimBar key={d.key} dim={d} />)}
              </div>
            </>
          ) : (
            <p style={{ fontSize: 12, color: "rgba(240,235,216,0.4)", textAlign: "center" }}>Score indisponible</p>
          )}
        </div>

        {/* ── Right: Brief ── */}
        <div style={{ flex: 1, minWidth: 260 }}>
          {!brief && !genError && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 140, opacity: 0.5 }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>✦</div>
              <p style={{ fontSize: 13, textAlign: "center", color: "rgba(240,235,216,0.7)" }}>
                Cliquez sur "Générer le résumé" pour obtenir<br />une analyse narrative de la période.
              </p>
            </div>
          )}

          {genError && (
            <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.2)", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 10, fontSize: 12 }}>
              {genError}
            </div>
          )}

          {brief && (
            <>
              {/* Quick stats */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: "1rem" }}>
                {[
                  { label: t.brief_stat_messages, value: brief.stats_summary?.total_items },
                  { label: t.brief_stat_risk,     value: `${brief.stats_summary?.risk_index}/100` },
                  { label: t.brief_stat_climate,  value: brief.stats_summary?.climate },
                  { label: t.brief_stat_positive, value: `${brief.stats_summary?.sentiment?.positive ?? 0}%` },
                ].map(s => (
                  <div key={s.label} style={{
                    background: "rgba(240,235,216,0.08)",
                    borderRadius: 10, padding: "7px 12px",
                    border: "1px solid rgba(240,235,216,0.12)",
                  }}>
                    <div style={{ fontSize: 9, color: "rgba(240,235,216,0.5)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{s.label}</div>
                    <div style={{ fontSize: 15, fontWeight: 700, marginTop: 2 }}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Narrative text */}
              {brief.brief ? (
                <div style={{ background: "rgba(240,235,216,0.07)", borderRadius: 12, padding: "1rem 1.25rem", border: "1px solid rgba(240,235,216,0.1)" }}>
                  <p style={{ fontSize: 13, lineHeight: 1.8, color: "rgba(240,235,216,0.88)", whiteSpace: "pre-wrap", margin: 0 }}>
                    {brief.brief}
                  </p>
                </div>
              ) : (
                <div style={{ padding: "1rem", background: "rgba(239,68,68,0.15)", borderRadius: 12, fontSize: 13 }}>
                  {t.brief_no_ollama} <code>ollama run llama3.2</code>
                </div>
              )}

              <div style={{ fontSize: 10, color: "rgba(240,235,216,0.35)", marginTop: 8, textAlign: "right" }}>
                {t.brief_generated_at(new Date(brief.generated_at).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB"), brief.period)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
