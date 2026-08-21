"use client";
import { useState } from "react";
import API from "@/lib/api";

/* ── Type & priority metadata ───────────────────────────────────── */
const TYPE_META: Record<string, { label: string; color: string; bg: string }> = {
  agent:    { label: "Agent IA",    color: "#3b82f6", bg: "rgba(59,130,246,0.1)"  },
  workflow: { label: "Workflow",    color: "#8b5cf6", bg: "rgba(139,92,246,0.1)"  },
  alerte:   { label: "Alerte",      color: "#f59e0b", bg: "rgba(245,158,11,0.1)"  },
  rapport:  { label: "Rapport Auto",color: "#22c55e", bg: "rgba(34,197,94,0.1)"   },
};

const PRIORITY_META: Record<string, { color: string; bg: string; label: string }> = {
  critique:  { color: "#ef4444", bg: "rgba(239,68,68,0.1)",    label: "Critique"  },
  urgent:    { color: "#f97316", bg: "rgba(249,115,22,0.1)",   label: "Urgent"    },
  important: { color: "#3b82f6", bg: "rgba(59,130,246,0.08)",  label: "Important" },
};

/* ── Small inline SVG icons ─────────────────────────────────────── */
function IconTrigger() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}
function IconCheck() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
function IconBot() {
  return (
    <svg width={22} height={22} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2" />
      <circle cx="12" cy="5" r="2" />
      <line x1="12" y1="7" x2="12" y2="11" />
      <line x1="8" y1="15" x2="8" y2="15" strokeWidth={3} />
      <line x1="16" y1="15" x2="16" y2="15" strokeWidth={3} />
    </svg>
  );
}

/* ── Agent card ─────────────────────────────────────────────────── */
function AgentCard({ rec, index }: { rec: any; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const p      = (rec.priority || "important").toLowerCase();
  const tp     = (rec.type || "agent").toLowerCase();
  const pMeta  = PRIORITY_META[p]  ?? PRIORITY_META.important;
  const tMeta  = TYPE_META[tp]     ?? TYPE_META.agent;

  return (
    <div
      onClick={() => setExpanded(e => !e)}
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${tMeta.color}`,
        borderRadius: "0 12px 12px 0",
        padding: "14px 16px",
        cursor: "pointer",
        transition: "box-shadow 0.15s, border-color 0.15s",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = `0 4px 18px ${tMeta.color}18`;
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        {/* Type badge */}
        <span style={{
          fontSize: 10, fontWeight: 700,
          color: tMeta.color, background: tMeta.bg,
          border: `1px solid ${tMeta.color}22`,
          borderRadius: 6, padding: "2px 8px",
          letterSpacing: "0.03em", flexShrink: 0,
        }}>
          {tMeta.label}
        </span>

        {/* Agent name */}
        <span style={{
          flex: 1,
          fontSize: 13.5,
          fontWeight: 700,
          color: "var(--text-primary)",
          letterSpacing: "-0.01em",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {rec.agent_name}
        </span>

        {/* Priority badge */}
        <span style={{
          fontSize: 10, fontWeight: 700,
          color: pMeta.color, background: pMeta.bg,
          borderRadius: 20, padding: "2px 9px", flexShrink: 0,
        }}>
          {pMeta.label}
        </span>

        {/* Expand chevron */}
        <svg width={13} height={13} viewBox="0 0 24 24" fill="none"
          stroke="var(--text-secondary)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"
          style={{ flexShrink: 0, transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>

      {/* Trigger (always visible) */}
      {rec.trigger && (
        <div style={{ display: "flex", gap: 6, alignItems: "flex-start", marginBottom: expanded ? 10 : 0 }}>
          <span style={{ color: tMeta.color, marginTop: 1, flexShrink: 0 }}>
            <IconTrigger />
          </span>
          <span style={{
            fontSize: 11.5,
            color: "var(--text-secondary)",
            lineHeight: 1.5,
            fontStyle: "italic",
          }}>
            {rec.trigger}
          </span>
        </div>
      )}

      {/* Expanded: action + benefit */}
      {expanded && (
        <>
          {/* Divider */}
          <div style={{ height: 1, background: "var(--border)", margin: "8px 0" }} />

          {/* Action */}
          {rec.action && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
                Ce que ça fait
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.65 }}>
                {rec.action}
              </div>
            </div>
          )}

          {/* Benefit */}
          {rec.benefit && (
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.2)",
              borderRadius: 8, padding: "5px 12px",
            }}>
              <span style={{ color: "#22c55e", flexShrink: 0 }}><IconCheck /></span>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: "#16a34a", lineHeight: 1.4 }}>
                {rec.benefit}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────────── */
export default function AIRecommendations({ sinceDays = 7 }: { sinceDays?: number }) {
  const [result, setResult]   = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await API.get(`/api/recommendations?since_days=${sinceDays}`);
      setResult(r.data);
    } catch (e: any) {
      setError(e.message ?? "Erreur de génération");
    } finally {
      setLoading(false);
    }
  };

  /* ── Empty state ── */
  if (!result && !loading) return (
    <div style={{ padding: "1.5rem 1rem", textAlign: "center" }}>
      <div style={{
        width: 52, height: 52, borderRadius: 14,
        background: "rgba(59,130,246,0.08)",
        border: "1px solid rgba(59,130,246,0.15)",
        display: "flex", alignItems: "center", justifyContent: "center",
        color: "#3b82f6", margin: "0 auto 14px",
      }}>
        <IconBot />
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
        Agents & Automatisations
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.6, maxWidth: 240, margin: "0 auto 18px" }}>
        L'IA analyse les patterns de vos messages et propose des agents adaptés à votre workflow.
      </div>
      {error && (
        <div style={{ fontSize: 11, color: "#ef4444", marginBottom: 12 }}>{error}</div>
      )}
      <button onClick={generate} style={{
        padding: "8px 20px", borderRadius: 10,
        background: "#1d2d44",
        color: "#f0ebd8", border: "none", cursor: "pointer",
        fontSize: 12.5, fontWeight: 600, letterSpacing: "0.01em",
        transition: "opacity 0.15s",
      }}>
        Analyser et proposer des agents
      </button>
    </div>
  );

  /* ── Loading state ── */
  if (loading) return (
    <div style={{ padding: "2rem 1rem", textAlign: "center" }}>
      <div style={{
        width: 22, height: 22,
        border: "2px solid var(--border)",
        borderTop: "2px solid #3b82f6",
        borderRadius: "50%",
        animation: "ai-spin 0.8s linear infinite",
        margin: "0 auto 12px",
      }} />
      <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
        Extraction des patterns en cours...
      </div>
      <style>{`@keyframes ai-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );

  /* ── Results ── */
  const recs: any[] = result?.recommendations ?? [];

  return (
    <div>
      {/* Features summary */}
      {result?.features_used && (
        <div style={{
          display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14,
          padding: "8px 10px",
          background: "var(--bg-input)", borderRadius: 10,
          border: "1px solid var(--border)",
        }}>
          <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>
            Basé sur{" "}
            <strong style={{ color: "var(--text-primary)" }}>
              {result.features_used.total_messages} messages
            </strong>
            {result.features_used.patterns_found?.length > 0 && (
              <> · patterns : {result.features_used.patterns_found.join(", ")}</>
            )}
          </span>
        </div>
      )}

      {/* Agent cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {recs.map((rec: any, i: number) => (
          <AgentCard key={i} rec={rec} index={i} />
        ))}
      </div>

      {/* Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
        <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>
          {result.provider} · {new Date(result.generated_at).toLocaleTimeString("fr-FR")} · {result.period}
        </span>
        <button onClick={generate} style={{
          padding: "4px 11px", borderRadius: 8, cursor: "pointer",
          border: "1px solid var(--border)", background: "transparent",
          color: "var(--text-secondary)", fontSize: 11,
          transition: "color 0.15s",
        }}>
          ↻ Actualiser
        </button>
      </div>
    </div>
  );
}
