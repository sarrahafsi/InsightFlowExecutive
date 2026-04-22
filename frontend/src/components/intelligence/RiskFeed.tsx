"use client";
import { useState } from "react";
import CorrectionModal from "./CorrectionModal";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface RiskItem {
  id: string;
  title: string;
  author: string;
  timestamp: string;
  source: string;
  business_label: string;
  business_reason: string;
  emotion_label: string;
  burnout_score?: number;
  is_after_hours?: boolean;
  is_weekend?: boolean;
}

const LABEL_META: Record<string, { color: string; bg: string; border: string; icon: string }> = {
  "Blocked":  { color: "#ef4444", bg: "#fef2f2", border: "#fecaca", icon: "🚫" },
  "Urgent":   { color: "#f97316", bg: "#fff7ed", border: "#fed7aa", icon: "🚨" },
  "Risk":     { color: "#f59e0b", bg: "#fffbeb", border: "#fde68a", icon: "⚠️" },
  "Conflict": { color: "#8b5cf6", bg: "#f5f3ff", border: "#ddd6fe", icon: "⚔️" },
  "Overload": { color: "#ec4899", bg: "#fdf4ff", border: "#f5d0fe", icon: "💥" },
  "Concern":  { color: "#eab308", bg: "#fefce8", border: "#fef08a", icon: "🔶" },
};

const SOURCE_ICONS: Record<string, string> = {
  gmail: "✉", slack: "#", jira: "J",
};

const EMOTION_ICONS: Record<string, string> = {
  frustration: "🔥",
  urgency: "⚡",
  concern: "⚠️",
  satisfaction: "✅",
  neutral: "○",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export default function RiskFeed({
  items,
  title,
  maxItems = 6,
}: {
  items: RiskItem[];
  title?: string;
  maxItems?: number;
}) {
  const { t } = useI18n();
  const [correcting, setCorrecting] = useState<RiskItem | null>(null);
  const [localItems, setLocalItems] = useState<RiskItem[]>(items);
  const [addedActions, setAddedActions] = useState<Set<string>>(new Set());

  const addAction = async (item: RiskItem) => {
    try {
      await API.post("/api/actions", {
        message_id:     item.id,
        title:          item.title,
        author:         item.author,
        source:         item.source,
        business_label: item.business_label,
      });
      setAddedActions(prev => new Set([...prev, item.id]));
    } catch {}
  };

  if (!localItems || localItems.length === 0) return null;

  const displayed = localItems.slice(0, maxItems);

  return (
    <div style={{
      background: "#fff",
      borderRadius: 20,
      padding: "1.75rem 2rem",
      boxShadow: "0 2px 20px rgba(13,19,33,0.07)",
      border: "1px solid rgba(239,68,68,0.15)",
      marginBottom: "1.5rem",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "1.25rem" }}>
        <div style={{
          width: 8, height: 8, borderRadius: "50%", background: "#ef4444",
          boxShadow: "0 0 0 3px rgba(239,68,68,0.2)",
          animation: "pulse 2s infinite",
        }} />
        <style>{`@keyframes pulse{0%,100%{box-shadow:0 0 0 3px rgba(239,68,68,0.2)}50%{box-shadow:0 0 0 6px rgba(239,68,68,0.1)}}`}</style>
        <div>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "#ef4444" }}>
            {title ?? t.risk_title}
          </span>
          <span style={{ fontSize: 11, color: "#748cab", marginLeft: 8 }}>
            {t.risk_signals(items.length)}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {displayed.map((item) => {
          const meta = LABEL_META[item.business_label] ?? LABEL_META["Concern"];
          return (
            <div key={item.id} style={{
              display: "flex",
              background: meta.bg,
              border: `1px solid ${meta.border}`,
              borderRadius: 12,
              overflow: "hidden",
              position: "relative",
            }}>
              {/* Left accent */}
              <div style={{ width: 4, background: meta.color, flexShrink: 0 }} />

              {/* Label badge */}
              <div style={{
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 4,
                minWidth: 90,
                borderRight: `1px solid ${meta.border}`,
                flexShrink: 0,
              }}>
                <span style={{ fontSize: 20 }}>{meta.icon}</span>
                <span style={{
                  fontSize: 9, fontWeight: 800, letterSpacing: "0.1em",
                  textTransform: "uppercase", color: meta.color, textAlign: "center",
                }}>
                  {item.business_label}
                </span>
              </div>

              {/* Content */}
              <div style={{ padding: "12px 16px", flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.title || t.risk_no_title}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, color: "#748cab" }}>
                    {SOURCE_ICONS[item.source] ?? "◈"} {item.source.charAt(0).toUpperCase() + item.source.slice(1)}
                  </span>
                  <span style={{ fontSize: 11, color: "#748cab" }}>·</span>
                  <span style={{ fontSize: 11, color: "#748cab" }}>{item.author}</span>
                  <span style={{ fontSize: 11, color: "#748cab" }}>·</span>
                  <span style={{ fontSize: 11, color: "#748cab" }}>{formatDate(item.timestamp)}</span>

                  {["frustration", "urgency", "concern"].includes(item.emotion_label) && (
                    <>
                      <span style={{ fontSize: 11, color: "#748cab" }}>·</span>
                      <span style={{ fontSize: 11 }}>
                        {EMOTION_ICONS[item.emotion_label] ?? "○"} {item.emotion_label}
                      </span>
                    </>
                  )}
                  {item.is_after_hours && (
                    <span style={{ fontSize: 10, background: "#fef3c7", color: "#92400e", borderRadius: 8, padding: "1px 6px", fontWeight: 600 }}>
                      {t.risk_after_hours}
                    </span>
                  )}
                  {item.is_weekend && (
                    <span style={{ fontSize: 10, background: "#ede9fe", color: "#6d28d9", borderRadius: 8, padding: "1px 6px", fontWeight: 600 }}>
                      {t.risk_weekend}
                    </span>
                  )}
                  {item.burnout_score !== undefined && item.burnout_score !== null && item.burnout_score >= 0.5 && (
                    <span style={{ fontSize: 10, background: "#fce7f3", color: "#be185d", borderRadius: 8, padding: "1px 6px", fontWeight: 600 }}>
                      {t.risk_burnout(Math.round(item.burnout_score * 100))}
                    </span>
                  )}
                </div>
                {item.business_reason && (
                  <div style={{ fontSize: 12, color: "#748cab", marginTop: 6, fontStyle: "italic", lineHeight: 1.4 }}>
                    &ldquo;{item.business_reason}&rdquo;
                  </div>
                )}
              </div>

              {/* Boutons actions */}
              <div style={{ position: "absolute", top: 8, right: 8, display: "flex", gap: 4 }}>
                <button
                  onClick={() => addAction(item)}
                  disabled={addedActions.has(item.id)}
                  title="Ajouter en action CEO"
                  style={{
                    padding: "3px 8px", borderRadius: 6, border: "1px solid rgba(62,92,118,0.2)",
                    background: addedActions.has(item.id) ? "#f0fdf4" : "rgba(255,255,255,0.9)",
                    color: addedActions.has(item.id) ? "#22c55e" : "#748cab",
                    fontSize: 10, cursor: addedActions.has(item.id) ? "default" : "pointer", fontWeight: 500,
                  }}
                >
                  {addedActions.has(item.id) ? t.btn_added : t.btn_add_action}
                </button>
                <button
                  onClick={() => setCorrecting(item)}
                  title="Corriger les labels NLP"
                  style={{
                    padding: "3px 8px", borderRadius: 6, border: "1px solid rgba(62,92,118,0.2)",
                    background: "rgba(255,255,255,0.9)", color: "#748cab",
                    fontSize: 10, cursor: "pointer", fontWeight: 500,
                  }}
                >
                  ✏️
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {localItems.length > maxItems && (
        <div style={{ textAlign: "center", marginTop: 12, fontSize: 12, color: "#748cab" }}>
          {t.risk_more(localItems.length - maxItems)}
        </div>
      )}

      {correcting && (
        <CorrectionModal
          itemId={correcting.id}
          title={correcting.title}
          current={{
            business_label:  correcting.business_label,
            sentiment_label: correcting.emotion_label,
            topic:           undefined,
          }}
          onClose={() => setCorrecting(null)}
          onSaved={(corrections) => {
            setLocalItems(prev => prev.map(it =>
              it.id === correcting.id
                ? { ...it, business_label: corrections.business_label ?? it.business_label }
                : it
            ));
          }}
        />
      )}
    </div>
  );
}
