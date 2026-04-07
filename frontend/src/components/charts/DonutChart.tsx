"use client";
interface Slice { label: string; value: number; color: string; }

function arc(cx: number, cy: number, r: number, start: number, end: number) {
  const s = { x: cx + r * Math.cos((start - 90) * Math.PI / 180), y: cy + r * Math.sin((start - 90) * Math.PI / 180) };
  const e = { x: cx + r * Math.cos((end   - 90) * Math.PI / 180), y: cy + r * Math.sin((end   - 90) * Math.PI / 180) };
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${end - start > 180 ? 1 : 0} 1 ${e.x} ${e.y}`;
}

export default function DonutChart({ data, size = 160, label }: {
  data: Slice[]; size?: number; label?: string;
}) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const cx = size / 2, cy = size / 2, r = size * 0.36, inner = size * 0.22;
  let angle = 0;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
        {data.map((d, i) => {
          const sweep = (d.value / total) * 360;
          const path = arc(cx, cy, r, angle, angle + sweep - 0.5);
          angle += sweep;
          return (
            <path key={i} d={path} fill="none" stroke={d.color}
              strokeWidth={size * 0.14} strokeLinecap="butt">
              <title>{d.label}: {d.value} ({Math.round(d.value / total * 100)}%)</title>
            </path>
          );
        })}
        <circle cx={cx} cy={cy} r={inner} fill="white" />
        {label && (
          <>
            <text x={cx} y={cy - 4} textAnchor="middle" fontSize={size * 0.11}
              fontWeight="700" fill="#0d1321" fontFamily="DM Sans, sans-serif">
              {total}
            </text>
            <text x={cx} y={cy + 12} textAnchor="middle" fontSize={size * 0.07}
              fill="#748cab" fontFamily="DM Sans, sans-serif">
              {label}
            </text>
          </>
        )}
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {data.map((d, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: d.color, flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: "#0d1321", fontFamily: "DM Sans, sans-serif" }}>
              {d.label}
            </span>
            <span style={{ fontSize: 12, color: "#748cab", marginLeft: "auto", paddingLeft: 12 }}>
              {Math.round(d.value / total * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
