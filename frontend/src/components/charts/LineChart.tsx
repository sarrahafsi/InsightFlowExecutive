"use client";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";

interface Point { date: string; count: number; }

interface TooltipPayload {
  value: number;
}

function CustomTooltip({ active, payload, label }: {
  active?: boolean; payload?: TooltipPayload[]; label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#0d1321", color: "#fff", borderRadius: 10,
      padding: "8px 14px", fontSize: 12, boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
    }}>
      <div style={{ color: "#748cab", marginBottom: 2 }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: 16 }}>{payload[0].value}</div>
    </div>
  );
}

export default function LineChart({ data, height = 120, color = "#3e5c76" }: {
  data: Point[]; height?: number; color?: string;
}) {
  if (!data.length) return null;
  const chartData = data.map(d => ({ date: d.date.slice(5), count: d.count }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
        <defs>
          <linearGradient id={`fill-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.18} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0ede8" vertical={false} />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#748cab" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 9, fill: "#748cab" }} tickLine={false} axisLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: "4 2" }} />
        <Area
          type="monotone" dataKey="count"
          stroke={color} strokeWidth={2.5}
          fill={`url(#fill-${color.replace("#", "")})`}
          dot={{ r: 3.5, fill: color, strokeWidth: 0 }}
          activeDot={{ r: 5, fill: color, stroke: "#fff", strokeWidth: 2 }}
          animationDuration={800}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
