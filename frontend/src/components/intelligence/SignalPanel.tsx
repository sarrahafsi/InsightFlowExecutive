"use client";
import { useState, useEffect } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface BusinessLabel {
  label: string; count: number; pct: number; color: string; icon: string; desc: string;
}
interface Emotion {
  label: string; count: number; pct: number; color: string; icon: string;
}
interface Intelligence {
  business_labels: BusinessLabel[];
  emotions:        Emotion[];
  topics:          { label: string; count: number }[];
  risk_count:      number;
  risk_rate:       number;
  climate:         string;
  climate_label:   string;
  climate_color:   string;
  nlp_coverage:    number;
}
interface Message {
  id: string; title: string; author: string; source: string;
  timestamp: string; business_label: string; emotion_label: string;
  sentiment: string; content: string; url: string; tags: string[];
}

const BUSINESS_LABELS: Record<string, Record<string, { label: string; action: string; color: string; icon: string }>> = {
  fr: {
    Urgent:           { label: "Urgences",      action: "nécessitent votre attention immédiate", color: "#ef4444", icon: "🚨" },
    Blocked:          { label: "Blocages",       action: "bloquent les équipes",                  color: "#f97316", icon: "🛑" },
    Risk:             { label: "Risques",        action: "à surveiller de près",                  color: "#f59e0b", icon: "⚠️"  },
    Conflict:         { label: "Conflits",       action: "détectés dans les échanges",            color: "#8b5cf6", icon: "⚡" },
    Overload:         { label: "Surcharges",     action: "signaux de surcharge identifiés",       color: "#ec4899", icon: "📈" },
    Concern:          { label: "Préoccupations", action: "méritent un suivi",                     color: "#eab308", icon: "🔶" },
    Progress:         { label: "Avancées",       action: "progressent bien",                      color: "#22c55e", icon: "✅" },
    "Neutral Update": { label: "Mises à jour",  action: "informatives, sans action requise",     color: "#94a3b8", icon: "ℹ️"  },
  },
  en: {
    Urgent:           { label: "Urgencies",   action: "need your immediate attention",  color: "#ef4444", icon: "🚨" },
    Blocked:          { label: "Blockers",    action: "blocking the teams",             color: "#f97316", icon: "🛑" },
    Risk:             { label: "Risks",       action: "to watch closely",               color: "#f59e0b", icon: "⚠️"  },
    Conflict:         { label: "Conflicts",   action: "detected in exchanges",          color: "#8b5cf6", icon: "⚡" },
    Overload:         { label: "Overloads",   action: "overload signals identified",    color: "#ec4899", icon: "📈" },
    Concern:          { label: "Concerns",    action: "worth following up",             color: "#eab308", icon: "🔶" },
    Progress:         { label: "Progress",    action: "going well",                     color: "#22c55e", icon: "✅" },
    "Neutral Update": { label: "Updates",     action: "informative, no action needed",  color: "#94a3b8", icon: "ℹ️"  },
  },
};

const EMOTION_LABELS: Record<string, Record<string, { label: string; color: string; icon: string }>> = {
  fr: {
    frustration:  { label: "Frustration",  color: "#ef4444", icon: "😤" },
    urgency:      { label: "Urgence",      color: "#f97316", icon: "⚡" },
    concern:      { label: "Inquiétude",   color: "#eab308", icon: "😟" },
    satisfaction: { label: "Satisfaction", color: "#22c55e", icon: "😊" },
    neutral:      { label: "Neutralité",   color: "#94a3b8", icon: "😐" },
  },
  en: {
    frustration:  { label: "Frustration",  color: "#ef4444", icon: "😤" },
    urgency:      { label: "Urgency",      color: "#f97316", icon: "⚡" },
    concern:      { label: "Concern",      color: "#eab308", icon: "😟" },
    satisfaction: { label: "Satisfaction", color: "#22c55e", icon: "😊" },
    neutral:      { label: "Neutral",      color: "#94a3b8", icon: "😐" },
  },
};

const SOURCE_ICON: Record<string, string> = {
  gmail: "📧", outlook: "📨", teams: "💬", slack: "💼", jira: "🎫", clickup: "✅",
};

const CLIMATE_CONFIG: Record<string, { label: string; color: string; icon: string; bg: string }> = {
  critical: { label: "Critique", color: "#ef4444", icon: "🔴", bg: "#fef2f2" },
  tense:    { label: "Tendu",    color: "#f97316", icon: "🟠", bg: "#fff7ed" },
  moderate: { label: "Modéré",   color: "#f59e0b", icon: "🟡", bg: "#fefce8" },
  healthy:  { label: "Sain",     color: "#22c55e", icon: "🟢", bg: "#f0fdf4" },
};

function generateInsight(data: Intelligence): string {
  const urgent      = data.business_labels?.find(b => b.label === "Urgent");
  const blocked     = data.business_labels?.find(b => b.label === "Blocked");
  const risk        = data.business_labels?.find(b => b.label === "Risk");
  const concern_bl  = data.business_labels?.find(b => b.label === "Concern");
  const frustration = data.emotions?.find(e => e.label === "frustration");
  const urgency_em  = data.emotions?.find(e => e.label === "urgency");
  const concern_em  = data.emotions?.find(e => e.label === "concern");
  const satisfaction = data.emotions?.find(e => e.label === "satisfaction");
  const parts: string[] = [];
  if (urgent?.count)                         parts.push(`${urgent.count} sujet${urgent.count > 1 ? "s" : ""} urgent${urgent.count > 1 ? "s" : ""}`);
  if (blocked?.count)                        parts.push(`${blocked.count} blocage${blocked.count > 1 ? "s" : ""}`);
  if (risk?.count)                           parts.push(`${risk.count} risque${risk.count > 1 ? "s" : ""}`);
  if (concern_bl && concern_bl.count > 0)    parts.push(`${concern_bl.count} préoccupation${concern_bl.count > 1 ? "s" : ""}`);
  if (frustration && frustration.pct > 15)   parts.push(`frustration détectée (${frustration.pct}%)`);
  if (urgency_em && urgency_em.pct > 10)     parts.push(`signaux d'urgence (${urgency_em.pct}%)`);
  if (concern_em && concern_em.pct > 20)     parts.push(`inquiétude dominante (${concern_em.pct}%)`);
  if (satisfaction && satisfaction.pct > 50) parts.push(`${satisfaction.pct}% de satisfaction`);
  if (parts.length === 0) return "Aucun signal critique détecté — situation globalement sous contrôle.";
  return `Détecté : ${parts.join(", ")}.`;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/* ── Drawer ──────────────────────────────────────────────────────────── */
function MessageDrawer({
  open, onClose, title, color, icon, messages, loading, ui,
}: {
  open: boolean; onClose: () => void;
  title: string; color: string; icon: string;
  messages: Message[]; loading: boolean;
  ui: { loading: string; no_messages: string; message: string; unknown: string; no_subject: string };
}) {
  const { locale } = useI18n();
  const BUSINESS_FR = BUSINESS_LABELS[locale] ?? BUSINESS_LABELS.fr;
  const EMOTION_FR  = EMOTION_LABELS[locale]  ?? EMOTION_LABELS.fr;

  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [onClose]);

  if (!open) return null;

  return (
    <>
      {/* Overlay */}
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(13,19,33,0.35)",
        zIndex: 1000, backdropFilter: "blur(2px)",
      }} />

      {/* Drawer */}
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0,
        width: "min(480px, 95vw)",
        background: "#fff",
        boxShadow: "-8px 0 40px rgba(13,19,33,0.15)",
        zIndex: 1001,
        display: "flex", flexDirection: "column",
        animation: "slideIn 0.25s ease",
      }}>
        <style>{`@keyframes slideIn{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>

        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "1.25rem 1.5rem",
          borderBottom: "1px solid rgba(62,92,118,0.1)",
          background: `${color}0a`,
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 22 }}>{icon}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#0d1321" }}>{title}</div>
            <div style={{ fontSize: 12, color: "#748cab" }}>
              {loading ? ui.loading : `${messages.length} ${ui.message}${messages.length > 1 ? "s" : ""}`}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            fontSize: 20, color: "#748cab", padding: "4px 8px", borderRadius: 8,
            lineHeight: 1,
          }}>✕</button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1rem 1.5rem" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
              {ui.loading}
            </div>
          ) : messages.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
              {ui.no_messages}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {messages.map(msg => {
                const bizMeta  = BUSINESS_FR[msg.business_label];
                const emoMeta  = EMOTION_FR[msg.emotion_label];
                const srcIcon  = SOURCE_ICON[msg.source] ?? "📄";
                return (
                  <div key={msg.id} style={{
                    background: "#f8fafc",
                    border: "1px solid rgba(62,92,118,0.1)",
                    borderRadius: 12,
                    padding: "14px 16px",
                    cursor: msg.url ? "pointer" : "default",
                    transition: "box-shadow 0.15s",
                  }}
                    onClick={() => msg.url && window.open(msg.url, "_blank")}
                    onMouseEnter={e => { if (msg.url) (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 16px rgba(13,19,33,0.1)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
                  >
                    {/* Row 1: source + author + date */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span style={{ fontSize: 14 }}>{srcIcon}</span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {msg.author || ui.unknown}
                      </span>
                      <span style={{ fontSize: 11, color: "#94a3b8", flexShrink: 0 }}>
                        {formatDate(msg.timestamp)}
                      </span>
                    </div>

                    {/* Row 2: title */}
                    <div style={{ fontSize: 13, color: "#1d2d44", fontWeight: 500, marginBottom: 6, lineHeight: 1.4 }}>
                      {msg.title || ui.no_subject}
                    </div>

                    {/* Row 3: content preview */}
                    {msg.content && (
                      <div style={{
                        fontSize: 12, color: "#748cab", lineHeight: 1.6,
                        marginBottom: 8, overflow: "hidden",
                        display: "-webkit-box", WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical" as const,
                      }}>
                        {msg.content}
                      </div>
                    )}

                    {/* Row 4: badges */}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {bizMeta && (
                        <span style={{
                          fontSize: 11, fontWeight: 600,
                          color: bizMeta.color,
                          background: `${bizMeta.color}15`,
                          borderRadius: 6, padding: "2px 8px",
                        }}>
                          {bizMeta.icon} {bizMeta.label}
                        </span>
                      )}
                      {emoMeta && (
                        <span style={{
                          fontSize: 11, fontWeight: 600,
                          color: emoMeta.color,
                          background: `${emoMeta.color}15`,
                          borderRadius: 6, padding: "2px 8px",
                        }}>
                          {emoMeta.icon} {emoMeta.label}
                        </span>
                      )}
                      {msg.sentiment && (
                        <span style={{
                          fontSize: 11, color: "#748cab",
                          background: "rgba(116,140,171,0.1)",
                          borderRadius: 6, padding: "2px 8px",
                        }}>
                          {msg.sentiment === "POSITIVE" ? "😊" : msg.sentiment === "NEGATIVE" ? "😞" : "😐"} {msg.sentiment.toLowerCase()}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN COMPONENT
═══════════════════════════════════════════════════════════ */
export default function SignalPanel({ data, sinceDays = 30 }: { data: Intelligence; sinceDays?: number }) {
  const { locale } = useI18n();
  const BUSINESS_FR = BUSINESS_LABELS[locale] ?? BUSINESS_LABELS.fr;
  const EMOTION_FR  = EMOTION_LABELS[locale]  ?? EMOTION_LABELS.fr;

  const climate = CLIMATE_CONFIG[data.climate] ?? CLIMATE_CONFIG.moderate;

  const UI = {
    title:         locale === "en" ? "Signal Dashboard"        : "Tableau de bord des signaux",
    subtitle:      locale === "en" ? "Communication Analysis"  : "Analyse de communication",
    attention:     locale === "en" ? "Focus areas"             : "Points d'attention",
    no_signal:     locale === "en" ? "No critical signal"      : "Aucun signal critique",
    tone:          locale === "en" ? "Communication tone"      : "Ton des communications",
    topics:        locale === "en" ? "Dominant topics"         : "Sujets dominants",
    no_emotion:    locale === "en" ? "No emotional data"       : "Aucune donnée émotionnelle",
    climate_label: locale === "en" ? `${climate.label} climate` : `Climat ${climate.label}`,
    loading:       locale === "en" ? "Loading messages…"       : "Chargement des messages…",
    no_messages:   locale === "en" ? "No messages found for this filter." : "Aucun message trouvé pour ce filtre.",
    message:       locale === "en" ? "message"                 : "message",
    unknown:       locale === "en" ? "Unknown"                 : "Inconnu",
    no_subject:    locale === "en" ? "(no subject)"            : "(sans objet)",
  };

  const [drawer, setDrawer] = useState<{ open: boolean; title: string; color: string; icon: string; businessLabel?: string; emotionLabel?: string }>({
    open: false, title: "", color: "#3e5c76", icon: "📧",
  });
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading]   = useState(false);

  // Close drawer and clear messages when the time filter changes
  useEffect(() => {
    setDrawer(d => ({ ...d, open: false }));
    setMessages([]);
  }, [sinceDays]);

  async function openDrawer(opts: { title: string; color: string; icon: string; businessLabel?: string; emotionLabel?: string }) {
    setDrawer({ open: true, ...opts });
    setLoading(true);
    setMessages([]);
    try {
      const params = new URLSearchParams({ since_days: String(sinceDays), limit: "50" });
      if (opts.businessLabel) params.set("business_label", opts.businessLabel);
      if (opts.emotionLabel)  params.set("emotion_label",  opts.emotionLabel);
      const res = await API.get(`/api/analytics/messages?${params}`);
      setMessages(res.data.items ?? []);
    } catch {
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }

  const actionable = (data.business_labels ?? []).filter(b =>
    ["Urgent", "Blocked", "Risk", "Conflict", "Overload", "Concern"].includes(b.label) && b.count > 0
  );
  const positive = (data.business_labels ?? []).filter(b =>
    ["Progress", "Neutral Update"].includes(b.label) && b.count > 0
  );
  const insight = generateInsight(data);

  return (
    <>
      <div style={{
        background: "#fff", borderRadius: 20, padding: "1.75rem 2rem",
        boxShadow: "0 2px 20px rgba(13,19,33,0.07)",
        border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem",
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.25rem", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>
              {UI.subtitle}
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif", margin: 0 }}>
              {UI.title}
            </h2>
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 16px", borderRadius: 20,
            background: climate.bg, border: `1px solid ${climate.color}40`,
          }}>
            <span style={{ fontSize: 16 }}>{climate.icon}</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: climate.color }}>{UI.climate_label}</span>
          </div>
        </div>

        {/* Insight */}
        <div style={{
          background: "rgba(62,92,118,0.05)", borderRadius: 12,
          padding: "10px 16px", fontSize: 13, color: "#3e5c76", fontWeight: 500,
          marginBottom: "1.75rem", borderLeft: "3px solid #3e5c76",
        }}>
          💡 {insight}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>

          {/* LEFT — Points d'attention */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", marginBottom: "1rem" }}>
              {UI.attention}
            </div>

            {actionable.length === 0 ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px", background: "#f0fdf4", borderRadius: 10 }}>
                <span style={{ fontSize: 16 }}>✅</span>
                <span style={{ fontSize: 13, color: "#16a34a", fontWeight: 500 }}>{UI.no_signal}</span>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {actionable.map(b => {
                  const meta = BUSINESS_FR[b.label] ?? { label: b.label, action: "", color: b.color, icon: b.icon };
                  return (
                    <div key={b.label}
                      onClick={() => openDrawer({ title: `${meta.icon} ${b.count} ${meta.label}`, color: meta.color, icon: meta.icon, businessLabel: b.label })}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "10px 14px",
                        background: `${meta.color}0d`,
                        borderRadius: 10,
                        borderLeft: `3px solid ${meta.color}`,
                        cursor: "pointer",
                        transition: "transform 0.15s, box-shadow 0.15s",
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = "translateX(3px)"; (e.currentTarget as HTMLElement).style.boxShadow = `2px 4px 12px ${meta.color}25`; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = "translateX(0)"; (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
                    >
                      <span style={{ fontSize: 16, flexShrink: 0 }}>{meta.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>{b.count} {meta.label}</div>
                        <div style={{ fontSize: 11, color: "#748cab" }}>{meta.action}</div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: meta.color, background: `${meta.color}18`, borderRadius: 6, padding: "2px 8px" }}>
                          {b.pct}%
                        </span>
                        <span style={{ fontSize: 12, color: "#748cab" }}>›</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {positive.length > 0 && (
              <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                {positive.map(b => {
                  const meta = BUSINESS_FR[b.label] ?? { label: b.label, action: "", color: b.color, icon: b.icon };
                  return (
                    <div key={b.label}
                      onClick={() => openDrawer({ title: `${meta.icon} ${b.count} ${meta.label}`, color: meta.color, icon: meta.icon, businessLabel: b.label })}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "8px 12px", background: "#f8fafc", borderRadius: 8,
                        cursor: "pointer", transition: "background 0.15s",
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#f0fdf4"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "#f8fafc"; }}
                    >
                      <span style={{ fontSize: 14 }}>{meta.icon}</span>
                      <span style={{ fontSize: 12, color: "#748cab", flex: 1 }}>{b.count} {meta.label}</span>
                      <span style={{ fontSize: 11, color: "#94a3b8" }}>{b.pct}%</span>
                      <span style={{ fontSize: 12, color: "#748cab" }}>›</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* RIGHT — Ton des communications */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", marginBottom: "1rem" }}>
              {UI.tone}
            </div>

            {(data.emotions ?? []).length === 0 ? (
              <p style={{ color: "#748cab", fontSize: 13 }}>{UI.no_emotion}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {data.emotions.filter(e => e.count > 0).sort((a, b) => b.pct - a.pct).map(e => {
                  const meta   = EMOTION_FR[e.label] ?? { label: e.label, color: e.color, icon: e.icon };
                  const maxPct = Math.max(...data.emotions.map(x => x.pct), 1);
                  return (
                    <div key={e.label}
                      onClick={() => openDrawer({ title: `${meta.icon} ${meta.label}`, color: meta.color, icon: meta.icon, emotionLabel: e.label })}
                      style={{ cursor: "pointer", borderRadius: 8, padding: "6px 8px", transition: "background 0.15s" }}
                      onMouseEnter={e2 => { (e2.currentTarget as HTMLElement).style.background = "rgba(62,92,118,0.05)"; }}
                      onMouseLeave={e2 => { (e2.currentTarget as HTMLElement).style.background = "transparent"; }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 15, width: 22, textAlign: "center" }}>{meta.icon}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", width: 90, flexShrink: 0 }}>{meta.label}</span>
                        <div style={{ flex: 1, height: 6, background: "rgba(0,0,0,0.06)", borderRadius: 4, overflow: "hidden" }}>
                          <div style={{ width: `${(e.pct / maxPct) * 100}%`, height: "100%", background: meta.color, borderRadius: 4, transition: "width 0.6s ease" }} />
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 700, color: meta.color, width: 34, textAlign: "right", flexShrink: 0 }}>{e.pct}%</span>
                        <span style={{ fontSize: 12, color: "#748cab" }}>›</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Topics */}
            {(data.topics ?? []).length > 0 && (
              <div style={{ marginTop: "1.5rem" }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab", marginBottom: 10 }}>
                  {UI.topics}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {data.topics.map((t, i) => (
                    <span key={i} style={{
                      padding: "4px 12px", borderRadius: 20,
                      background: `rgba(62,92,118,${0.07 + (1 - i / data.topics.length) * 0.1})`,
                      color: "#3e5c76", fontSize: 12, fontWeight: 500,
                    }}>
                      {t.label}<span style={{ color: "#748cab", fontSize: 11, marginLeft: 4 }}>{t.count}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <MessageDrawer
        open={drawer.open}
        onClose={() => setDrawer(d => ({ ...d, open: false }))}
        title={drawer.title}
        color={drawer.color}
        icon={drawer.icon}
        messages={messages}
        loading={loading}
        ui={UI}
      />
    </>
  );
}
