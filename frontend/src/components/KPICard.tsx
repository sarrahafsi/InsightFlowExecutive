"use client";
import { useEffect, useRef, useState } from "react";

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  delta?: number;
  deltaLabel?: string;
  icon?: string;
  accent?: string;
  risk?: "low" | "medium" | "high";
  children?: React.ReactNode;
}

function useCountUp(target: number, duration = 700) {
  const [count, setCount] = useState(0);
  const raf = useRef<number>(0);
  useEffect(() => {
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      setCount(Math.round(ease * target));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);
  return count;
}

export default function KPICard({
  title, value, subtitle, delta, deltaLabel, icon, accent = "#3e5c76", risk, children
}: KPICardProps) {
  const riskColor = risk === "high" ? "#ef4444" : risk === "medium" ? "#f59e0b" : "#22c55e";
  const barColor = risk ? riskColor : accent;
  const deltaColor = delta === undefined ? "#748cab" : delta > 0 ? "#22c55e" : delta < 0 ? "#ef4444" : "#748cab";
  const deltaArrow = delta === undefined ? "" : delta > 0 ? "↑" : delta < 0 ? "↓" : "→";
  const [hovered, setHovered] = useState(false);

  const numericValue = typeof value === "number" ? value : parseFloat(String(value));
  const isAnimatable = !isNaN(numericValue) && typeof value === "number";
  const animated = useCountUp(isAnimatable ? numericValue : 0);
  const displayValue = isAnimatable ? animated : value;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: "#ffffff",
        borderRadius: 16,
        padding: "1.25rem 1.5rem",
        boxShadow: hovered
          ? "0 8px 28px rgba(13,19,33,0.12)"
          : "0 2px 12px rgba(13,19,33,0.06)",
        border: `1px solid ${hovered ? barColor + "44" : "rgba(62,92,118,0.1)"}`,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        position: "relative",
        overflow: "hidden",
        transition: "box-shadow 0.2s, border-color 0.2s, transform 0.15s",
        transform: hovered ? "translateY(-2px)" : "none",
        cursor: "default",
      }}
    >
      {/* Accent bar */}
      <div style={{
        position: "absolute", top: 0, left: 0,
        width: hovered ? "100%" : "40%",
        height: 3,
        background: barColor,
        borderRadius: "16px 16px 0 0",
        transition: "width 0.35s ease",
      }} />

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, color: "#748cab", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {title}
        </span>
        {icon && (
          <span style={{
            fontSize: 18,
            transform: hovered ? "scale(1.15)" : "scale(1)",
            transition: "transform 0.2s",
            display: "inline-block",
          }}>{icon}</span>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span style={{
          fontSize: 28, fontWeight: 700, color: "#0d1321", lineHeight: 1,
          transition: "color 0.2s",
        }}>
          {displayValue}
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
