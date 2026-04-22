"use client";
import { useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const BUSINESS_LABELS = [
  "Progress", "Neutral Update", "Concern",
  "Risk", "Blocked", "Overload", "Conflict", "Urgent",
];
const SENTIMENT_LABELS = ["POSITIVE", "NEUTRAL", "NEGATIVE"];
const TOPICS = [
  "deadline", "budget", "hiring", "technical",
  "customer", "product", "strategy", "conflict", "other",
];

const LABEL_COLORS: Record<string, string> = {
  Blocked: "#ef4444", Urgent: "#f97316", Risk: "#f59e0b",
  Conflict: "#8b5cf6", Overload: "#ec4899", Concern: "#eab308",
  Progress: "#22c55e", "Neutral Update": "#94a3b8",
};
const SENTIMENT_COLORS: Record<string, string> = {
  POSITIVE: "#22c55e", NEUTRAL: "#94a3b8", NEGATIVE: "#ef4444",
};

interface Props {
  itemId: string;
  title: string;
  current: {
    business_label?: string;
    sentiment_label?: string;
    topic?: string;
  };
  onClose: () => void;
  onSaved: (corrections: Record<string, string>) => void;
}

export default function CorrectionModal({ itemId, title, current, onClose, onSaved }: Props) {
  const { t } = useI18n();
  const [businessLabel, setBusinessLabel]   = useState(current.business_label  ?? "");
  const [sentimentLabel, setSentimentLabel] = useState(current.sentiment_label ?? "");
  const [topic, setTopic]                   = useState(current.topic           ?? "");
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    const payload: Record<string, string> = {};
    if (businessLabel  && businessLabel  !== current.business_label)  payload.business_label  = businessLabel;
    if (sentimentLabel && sentimentLabel !== current.sentiment_label) payload.sentiment_label = sentimentLabel;
    if (topic          && topic          !== current.topic)           payload.topic           = topic;

    if (Object.keys(payload).length === 0) {
      onClose();
      return;
    }

    try {
      await API.patch(`/api/items/${itemId}/correct`, payload);
      onSaved(payload);
      onClose();
    } catch (e: any) {
      setError(e.message ?? "Erreur lors de la correction");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(13,19,33,0.45)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: "1rem",
    }} onClick={onClose}>
      <div style={{
        background: "#fff", borderRadius: 20,
        padding: "2rem", width: "100%", maxWidth: 480,
        boxShadow: "0 20px 60px rgba(13,19,33,0.2)",
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#748cab", fontWeight: 600, marginBottom: 6 }}>
            {t.correction_title}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#0d1321", lineHeight: 1.4 }}>
            {title}
          </div>
        </div>

        {/* Business Label */}
        <div style={{ marginBottom: "1.25rem" }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#3e5c76", display: "block", marginBottom: 8 }}>
            {t.correction_business}
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {BUSINESS_LABELS.map(lbl => (
              <button key={lbl} onClick={() => setBusinessLabel(lbl)} style={{
                padding: "5px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
                fontWeight: businessLabel === lbl ? 700 : 400,
                border: `1.5px solid ${businessLabel === lbl ? LABEL_COLORS[lbl] : "rgba(62,92,118,0.2)"}`,
                background: businessLabel === lbl ? `${LABEL_COLORS[lbl]}18` : "transparent",
                color: businessLabel === lbl ? LABEL_COLORS[lbl] : "#748cab",
                transition: "all 0.15s",
              }}>
                {lbl}
              </button>
            ))}
          </div>
        </div>

        {/* Sentiment */}
        <div style={{ marginBottom: "1.25rem" }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#3e5c76", display: "block", marginBottom: 8 }}>
            {t.correction_sentiment}
          </label>
          <div style={{ display: "flex", gap: 6 }}>
            {SENTIMENT_LABELS.map(lbl => (
              <button key={lbl} onClick={() => setSentimentLabel(lbl)} style={{
                padding: "5px 16px", borderRadius: 20, fontSize: 12, cursor: "pointer",
                fontWeight: sentimentLabel === lbl ? 700 : 400,
                border: `1.5px solid ${sentimentLabel === lbl ? SENTIMENT_COLORS[lbl] : "rgba(62,92,118,0.2)"}`,
                background: sentimentLabel === lbl ? `${SENTIMENT_COLORS[lbl]}18` : "transparent",
                color: sentimentLabel === lbl ? SENTIMENT_COLORS[lbl] : "#748cab",
                transition: "all 0.15s",
              }}>
                {lbl}
              </button>
            ))}
          </div>
        </div>

        {/* Topic */}
        <div style={{ marginBottom: "1.5rem" }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#3e5c76", display: "block", marginBottom: 8 }}>
            {t.correction_topic}
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {TOPICS.map(t => (
              <button key={t} onClick={() => setTopic(t)} style={{
                padding: "5px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
                fontWeight: topic === t ? 700 : 400,
                border: `1.5px solid ${topic === t ? "#3e5c76" : "rgba(62,92,118,0.2)"}`,
                background: topic === t ? "rgba(62,92,118,0.1)" : "transparent",
                color: topic === t ? "#3e5c76" : "#748cab",
                transition: "all 0.15s",
              }}>
                {t}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "#ef4444", marginBottom: 12 }}>
            {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={{
            padding: "8px 20px", borderRadius: 10, border: "1px solid rgba(62,92,118,0.2)",
            background: "transparent", color: "#748cab", fontSize: 13, cursor: "pointer",
          }}>
            {t.correction_cancel}
          </button>
          <button onClick={handleSave} disabled={saving} style={{
            padding: "8px 20px", borderRadius: 10, border: "none",
            background: saving ? "rgba(62,92,118,0.4)" : "linear-gradient(135deg, #1d2d44, #3e5c76)",
            color: "#f0ebd8", fontSize: 13, fontWeight: 600, cursor: saving ? "not-allowed" : "pointer",
          }}>
            {saving ? t.correction_saving : t.correction_save}
          </button>
        </div>
      </div>
    </div>
  );
}
