"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import ReactMarkdown from "react-markdown";

interface Dimension {
  key: string; label: string; score: number; weight: number;
}

interface SentimentTrend {
  delta: number; direction: "improving" | "degrading" | "stable";
  first_half: number; last_half: number;
}

interface OHSData {
  score: number; label: string; color: string; trend: number;
  sentiment_trend: SentimentTrend; breakdown: Dimension[];
}

/* ── Circular gauge (light theme) ─────────────────────────────── */
function CircularGauge({ score, color }: { score: number; color: string }) {
  const size = 120;
  const sw   = 8;
  const r    = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;

  return (
    <svg width={size} height={size} style={{ display: "block" }}>
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke="rgba(0,0,0,0.07)" strokeWidth={sw} />
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={`${filled} ${circ - filled}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      <text x={size / 2} y={size / 2 + 2}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={26} fontWeight={700} fill={color}
        fontFamily="DM Serif Display, serif">
        {score}
      </text>
      <text x={size / 2} y={size / 2 + 18}
        textAnchor="middle" fontSize={10} fill="#94a3b8">
        / 100
      </text>
    </svg>
  );
}

/* ── Dimension progress bar ────────────────────────────────────── */
function DimBar({ dim }: { dim: Dimension }) {
  const color =
    dim.score >= 70 ? "#22c55e" :
    dim.score >= 40 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, marginBottom: 4 }}>
        <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{dim.label}</span>
        <span style={{ color, fontWeight: 700 }}>{Math.round(dim.score)}</span>
      </div>
      <div style={{ height: 5, borderRadius: 5, background: "rgba(0,0,0,0.07)" }}>
        <div style={{
          height: "100%", width: `${dim.score}%`, borderRadius: 5,
          background: color, transition: "width 0.7s ease",
        }} />
      </div>
    </div>
  );
}

/* ── Main panel ────────────────────────────────────────────────── */
export default function OrganizationHealthPanel({ sinceDays = 7 }: { sinceDays?: number }) {
  const { t, locale } = useI18n();
  const [ohs, setOhs]       = useState<OHSData | null>(null);
  const [ohsLoading, setOhsL] = useState(true);
  const [brief, setBrief]   = useState<any | null>(null);
  const [generating, setGen] = useState(false);
  const [genError, setGenErr] = useState<string | null>(null);

  const generate = async () => {
    setGen(true); setGenErr(null);
    try {
      const r = await API.get(`/api/brief/weekly?since_days=${sinceDays}`);
      setBrief(r.data);
    } catch (e: any) {
      setGenErr(e.message);
    } finally { setGen(false); }
  };

  useEffect(() => {
    API.get("/api/health/ohs?window_days=7")
      .then(r => setOhs(r.data)).catch(() => {})
      .finally(() => setOhsL(false));
    generate();
  }, []);

  const trendColor = !ohs ? "#94a3b8" : ohs.trend > 0 ? "#22c55e" : ohs.trend < 0 ? "#ef4444" : "#94a3b8";
  const trendSign  = ohs && ohs.trend > 0 ? "+" : "";

  return (
    <div style={{
      background: "var(--bg-card)",
      borderRadius: 16,
      border: "1px solid var(--border)",
      boxShadow: "0 2px 12px var(--shadow-card)",
      marginBottom: "1.5rem",
      overflow: "hidden",
    }}>
      {/* Top accent */}
      <div style={{ height: 3, background: "linear-gradient(90deg, #3b82f6, #8b5cf6, #3b82f6)", backgroundSize: "200% 100%" }} />

      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "1.25rem 1.75rem 1rem",
        borderBottom: "1px solid var(--border)",
        flexWrap: "wrap", gap: 10,
      }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 3 }}>
            Tableau de bord exécutif
          </div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
            État de l'organisation
          </h2>
        </div>
        <button
          onClick={generate}
          disabled={generating}
          style={{
            padding: "8px 18px", borderRadius: 10,
            border: "1px solid var(--border)",
            background: generating ? "var(--bg-input)" : "#1d2d44",
            color: generating ? "var(--text-secondary)" : "#f0ebd8",
            fontSize: 12.5, fontWeight: 600,
            cursor: generating ? "not-allowed" : "pointer",
            transition: "all 0.15s",
          }}
        >
          {generating ? "Génération..." : brief ? "↻ Régénérer" : "Générer le résumé"}
        </button>
      </div>

      {/* Body */}
      <div style={{ display: "flex", gap: 0, alignItems: "stretch", flexWrap: "wrap" }}>

        {/* ── Left : OHS score ── */}
        <div style={{
          width: 220, flexShrink: 0,
          padding: "1.25rem 1.5rem",
          borderRight: "1px solid var(--border)",
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: 10,
        }}>
          {ohsLoading ? (
            <div style={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ width: 18, height: 18, border: "2px solid var(--border)", borderTop: `2px solid #3b82f6`, borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          ) : ohs ? (
            <>
              <CircularGauge score={ohs.score} color={ohs.color} />

              {/* Label */}
              <span style={{
                fontSize: 11, fontWeight: 700,
                color: ohs.color,
                background: `${ohs.color}12`,
                border: `1px solid ${ohs.color}33`,
                padding: "3px 12px", borderRadius: 20,
              }}>
                {ohs.label}
              </span>

              {/* Trend */}
              {ohs.trend !== 0 && (
                <div style={{ fontSize: 11, color: trendColor, fontWeight: 500, textAlign: "center" }}>
                  {trendSign}{ohs.trend} pts vs semaine précédente
                </div>
              )}

              {/* Sentiment trend */}
              {ohs.sentiment_trend && (() => {
                const st = ohs.sentiment_trend;
                const arrow = st.direction === "improving" ? "↗" : st.direction === "degrading" ? "↘" : "→";
                const c     = st.direction === "improving" ? "#22c55e" : st.direction === "degrading" ? "#ef4444" : "#94a3b8";
                return (
                  <div style={{
                    width: "100%", textAlign: "center",
                    padding: "6px 10px", borderRadius: 8,
                    background: `${c}0d`, border: `1px solid ${c}22`,
                  }}>
                    <div style={{ fontSize: 11.5, color: c, fontWeight: 600 }}>{arrow} Sentiment</div>
                    <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>
                      {Math.round(st.first_half * 100)}% → {Math.round(st.last_half * 100)}%
                    </div>
                  </div>
                );
              })()}

              {/* Dimensions */}
              <div style={{ width: "100%" }}>
                {ohs.breakdown.map(d => <DimBar key={d.key} dim={d} />)}
              </div>
            </>
          ) : (
            <p style={{ fontSize: 12, color: "var(--text-secondary)", textAlign: "center" }}>Score indisponible</p>
          )}
        </div>

        {/* ── Right : Brief ── */}
        <div style={{ flex: 1, minWidth: 260, padding: "1.25rem 1.75rem" }}>
          {!brief && !genError && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 160, gap: 10 }}>
              <div style={{
                width: 44, height: 44, borderRadius: 12,
                background: "rgba(59,130,246,0.08)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 20,
              }}>
                ✦
              </div>
              <p style={{ fontSize: 13, textAlign: "center", color: "var(--text-secondary)", lineHeight: 1.6, maxWidth: 280, margin: 0 }}>
                Cliquez sur "Générer le résumé" pour obtenir une analyse narrative de la période.
              </p>
            </div>
          )}

          {genError && (
            <div style={{ padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, fontSize: 12, color: "#ef4444" }}>
              {genError}
            </div>
          )}

          {brief && (
            <>
              {/* Quick stats */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: "1.1rem" }}>
                {[
                  { label: t.brief_stat_messages, value: brief.stats_summary?.total_items },
                  { label: t.brief_stat_risk,     value: `${brief.stats_summary?.risk_index}/100` },
                  { label: t.brief_stat_climate,  value: brief.stats_summary?.climate },
                  { label: t.brief_stat_positive, value: `${brief.stats_summary?.sentiment?.positive ?? 0}%` },
                ].map(s => (
                  <div key={s.label} style={{
                    background: "var(--bg-input)", borderRadius: 10,
                    padding: "8px 14px", border: "1px solid var(--border)",
                    minWidth: 80,
                  }}>
                    <div style={{ fontSize: 10, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>
                      {s.label}
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Narrative */}
              {brief.brief ? (
                <div style={{
                  background: "var(--bg-input)", borderRadius: 12,
                  padding: "1rem 1.25rem", border: "1px solid var(--border)",
                }}>
                  <ReactMarkdown
                    components={{
                      p: ({ children }) => (
                        <p style={{ fontSize: 13, lineHeight: 1.85, color: "var(--text-primary)", margin: "0 0 0.6rem 0" }}>
                          {children}
                        </p>
                      ),
                      strong: ({ children }) => (
                        <strong style={{ fontWeight: 700, color: "var(--text-primary)" }}>
                          {children}
                        </strong>
                      ),
                      em: ({ children }) => (
                        <em style={{ fontStyle: "italic", color: "var(--text-secondary)" }}>
                          {children}
                        </em>
                      ),
                    }}
                  >
                    {brief.brief}
                  </ReactMarkdown>
                </div>
              ) : (
                <div style={{ padding: "1rem", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 12, fontSize: 13, color: "#dc2626" }}>
                  {t.brief_no_ollama} <code style={{ background: "#fee2e2", padding: "1px 5px", borderRadius: 4 }}>ollama run llama3.2</code>
                </div>
              )}

              <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 8, textAlign: "right" }}>
                {t.brief_generated_at(new Date(brief.generated_at).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB"), brief.period)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
