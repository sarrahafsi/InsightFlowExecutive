"use client";
import { useEffect, useRef, useState } from "react";

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  delta?: number;
  deltaLabel?: string;
  icon?: React.ReactNode;
  accent?: string;
  risk?: "low" | "medium" | "high";
  onClick?: () => void;
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

const RISK_COLORS = { high: "#ef4444", medium: "#f59e0b", low: "#22c55e" };
const RISK_BG     = { high: "#fef2f2", medium: "#fffbeb", low: "#f0fdf4" };
const RISK_LABELS = { high: "Critique", medium: "Modéré", low: "Normal" };

export default function KPICard({
  title, value, subtitle, delta, icon, accent = "#3e5c76", risk, onClick, children,
}: KPICardProps) {
  const barColor   = risk ? RISK_COLORS[risk] : accent;
  const deltaColor = delta === undefined ? "#748cab" : delta > 0 ? "#22c55e" : delta < 0 ? "#ef4444" : "#748cab";
  const deltaArrow = delta === undefined ? "" : delta > 0 ? "↑" : delta < 0 ? "↓" : "→";
  const [hovered, setHovered] = useState(false);

  const numericValue = typeof value === "number" ? value : parseFloat(String(value));
  const isAnimatable = !isNaN(numericValue) && typeof value === "number";
  const animated     = useCountUp(isAnimatable ? numericValue : 0);
  const displayValue = isAnimatable ? animated : value;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      title={onClick ? "Voir le détail" : undefined}
      style={{
        background: "var(--bg-card)",
        borderRadius: 14,
        padding: "1.25rem 1.15rem",
        boxShadow: hovered ? `0 8px 28px ${barColor}22` : "0 2px 10px var(--shadow-card)",
        border: `1.5px solid ${hovered ? barColor + "44" : "var(--border)"}`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: 6,
        position: "relative",
        overflow: "hidden",
        transition: "box-shadow 0.2s, border-color 0.2s, transform 0.15s",
        transform: hovered ? "translateY(-2px)" : "none",
        cursor: onClick ? "pointer" : "default",
        minHeight: 150,
        justifyContent: "center",
      }}
    >
      {/* Accent bar — top */}
      <div style={{
        position: "absolute", top: 0, left: 0,
        width: hovered ? "100%" : "40%",
        height: 3,
        background: `linear-gradient(90deg, ${barColor}, ${barColor}33)`,
        borderRadius: "14px 14px 0 0",
        transition: "width 0.35s ease",
      }} />

      {/* Icon */}
      {icon && (
        <div style={{
          width: 42, height: 42, borderRadius: 11, flexShrink: 0,
          background: `${barColor}14`,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: barColor,
          transform: hovered ? "scale(1.08)" : "scale(1)",
          transition: "transform 0.2s",
          marginBottom: 2,
        }}>
          {icon}
        </div>
      )}

      {/* Value */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, justifyContent: "center" }}>
        <span style={{
          fontSize: 28,
          fontWeight: 700,
          color: "var(--text-primary)",
          lineHeight: 1,
          letterSpacing: "-0.02em",
          fontVariantNumeric: "tabular-nums",
        }}>
          {displayValue}
        </span>
        {delta !== undefined && (
          <span style={{ fontSize: 12, fontWeight: 700, color: deltaColor }}>
            {deltaArrow} {Math.abs(delta)}%
          </span>
        )}
      </div>

      {/* Title */}
      <span style={{
        fontSize: 12,
        fontWeight: 600,
        color: "var(--text-primary)",
        letterSpacing: "0.01em",
        lineHeight: 1.3,
      }}>
        {title}
      </span>

      {/* Subtitle */}
      {subtitle && (
        <span style={{
          fontSize: 11,
          color: "var(--text-secondary)",
          lineHeight: 1.4,
        }}>
          {subtitle}
        </span>
      )}

      {/* Risk badge */}
      {risk && (
        <span style={{
          fontSize: 10, fontWeight: 700,
          color: RISK_COLORS[risk],
          background: RISK_BG[risk],
          border: `1px solid ${RISK_COLORS[risk]}2a`,
          borderRadius: 20,
          padding: "2px 9px",
          letterSpacing: "0.03em",
        }}>
          {RISK_LABELS[risk]}
        </span>
      )}

      {/* Hover hint */}
      {onClick && (
        <span style={{
          position: "absolute", bottom: 8, right: 10,
          fontSize: 10, color: barColor, fontWeight: 600,
          opacity: hovered ? 1 : 0,
          transition: "opacity 0.2s",
        }}>
          Voir le détail →
        </span>
      )}

      {children}
    </div>
  );
}
