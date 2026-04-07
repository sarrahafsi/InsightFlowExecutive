"use client";
interface Point { date: string; count: number; }

export default function LineChart({ data, height = 120, color = "#3e5c76" }: {
  data: Point[]; height?: number; color?: string;
}) {
  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.count), 1);
  const W = 600, H = height - 20, pad = 10;
  const xs = data.map((_, i) => pad + (i / (data.length - 1)) * (W - pad * 2));
  const ys = data.map(d => H - (d.count / max) * (H - pad) + pad * 0.5);

  const line = xs.map((x, i) => `${i === 0 ? "M" : "L"} ${x} ${ys[i]}`).join(" ");
  const area = `${line} L ${xs[xs.length - 1]} ${H + pad} L ${xs[0]} ${H + pad} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${height}`} style={{ width: "100%", height }}>
      <defs>
        <linearGradient id={`lg-${color.replace("#","")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.15} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      {/* Grid lines */}
      {[0.25, 0.5, 0.75, 1].map(f => (
        <line key={f} x1={pad} y1={H * (1 - f) + pad} x2={W - pad} y2={H * (1 - f) + pad}
          stroke="#e8e4d9" strokeWidth={1} />
      ))}
      <path d={area} fill={`url(#lg-${color.replace("#","")})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {/* Dots */}
      {xs.map((x, i) => data[i].count > 0 && (
        <circle key={i} cx={x} cy={ys[i]} r={3.5} fill={color}>
          <title>{data[i].date}: {data[i].count}</title>
        </circle>
      ))}
      {/* X labels — show every 2nd */}
      {data.map((d, i) => i % 2 === 0 && (
        <text key={i} x={xs[i]} y={height - 2} textAnchor="middle"
          fontSize={9} fill="#748cab" fontFamily="DM Sans, sans-serif">
          {d.date.slice(5)}
        </text>
      ))}
    </svg>
  );
}
