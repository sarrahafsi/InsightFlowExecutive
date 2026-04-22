"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface PeriodData {
  label: string;
  total_items: number;
  risk_index: number;
  sentiment: { positive: number; neutral: number; negative: number };
  velocity: number;
  risk_count: number;
  climate_label?: string;
}

function Delta({ a, b, inverse = false }: { a: number; b: number; inverse?: boolean }) {
  if (b === 0) return null;
  const pct = Math.round(((a - b) / b) * 100);
  const good = inverse ? pct < 0 : pct > 0;
  const color = pct === 0 ? "#748cab" : good ? "#22c55e" : "#ef4444";
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color, marginLeft: 6 }}>
      {pct > 0 ? "↑" : pct < 0 ? "↓" : "="}{Math.abs(pct)}%
    </span>
  );
}

function CompareRow({ label, a, b, inverse = false, format = (v: number) => String(v) }: {
  label: string; a: number; b: number; inverse?: boolean; format?: (v: number) => string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "10px 0", borderBottom: "1px solid rgba(62,92,118,0.07)" }}>
      <div style={{ flex: 1, fontSize: 13, color: "#748cab" }}>{label}</div>
      <div style={{ width: 100, textAlign: "right", fontSize: 14, fontWeight: 700, color: "#0d1321" }}>
        {format(a)}<Delta a={a} b={b} inverse={inverse} />
      </div>
      <div style={{ width: 100, textAlign: "right", fontSize: 13, color: "#748cab" }}>{format(b)}</div>
    </div>
  );
}

export default function CompareMode() {
  const { t } = useI18n();
  const [data, setData]     = useState<{ period_a: PeriodData; period_b: PeriodData } | null>(null);
  const [loading, setLoading] = useState(true);
  const [periodA, setPeriodA] = useState(7);
  const [periodB, setPeriodB] = useState(14);

  useEffect(() => {
    setLoading(true);
    API.get(`/api/search/compare?period_a=${periodA}&period_b=${periodB}`)
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [periodA, periodB]);

  return (
    <div style={{ background: "#fff", borderRadius: 20, padding: "1.5rem 1.75rem", boxShadow: "0 2px 20px rgba(13,19,33,0.07)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>{t.compare_badge}</div>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>{t.compare_title}</h2>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select value={periodA} onChange={e => setPeriodA(Number(e.target.value))}
            style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)", fontSize: 12, color: "#3e5c76", background: "#f8f9fa" }}>
            {[3,7,14,30].map(d => <option key={d} value={d}>J-{d}</option>)}
          </select>
          <span style={{ fontSize: 12, color: "#748cab" }}>{t.compare_vs}</span>
          <select value={periodB} onChange={e => setPeriodB(Number(e.target.value))}
            style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)", fontSize: 12, color: "#748cab", background: "#f8f9fa" }}>
            {[7,14,30,60].map(d => <option key={d} value={d}>J-{d}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <p style={{ textAlign: "center", color: "#748cab", fontSize: 13, padding: "1rem" }}>{t.compare_loading}</p>
      ) : data ? (
        <div>
          {/* En-têtes colonnes */}
          <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
            <div style={{ flex: 1 }} />
            <div style={{ width: 100, textAlign: "right", fontSize: 11, fontWeight: 700, color: "#3e5c76", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              {data.period_a.label}
            </div>
            <div style={{ width: 100, textAlign: "right", fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              {data.period_b.label}
            </div>
          </div>

          <CompareRow label={t.compare_messages} a={data.period_a.total_items} b={data.period_b.total_items} />
          <CompareRow label={t.compare_risk_idx} a={data.period_a.risk_index} b={data.period_b.risk_index} inverse format={v => `${v}/100`} />
          <CompareRow label={t.compare_signals} a={data.period_a.risk_count} b={data.period_b.risk_count} inverse />
          <CompareRow label={t.compare_positive} a={data.period_a.sentiment.positive} b={data.period_b.sentiment.positive} format={v => `${v}%`} />
          <CompareRow label={t.compare_negative} a={data.period_a.sentiment.negative} b={data.period_b.sentiment.negative} inverse format={v => `${v}%`} />
          <CompareRow label={t.compare_volume} a={data.period_a.velocity} b={data.period_b.velocity} />

          {data.period_a.climate_label && (
            <div style={{ marginTop: 12, padding: "8px 12px", background: "rgba(62,92,118,0.05)", borderRadius: 8, fontSize: 12, color: "#3e5c76" }}>
              {t.compare_climate(data.period_a.climate_label ?? "")}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
