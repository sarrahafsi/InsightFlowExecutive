"use client";
import {
  BarChart as ReBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";

interface BarData { label: string; value: number; color?: string; }

interface TooltipPayload {
  value: number;
  payload: BarData;
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
      <div style={{ color: "#748cab", marginBottom: 2 }}>{d.payload.label}</div>
      <div style={{ fontWeight: 700, fontSize: 16 }}>{d.value}</div>
    </div>
  );
}

export default function BarChart({ data, height = 140, color = "#3e5c76" }: {
  data: BarData[]; height?: number; color?: string;
}) {
  if (!data.length) return null;
  const chartData = data.map(d => ({ ...d, name: d.label }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ReBarChart data={chartData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }} barCategoryGap="35%">
        <CartesianGrid strokeDasharray="3 3" stroke="#f0ede8" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#748cab" }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 9, fill: "#748cab" }} tickLine={false} axisLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(62,92,118,0.05)" }} />
        <Bar dataKey="value" radius={[4, 4, 0, 0]} animationDuration={700}>
          {chartData.map((d, i) => (
            <Cell key={i} fill={d.color ?? color} fillOpacity={0.88} />
          ))}
        </Bar>
      </ReBarChart>
    </ResponsiveContainer>
  );
}
