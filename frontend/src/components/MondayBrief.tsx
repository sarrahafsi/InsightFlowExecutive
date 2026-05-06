"use client";
import { useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function MondayBrief({ sinceDays = 7 }: { sinceDays?: number }) {
  const { t, locale } = useI18n();
  const [brief, setBrief]     = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await API.get(`/api/brief/weekly?since_days=${sinceDays}`);
      setBrief(r.data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ background: "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)", borderRadius: 20, padding: "1.75rem 2rem", marginBottom: "1.5rem", color: "#f0ebd8" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(240,235,216,0.6)", marginBottom: 6 }}>
            {t.brief_badge}
          </div>
          <h2 style={{ fontSize: 20, fontFamily: "DM Serif Display, serif", marginBottom: 4 }}>
            {t.brief_title}
          </h2>
          <p style={{ fontSize: 13, color: "rgba(240,235,216,0.7)" }}>
            {t.brief_sub(sinceDays)}
          </p>
        </div>
        <button
          onClick={generate}
          disabled={loading}
          style={{
            padding: "10px 22px", borderRadius: 12, border: "1px solid rgba(240,235,216,0.3)",
            background: loading ? "rgba(240,235,216,0.1)" : "rgba(240,235,216,0.15)",
            color: "#f0ebd8", fontSize: 13, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
            backdropFilter: "blur(4px)",
          }}
        >
          {loading ? t.brief_generating : brief ? t.brief_regenerate : t.brief_generate}
        </button>
      </div>

      {error && (
        <div style={{ marginTop: 16, padding: "10px 14px", background: "rgba(239,68,68,0.2)", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 10, fontSize: 12 }}>
          {error}
        </div>
      )}

      {brief && (
        <div style={{ marginTop: "1.5rem" }}>
          {/* Stats rapides */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: "1.25rem" }}>
            {[
              { label: t.brief_stat_messages, value: brief.stats_summary?.total_items },
              { label: t.brief_stat_risk, value: `${brief.stats_summary?.risk_index}/100` },
              { label: t.brief_stat_climate, value: brief.stats_summary?.climate },
              { label: t.brief_stat_positive, value: `${brief.stats_summary?.sentiment?.positive ?? 0}%` },
            ].map(s => (
              <div key={s.label} style={{ background: "rgba(240,235,216,0.1)", borderRadius: 10, padding: "8px 14px", border: "1px solid rgba(240,235,216,0.15)" }}>
                <div style={{ fontSize: 10, color: "rgba(240,235,216,0.6)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{s.label}</div>
                <div style={{ fontSize: 16, fontWeight: 700, marginTop: 2 }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* Texte narratif */}
          {brief.brief ? (
            <div style={{ background: "rgba(240,235,216,0.08)", borderRadius: 12, padding: "1.25rem 1.5rem", border: "1px solid rgba(240,235,216,0.12)" }}>
              <p style={{ fontSize: 14, lineHeight: 1.8, color: "rgba(240,235,216,0.9)", whiteSpace: "pre-wrap" }}>
                {brief.brief}
              </p>
            </div>
          ) : (
            <div style={{ padding: "1rem", background: "rgba(239,68,68,0.15)", borderRadius: 12, fontSize: 13, color: "rgba(240,235,216,0.8)" }}>
              {t.brief_no_ollama} <code>ollama run llama3.2</code>
            </div>
          )}

          <div style={{ fontSize: 11, color: "rgba(240,235,216,0.4)", marginTop: 10, textAlign: "right" }}>
            {t.brief_generated_at(new Date(brief.generated_at).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB"), brief.period)}
          </div>
        </div>
      )}
    </div>
  );
}
