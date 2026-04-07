"use client";
interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  delta?: number;       // % change
  deltaLabel?: string;
  icon?: string;
  accent?: string;
  risk?: "low" | "medium" | "high";
  children?: React.ReactNode;
}

export default function KPICard({
  title, value, subtitle, delta, deltaLabel, icon, accent = "#3e5c76", risk, children
}: KPICardProps) {
  const riskColor = risk === "high" ? "#ef4444" : risk === "medium" ? "#f59e0b" : "#22c55e";
  const deltaColor = delta === undefined ? "#748cab" : delta > 0 ? "#22c55e" : delta < 0 ? "#ef4444" : "#748cab";
  const deltaArrow = delta === undefined ? "" : delta > 0 ? "↑" : delta < 0 ? "↓" : "→";

  return (
    <div style={{
      background: "#ffffff",
      borderRadius: 16,
      padding: "1.25rem 1.5rem",
      boxShadow: "0 2px 12px rgba(13,19,33,0.06)",
      border: "1px solid rgba(62,92,118,0.1)",
      display: "flex",
      flexDirection: "column",
      gap: 8,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Top accent bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 3,
        background: risk ? riskColor : accent,
        borderRadius: "16px 16px 0 0",
      }} />

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, color: "#748cab", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {title}
        </span>
        {icon && <span style={{ fontSize: 18 }}>{icon}</span>}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span style={{ fontSize: 28, fontWeight: 700, color: "#0d1321", lineHeight: 1 }}>
          {value}
        </span>
        {delta !== undefined && (
          <span style={{ fontSize: 13, fontWeight: 600, color: deltaColor }}>
            {deltaArrow} {Math.abs(delta)}% {deltaLabel ?? "vs sem. passée"}
          </span>
        )}
      </div>

      {subtitle && (
        <span style={{ fontSize: 12, color: "#748cab" }}>{subtitle}</span>
      )}

      {children}
    </div>
  );
}
