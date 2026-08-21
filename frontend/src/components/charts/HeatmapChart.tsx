"use client";
import { useEffect, useRef, useState } from "react";
import API from "@/lib/api";

const DAYS  = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

function cellColor(count: number, maxVal: number): string {
  if (count === 0) return "#eef2f7";
  const t = count / maxVal;
  if (t > 0.7) return "#ef4444";
  if (t > 0.4) return "#f97316";
  if (t > 0.15) return "#fbbf24";
  return "#fde68a";
}

function cellTextColor(count: number, maxVal: number): string {
  const t = count / maxVal;
  return t > 0.4 ? "#fff" : "transparent";
}

export default function HeatmapChart({ sinceDays = 30 }: { sinceDays?: number }) {
  const [heatData, setHeatData] = useState<any | null>(null);
  const [loading, setLoading]   = useState(true);
  const [tooltip, setTooltip]   = useState<{ x: number; y: number; day: string; hour: number; count: number } | null>(null);

  useEffect(() => {
    API.get(`/api/analytics/heatmap?since_days=${sinceDays}`)
      .then(r => setHeatData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sinceDays]);

  if (loading) return (
    <div style={{ height: 160, display: "flex", alignItems: "center", justifyContent: "center", color: "#748cab", fontSize: 13 }}>
      Chargement...
    </div>
  );
  if (!heatData) return null;

  const maxVal = heatData.max_value || 1;
  const matrix: number[][] = Array.from({ length: 7 }, () => new Array(24).fill(0));
  for (const d of heatData.data as any[]) {
    matrix[d.day_index][d.hour] = d.count;
  }

  return (
    <div style={{ width: "100%" }}>
      {/* Hour axis */}
      <div style={{ display: "flex", paddingLeft: 36, marginBottom: 4 }}>
        {HOURS.map(h => (
          <div key={h} style={{
            flex: 1, textAlign: "center", fontSize: 9, color: "#94a3b8", lineHeight: 1,
            visibility: h % 3 === 0 ? "visible" : "hidden",
          }}>
            {h}h
          </div>
        ))}
      </div>

      {/* Grid rows */}
      {DAYS.map((day, di) => (
        <div key={day} style={{ display: "flex", alignItems: "center", marginBottom: 3 }}>
          {/* Day label */}
          <div style={{ width: 30, flexShrink: 0, fontSize: 10, color: "#748cab", textAlign: "right", paddingRight: 6 }}>
            {day}
          </div>
          {/* Cells */}
          {HOURS.map(h => {
            const count = matrix[di][h];
            return (
              <div
                key={h}
                onMouseEnter={e => {
                  if (count > 0) {
                    const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                    setTooltip({ x: rect.left + rect.width / 2, y: rect.top, day, hour: h, count });
                  }
                }}
                onMouseLeave={() => setTooltip(null)}
                style={{
                  flex: 1,
                  height: 20,
                  marginRight: 2,
                  borderRadius: 3,
                  background: cellColor(count, maxVal),
                  cursor: count > 0 ? "pointer" : "default",
                  transition: "transform 0.1s, box-shadow 0.1s",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 8, color: cellTextColor(count, maxVal), fontWeight: 700,
                }}
              >
                {count > 0 && count}
              </div>
            );
          })}
        </div>
      ))}

      {/* Legend + peak info */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 10, color: "#94a3b8" }}>Faible</span>
          {["#fde68a", "#fbbf24", "#f97316", "#ef4444"].map(c => (
            <div key={c} style={{ width: 14, height: 14, borderRadius: 3, background: c }} />
          ))}
          <span style={{ fontSize: 10, color: "#94a3b8" }}>Élevé</span>
        </div>
        <span style={{ fontSize: 10, color: "#94a3b8" }}>
          Tensions & frustrations · {sinceDays} derniers jours
        </span>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: "fixed",
          left: tooltip.x, top: tooltip.y - 8,
          transform: "translate(-50%, -100%)",
          background: "#1d2d44", color: "#f0ebd8",
          padding: "5px 12px", borderRadius: 8,
          fontSize: 12, pointerEvents: "none", zIndex: 9999,
          whiteSpace: "nowrap", boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
        }}>
          <strong>{tooltip.day}</strong> à {tooltip.hour}h — {tooltip.count} tension{tooltip.count > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
