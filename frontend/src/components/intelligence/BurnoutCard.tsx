"use client";
import { useI18n } from "@/lib/i18n";

interface BurnoutData {
  after_hours_count: number;
  after_hours_rate: number;
  weekend_count: number;
  weekend_rate: number;
  high_burnout_count: number;
  avg_burnout_score: number;
}

function GaugeBar({ value, max = 100, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={{ height: 4, background: "rgba(0,0,0,0.06)", borderRadius: 4, overflow: "hidden", marginTop: 4 }}>
      <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.6s ease" }} />
    </div>
  );
}

export default function BurnoutCard({ data }: { data: BurnoutData }) {
  const { t } = useI18n();
  const riskLevel = data.high_burnout_count > 3 ? "high"
                  : data.after_hours_rate > 15 || data.weekend_rate > 10 ? "medium"
                  : "low";

  const riskColor = riskLevel === "high" ? "#ef4444" : riskLevel === "medium" ? "#f59e0b" : "#22c55e";

  return (
    <div style={{
      background: "#fff",
      borderRadius: 16,
      padding: "1.5rem",
      boxShadow: "0 2px 12px rgba(13,19,33,0.06)",
      border: `1px solid ${riskColor}30`,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab" }}>
            {t.burnout_title}
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#0d1321", marginTop: 2 }}>
            {t.burnout_subtitle}
          </div>
        </div>
        <div style={{
          padding: "4px 12px", borderRadius: 20,
          background: `${riskColor}15`,
          fontSize: 11, fontWeight: 700, color: riskColor,
          border: `1px solid ${riskColor}30`,
        }}>
          {riskLevel === "high" ? t.kpi_risk_high : riskLevel === "medium" ? t.kpi_risk_medium : t.kpi_risk_low}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
            <span style={{ fontSize: 12, color: "#748cab" }}>{t.burnout_after_hours}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: data.after_hours_rate > 15 ? "#f59e0b" : "#0d1321" }}>
              {data.after_hours_count} msgs ({data.after_hours_rate}%)
            </span>
          </div>
          <GaugeBar value={data.after_hours_rate} max={30} color={data.after_hours_rate > 15 ? "#f59e0b" : "#94a3b8"} />
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
            <span style={{ fontSize: 12, color: "#748cab" }}>{t.burnout_weekend}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: data.weekend_rate > 10 ? "#f97316" : "#0d1321" }}>
              {data.weekend_count} msgs ({data.weekend_rate}%)
            </span>
          </div>
          <GaugeBar value={data.weekend_rate} max={20} color={data.weekend_rate > 10 ? "#f97316" : "#94a3b8"} />
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
            <span style={{ fontSize: 12, color: "#748cab" }}>{t.burnout_score}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: data.high_burnout_count > 0 ? "#ef4444" : "#0d1321" }}>
              {t.burnout_authors(data.high_burnout_count)}
            </span>
          </div>
          <GaugeBar value={data.avg_burnout_score * 100} max={100} color={
            data.avg_burnout_score > 0.5 ? "#ef4444" : data.avg_burnout_score > 0.25 ? "#f59e0b" : "#22c55e"
          } />
          <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>
            {t.burnout_avg(Math.round(data.avg_burnout_score * 100))}
          </div>
        </div>
      </div>
    </div>
  );
}
