"use client";
interface BarData { label: string; value: number; color?: string; }

export default function BarChart({ data, height = 140, color = "#3e5c76" }: {
  data: BarData[]; height?: number; color?: string;
}) {
  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  const w = 100 / data.length;

  return (
    <svg viewBox={`0 0 ${data.length * 24} ${height}`} style={{ width: "100%", height }}>
      {data.map((d, i) => {
        const bh = Math.max((d.value / max) * (height - 28), 2);
        const x = i * 24 + 2;
        const y = height - 20 - bh;
        return (
          <g key={i}>
            <rect x={x} y={y} width={20} height={bh}
              fill={d.color ?? color} rx={3} opacity={0.85}>
              <title>{d.label}: {d.value}</title>
            </rect>
            <text x={x + 10} y={height - 6} textAnchor="middle"
              fontSize={9} fill="#748cab" fontFamily="DM Sans, sans-serif">
              {d.label}
            </text>
            {d.value > 0 && (
              <text x={x + 10} y={y - 3} textAnchor="middle"
                fontSize={8} fill={color} fontFamily="DM Sans, sans-serif" fontWeight="600">
                {d.value}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
