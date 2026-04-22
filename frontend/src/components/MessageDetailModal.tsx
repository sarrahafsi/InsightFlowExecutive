"use client";

import { useState } from "react";
import API from "@/lib/api";

const LABEL_COLORS: Record<string, string> = {
  Blocked: "#ef4444", Urgent: "#f97316", Risk: "#f59e0b",
  Conflict: "#8b5cf6", Overload: "#ec4899", Concern: "#eab308",
  Progress: "#22c55e", "Neutral Update": "#94a3b8",
};
const SENTIMENT_COLORS: Record<string, string> = {
  POSITIVE: "#22c55e", NEUTRAL: "#94a3b8", NEGATIVE: "#ef4444",
};

interface MessageDetail {
  id: string;
  title: string;
  author: string;
  timestamp: string;
  source: string;
  snippet?: string;
  content?: string;
  business_label?: string;
  business_reason?: string;
  sentiment_label?: string;
  emotion_label?: string;
  topic?: string;
  is_after_hours?: boolean;
  is_weekend?: boolean;
  burnout_score?: number;
}

export default function MessageDetailModal({
  item,
  onClose,
}: {
  item: MessageDetail;
  onClose: () => void;
}) {
  const bl      = item.business_label || "Neutral Update";
  const blColor = LABEL_COLORS[bl] ?? "#94a3b8";
  const slColor = SENTIMENT_COLORS[item.sentiment_label ?? ""] ?? "#94a3b8";

  // Draft / Send state
  const [draft,        setDraft]        = useState("");
  const [draftTo,      setDraftTo]      = useState("");
  const [draftSubject, setDraftSubject] = useState("");
  const [threadId,     setThreadId]     = useState<string | null>(null);
  const [generating,   setGenerating]   = useState(false);
  const [sending,      setSending]      = useState(false);
  const [sent,         setSent]         = useState(false);
  const [error,        setError]        = useState("");

  const isGmail = item.source === "gmail";

  async function handleGenerateDraft() {
    setGenerating(true);
    setError("");
    setDraft("");
    setSent(false);
    try {
      const res = await API.post(`/api/emails/draft/${item.id}`, {});
      setDraft(res.data.draft);
      setDraftTo(res.data.to      ?? "");
      setDraftSubject(res.data.subject ?? `Re: ${item.title}`);
      setThreadId(res.data.thread_id  ?? null);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Erreur lors de la génération du brouillon.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleSend() {
    if (!draft.trim()) return;
    setSending(true);
    setError("");
    try {
      await API.post("/api/emails/send", {
        to:        draftTo,
        subject:   draftSubject,
        body:      draft,
        thread_id: threadId,
      });
      setSent(true);
      setDraft("");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Erreur lors de l'envoi.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(13,19,33,0.5)", display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}
      onClick={onClose}
    >
      <div
        style={{ background: "#fff", borderRadius: 20, width: "100%", maxWidth: 580, maxHeight: "90vh", overflow: "auto", boxShadow: "0 24px 64px rgba(13,19,33,0.22)" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ padding: "1.5rem 1.75rem 1rem", borderBottom: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: "#748cab", marginBottom: 6, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span>{item.source.toUpperCase()}</span>
                <span>·</span>
                <span>{item.author}</span>
                <span>·</span>
                <span>{new Date(item.timestamp).toLocaleString("fr-FR")}</span>
              </div>
              <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", lineHeight: 1.4 }}>
                {item.title}
              </h2>
            </div>
            <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, color: "#748cab", cursor: "pointer", padding: "0 4px", flexShrink: 0 }}>✕</button>
          </div>
        </div>

        {/* NLP Labels */}
        <div style={{ padding: "1rem 1.75rem", display: "flex", flexWrap: "wrap", gap: 8, borderBottom: "1px solid rgba(62,92,118,0.08)" }}>
          {item.business_label && (
            <span style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 700, background: `${blColor}18`, color: blColor, border: `1px solid ${blColor}40` }}>
              {bl}
            </span>
          )}
          {item.sentiment_label && (
            <span style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: `${slColor}15`, color: slColor, border: `1px solid ${slColor}30` }}>
              {item.sentiment_label}
            </span>
          )}
          {item.emotion_label && (
            <span style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, background: "rgba(62,92,118,0.08)", color: "#3e5c76", border: "1px solid rgba(62,92,118,0.15)" }}>
              {item.emotion_label}
            </span>
          )}
          {item.topic && (
            <span style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, background: "rgba(62,92,118,0.08)", color: "#3e5c76", border: "1px solid rgba(62,92,118,0.15)" }}>
              📌 {item.topic}
            </span>
          )}
          {item.is_after_hours && (
            <span style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, background: "#fef3c7", color: "#92400e" }}>🌙 hors horaires</span>
          )}
          {item.is_weekend && (
            <span style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, background: "#ede9fe", color: "#6d28d9" }}>📅 week-end</span>
          )}
        </div>

        {/* Business reason */}
        {item.business_reason && (
          <div style={{ padding: "1rem 1.75rem", background: `${blColor}08`, borderBottom: "1px solid rgba(62,92,118,0.08)" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: blColor, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Analyse IA</div>
            <p style={{ fontSize: 13, color: "#3e5c76", fontStyle: "italic", lineHeight: 1.6 }}>&ldquo;{item.business_reason}&rdquo;</p>
          </div>
        )}

        {/* Content */}
        <div style={{ padding: "1.25rem 1.75rem", borderBottom: isGmail ? "1px solid rgba(62,92,118,0.08)" : "none" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#748cab", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.08em" }}>Contenu</div>
          <p style={{ fontSize: 13, color: "#3e5c76", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
            {item.snippet || item.content || "(contenu non disponible)"}
          </p>
        </div>

        {/* Draft & Send — Gmail only */}
        {isGmail && (
          <div style={{ padding: "1.25rem 1.75rem 1.75rem" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#748cab", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Répondre
            </div>

            {/* Bouton générer */}
            {!draft && !sent && (
              <button
                onClick={handleGenerateDraft}
                disabled={generating}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "10px 20px", borderRadius: 10, border: "none",
                  background: generating ? "#e2e8f0" : "#1d4ed8",
                  color: generating ? "#94a3b8" : "#fff",
                  fontSize: 13, fontWeight: 600, cursor: generating ? "not-allowed" : "pointer",
                  transition: "all 0.15s",
                }}
              >
                {generating ? (
                  <>
                    <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid #94a3b8", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
                    Génération en cours...
                  </>
                ) : (
                  <> Générer une réponse</>
                )}
              </button>
            )}

            {/* Brouillon généré */}
            {draft && !sent && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* À / Objet */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 11, color: "#748cab", width: 44, flexShrink: 0 }}>À</span>
                    <input
                      value={draftTo}
                      onChange={e => setDraftTo(e.target.value)}
                      style={{ flex: 1, fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)", color: "#0d1321", background: "#f8f9fa", outline: "none" }}
                    />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 11, color: "#748cab", width: 44, flexShrink: 0 }}>Objet</span>
                    <input
                      value={draftSubject}
                      onChange={e => setDraftSubject(e.target.value)}
                      style={{ flex: 1, fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)", color: "#0d1321", background: "#f8f9fa", outline: "none" }}
                    />
                  </div>
                </div>

                {/* Corps du brouillon */}
                <textarea
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  rows={6}
                  style={{
                    width: "100%", fontSize: 13, lineHeight: 1.6,
                    padding: "10px 12px", borderRadius: 10,
                    border: "1px solid rgba(62,92,118,0.2)",
                    color: "#0d1321", background: "#f8fafc",
                    resize: "vertical", outline: "none",
                    boxSizing: "border-box",
                  }}
                />

                {/* Actions */}
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={handleSend}
                    disabled={sending}
                    style={{
                      flex: 1, padding: "10px", borderRadius: 10, border: "none",
                      background: sending ? "#e2e8f0" : "#16a34a",
                      color: sending ? "#94a3b8" : "#fff",
                      fontSize: 13, fontWeight: 600, cursor: sending ? "not-allowed" : "pointer",
                    }}
                  >
                    {sending ? "Envoi en cours..." : "Envoyer"}
                  </button>
                  <button
                    onClick={handleGenerateDraft}
                    disabled={generating}
                    style={{
                      padding: "10px 16px", borderRadius: 10,
                      border: "1px solid rgba(62,92,118,0.2)",
                      background: "#f8f9fa", color: "#3e5c76",
                      fontSize: 12, cursor: "pointer",
                    }}
                  >
                    Régénérer
                  </button>
                  <button
                    onClick={() => setDraft("")}
                    style={{
                      padding: "10px 16px", borderRadius: 10,
                      border: "1px solid rgba(239,68,68,0.2)",
                      background: "#fff5f5", color: "#ef4444",
                      fontSize: 12, cursor: "pointer",
                    }}
                  >
                    Annuler
                  </button>
                </div>
              </div>
            )}

            {/* Succès */}
            {sent && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderRadius: 10, background: "#f0fdf4", border: "1px solid #bbf7d0" }}>
                <span style={{ fontSize: 18 }}>✅</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#16a34a" }}>Email envoyé avec succès</div>
                  <div style={{ fontSize: 11, color: "#4ade80", marginTop: 2 }}>à {draftTo}</div>
                </div>
                <button
                  onClick={() => setSent(false)}
                  style={{ marginLeft: "auto", background: "none", border: "none", fontSize: 11, color: "#16a34a", cursor: "pointer", textDecoration: "underline" }}
                >
                  Répondre à nouveau
                </button>
              </div>
            )}

            {/* Erreur */}
            {error && (
              <div style={{ marginTop: 8, padding: "10px 14px", borderRadius: 8, background: "#fff5f5", border: "1px solid #fecaca", fontSize: 12, color: "#ef4444" }}>
                {error}
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
