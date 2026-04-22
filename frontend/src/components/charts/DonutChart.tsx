"use client";
import { useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

interface Slice { label: string; value: number; color: string; }

interface TooltipPayload {
  name: string;
  value: number;
  payload: Slice & { pct: number };
}

function CustomTooltip({ active, payload }: {
  active?: boolean; payload?: TooltipPayload[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div style={{
      background: "#0d1321", color: "#fff", borderRadius: 10,
      padding: "8px 14px", fontSize: 12, boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
    }}>
      <div style={{ color: "#748cab", marginBottom: 2 }}>{d.name}</div>
      <div style={{ fontWeight: 700, fontSize: 16 }}>{d.value} <span style={{ fontSize: 11, color: "#748cab" }}>({d.payload.pct}%)</span></div>
    </div>
  );
}

export default function DonutChart({ data, size = 160, label }: {
  data: Slice[]; size?: number; label?: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const chartData = data.map(d => ({ ...d, name: d.label, pct: Math.round(d.value / total * 100) }));

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
      <div style={{ width: size, height: size, flexShrink: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%" cy="50%"
              innerRadius={size * 0.3}
              outerRadius={size * 0.44}
              paddingAngle={2}
              dataKey="value"
              animationBegin={0}
              animationDuration={700}
              onMouseEnter={(_, i) => setActive(i)}
              onMouseLeave={() => setActive(null)}
            >
              {chartData.map((d, i) => (
                <Cell
                  key={i} fill={d.color}
                  opacity={active === null || active === i ? 1 : 0.45}
                  stroke={active === i ? "#fff" : "none"}
                  strokeWidth={active === i ? 2 : 0}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            {/* Center label */}
          </PieChart>
        </ResponsiveContainer>
        {/* Center text via absolute overlay */}
        <div style={{
          position: "relative", marginTop: -size, height: size,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          pointerEvents: "none",
        }}>
          <span style={{ fontSize: size * 0.14, fontWeight: 700, color: "#0d1321", lineHeight: 1 }}>
            {active !== null ? chartData[active].value : total}
          </span>
          <span style={{ fontSize: size * 0.08, color: "#748cab", marginTop: 2 }}>
            {active !== null ? chartData[active].pct + "%" : label}
          </span>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1, minWidth: 100 }}>
        {chartData.map((d, i) => (
          <div
            key={i}
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive(null)}
            style={{
              display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
              opacity: active === null || active === i ? 1 : 0.45,
              transition: "opacity 0.15s",
            }}
          >
            <div style={{
              width: 10, height: 10, borderRadius: 2, background: d.color, flexShrink: 0,
              transform: active === i ? "scale(1.3)" : "scale(1)", transition: "transform 0.15s",
            }} />
            <span style={{ fontSize: 12, color: "#0d1321" }}>{d.label}</span>
            <span style={{ fontSize: 12, color: "#748cab", marginLeft: "auto", paddingLeft: 8 }}>
              {d.pct}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
