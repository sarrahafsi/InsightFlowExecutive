"use client";
import { useEffect, useState } from "react";
import API, { isUpgradeRequired } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface SourceItem {
  id: string; source: string; title: string; url: string; author?: string;
  to_email?: string; thread_id?: string | null;
  channel_id?: string | null; channel_name?: string | null;
  user_id?: string | null; thread_ts?: string | null;
}

interface DailyInsight {
  id: string;
  type: string;
  title: string;
  what_happened: string;
  why_it_matters: string;
  evidence: string[];
  impact: string;
  recommendation: string;
  source_items: SourceItem[];
  actions: string[];
}

type Contact =
  | { kind: "gmail"; email: string; thread_id: string | null; label: string }
  | { kind: "slack_channel"; channel_id: string; thread_ts: string | null; label: string }
  | { kind: "slack_dm"; user_id: string; label: string };

const ACTION_LABEL: Record<string, { fr: string; en: string }> = {
  create_meeting:   { fr: "Créer une réunion",      en: "Create a meeting" },
  send_message:     { fr: "Envoyer un message",     en: "Send a message" },
  create_task:      { fr: "Créer une tâche",        en: "Create a task" },
  ignore:           { fr: "Ignorer",                en: "Ignore" },
  remind_tomorrow:  { fr: "Me le rappeler demain",  en: "Remind me tomorrow" },
};

const TYPE_LABEL: Record<string, { fr: string; en: string; color: string }> = {
  risk_cluster:      { fr: "Risque détecté",     en: "Risk detected",       color: "#ef4444" },
  sentiment_decline: { fr: "Sentiment en baisse", en: "Sentiment declining", color: "#f59e0b" },
  stale_critical:    { fr: "Réponse en attente",  en: "Awaiting response",   color: "#f97316" },
};

function headline(fr: boolean, count: number): string {
  if (fr) {
    if (count === 0) return "Bonjour. Rien ne nécessite votre attention aujourd'hui.";
    return "Bonjour. Voici ce qui nécessite votre attention aujourd'hui.";
  }
  if (count === 0) return "Good morning. Nothing needs your attention today.";
  if (count === 1) return "Good morning. Here's the one thing that needs your attention today.";
  return `Good morning. Here are the ${count} things that need your attention today.`;
}

/**
 * Détermine où "Envoyer un message" doit partir :
 * 1. Gmail — répondre à l'expéditeur (dans le même thread si connu).
 * 2. Slack, insight ciblé sur UN message (stale_critical) — répondre en thread
 *    si on en a un, sinon DM à l'auteur.
 * 3. Slack, insight multi-messages (risk_cluster) — poster dans le canal
 *    d'origine (pas de destinataire unique, visible par l'équipe).
 */
function resolveContact(ins: DailyInsight): Contact | null {
  const gmail = ins.source_items.find(si => si.source === "gmail" && si.to_email);
  if (gmail) return { kind: "gmail", email: gmail.to_email!, thread_id: gmail.thread_id ?? null, label: gmail.to_email! };

  if (ins.type === "stale_critical") {
    const item = ins.source_items.find(si => si.source === "slack");
    if (item?.channel_id && item.thread_ts) {
      return { kind: "slack_channel", channel_id: item.channel_id, thread_ts: item.thread_ts, label: `#${item.channel_name || item.channel_id} (en thread)` };
    }
    if (item?.user_id) {
      return { kind: "slack_dm", user_id: item.user_id, label: item.author ? `DM à ${item.author}` : "DM Slack" };
    }
  }

  const channelItem = ins.source_items.find(si => si.source === "slack" && si.channel_id);
  if (channelItem) {
    return { kind: "slack_channel", channel_id: channelItem.channel_id!, thread_ts: null, label: `#${channelItem.channel_name || channelItem.channel_id}` };
  }

  return null;
}

function calendarUrl(ins: DailyInsight): string {
  const start = new Date();
  start.setDate(start.getDate() + 1);
  start.setHours(9, 0, 0, 0);
  const end = new Date(start.getTime() + 30 * 60000);
  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  const params = new URLSearchParams({
    action:  "TEMPLATE",
    text:    ins.title,
    details: `${ins.why_it_matters}\n\n${ins.recommendation ? "Recommandation : " + ins.recommendation : ""}`,
    dates:   `${fmt(start)}/${fmt(end)}`,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

export default function DailyBrief() {
  const { locale } = useI18n();
  const fr = locale !== "en";

  const [insights, setInsights]   = useState<DailyInsight[] | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [locked, setLocked]       = useState(false);
  const [toast, setToast]         = useState<string | null>(null);
  const [busy, setBusy]           = useState<string | null>(null);
  const [composeFor, setComposeFor] = useState<string | null>(null);
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody]       = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null); setLocked(false);
    API.get(`/api/brief/daily?lang=${locale}`)
      .then(r => { if (!cancelled) setInsights(r.data.insights ?? []); })
      .catch(e => {
        if (cancelled) return;
        if (isUpgradeRequired(e)) setLocked(true);
        else setError(e.message);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [locale]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const dismiss = (insightId: string) => setDismissed(prev => new Set([...prev, insightId]));

  const openComposer = (ins: DailyInsight, contact: Contact) => {
    setComposeFor(ins.id);
    setComposeSubject(fr ? `Suivi : ${ins.title}` : `Follow-up: ${ins.title}`);
    setComposeBody(
      contact.kind === "gmail"
        ? (fr ? `Bonjour,\n\n${ins.why_it_matters}\n\n${ins.recommendation}\n\nCordialement,`
              : `Hello,\n\n${ins.why_it_matters}\n\n${ins.recommendation}\n\nBest,`)
        : `${ins.why_it_matters}${ins.recommendation ? "\n\n" + ins.recommendation : ""}`
    );
  };

  const sendComposedMessage = async (ins: DailyInsight, contact: Contact) => {
    setBusy(ins.id);
    try {
      if (contact.kind === "gmail") {
        const form = new FormData();
        form.append("to", contact.email);
        form.append("subject", composeSubject);
        form.append("body", composeBody);
        if (contact.thread_id) form.append("thread_id", contact.thread_id);
        await API.post("/api/emails/send", form);
      } else if (contact.kind === "slack_channel") {
        await API.post("/auth/slack/send-message", {
          text: composeBody, channel_id: contact.channel_id, thread_ts: contact.thread_ts ?? undefined,
        });
      } else {
        await API.post("/auth/slack/send-message", { text: composeBody, user_id: contact.user_id });
      }
      showToast(fr ? "Message envoyé ✓" : "Message sent ✓");
      setComposeFor(null);
      dismiss(ins.id);
    } catch (e: any) {
      showToast(fr ? `Échec de l'envoi : ${e.message}` : `Failed to send: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };

  const createTask = async (ins: DailyInsight) => {
    setBusy(ins.id);
    try {
      const primary = ins.source_items[0];
      await API.post("/api/actions", {
        message_id:     primary?.id,
        title:           ins.title,
        author:          primary?.author,
        source:          primary?.source,
        business_label:  ins.type === "risk_cluster" ? "Risk" : ins.type === "stale_critical" ? "Urgent" : undefined,
      });
      showToast(fr ? "Tâche créée ✓ — visible dans Décisions/Actions." : "Task created ✓ — visible under Decisions/Actions.");
      dismiss(ins.id);
    } catch (e: any) {
      showToast(fr ? `Échec de la création : ${e.message}` : `Failed to create task: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleAction = (ins: DailyInsight, action: string) => {
    if (action === "ignore" || action === "remind_tomorrow") {
      dismiss(ins.id);
      return;
    }
    if (action === "create_task") {
      createTask(ins);
      return;
    }
    if (action === "create_meeting") {
      window.open(calendarUrl(ins), "_blank", "noopener,noreferrer");
      return;
    }
    if (action === "send_message") {
      const contact = resolveContact(ins);
      if (!contact) {
        showToast(fr
          ? "Aucun destinataire identifié pour cet insight — action indisponible."
          : "No recipient identified for this insight — action unavailable.");
        return;
      }
      openComposer(ins, contact);
    }
  };

  const CARD_BG     = "#ffffff";
  const CARD_BORDER = "1px solid rgba(62,92,118,0.14)";
  const CARD_SHADOW = "0 2px 10px rgba(13,19,33,0.05)";

  if (locked || loading || error) {
    return (
      <div style={{ background: CARD_BG, border: CARD_BORDER, boxShadow: CARD_SHADOW, borderRadius: 20, padding: "1.5rem 2rem", marginBottom: "1.5rem" }}>
        <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 6, fontWeight: 700 }}>
          Daily Brief
        </div>
        {loading && <p style={{ fontSize: 13, color: "#748cab" }}>{fr ? "Analyse en cours…" : "Analyzing…"}</p>}
        {locked && (
          <div style={{ marginTop: 8, padding: "10px 14px", background: "rgba(147,51,234,0.08)", border: "1px solid rgba(147,51,234,0.25)", borderRadius: 10, fontSize: 12, color: "#6b21a8" }}>
            🔒 {fr ? "Le Daily Brief est une fonctionnalité Pro — passez à un plan supérieur pour le débloquer." : "The Daily Brief is a Pro feature — upgrade your plan to unlock it."}
          </div>
        )}
        {error && !locked && (
          <div style={{ marginTop: 8, padding: "10px 14px", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 10, fontSize: 12, color: "#b91c1c" }}>
            {error}
          </div>
        )}
      </div>
    );
  }

  const visible = (insights ?? []).filter(i => !dismissed.has(i.id));

  return (
    <div style={{ background: CARD_BG, border: CARD_BORDER, boxShadow: CARD_SHADOW, borderRadius: 20, padding: "1.75rem 2rem", marginBottom: "1.5rem" }}>
      <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 6, fontWeight: 700 }}>
        Daily Brief
      </div>
      <h2 style={{ fontSize: 19, fontFamily: "DM Serif Display, serif", color: "#0d1321", marginBottom: visible.length ? 18 : 0 }}>
        {headline(fr, visible.length)}
      </h2>

      {visible.length === 0 && (
        <p style={{ fontSize: 13, color: "#748cab" }}>
          {fr ? "Tout est sous contrôle." : "Everything's under control."}
        </p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {visible.map(ins => {
          const type = TYPE_LABEL[ins.type] ?? { fr: "Signal", en: "Signal", color: "#94a3b8" };
          const isComposing = composeFor === ins.id;
          const isBusy = busy === ins.id;
          const contact = isComposing ? resolveContact(ins) : null;

          return (
            <div key={ins.id} style={{ background: "#f8f7f3", borderRadius: 14, padding: "1.25rem 1.5rem", border: "1px solid rgba(62,92,118,0.12)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: type.color, background: `${type.color}18`, borderRadius: 6, padding: "2px 8px" }}>
                  {fr ? type.fr : type.en}
                </span>
              </div>

              <p style={{ fontSize: 15, fontWeight: 600, color: "#0d1321", marginBottom: 10, lineHeight: 1.5 }}>
                {ins.what_happened}
              </p>

              <div style={{ fontSize: 12, color: "#748cab", fontWeight: 700, marginBottom: 4 }}>
                {fr ? "Pourquoi ?" : "Why?"}
              </div>
              <p style={{ fontSize: 13, lineHeight: 1.7, color: "#3e5c76", marginBottom: 10 }}>
                {ins.why_it_matters}
              </p>

              {ins.evidence.length > 0 && (
                <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 12, color: "#748cab", lineHeight: 1.8 }}>
                  {ins.evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}

              {ins.impact && (
                <p style={{ fontSize: 12, marginBottom: 8 }}>
                  <span style={{ color: "#748cab", fontWeight: 700 }}>{fr ? "Impact possible : " : "Possible impact: "}</span>
                  <span style={{ color: "#3e5c76" }}>{ins.impact}</span>
                </p>
              )}

              {ins.recommendation && (
                <p style={{ fontSize: 12, marginBottom: 14 }}>
                  <span style={{ color: "#748cab", fontWeight: 700 }}>{fr ? "Recommandation : " : "Recommendation: "}</span>
                  <span style={{ color: "#3e5c76" }}>{ins.recommendation}</span>
                </p>
              )}

              {isComposing && contact ? (
                <div style={{ background: "#fff", border: "1px solid rgba(62,92,118,0.2)", borderRadius: 10, padding: "0.9rem 1rem", marginTop: 4 }}>
                  <div style={{ fontSize: 11, color: "#748cab", marginBottom: 8 }}>
                    {fr ? "À : " : "To: "}<strong>{contact.label}</strong>
                  </div>
                  {contact.kind === "gmail" && (
                    <input
                      value={composeSubject}
                      onChange={e => setComposeSubject(e.target.value)}
                      style={{ width: "100%", boxSizing: "border-box", padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)", fontSize: 12.5, marginBottom: 8 }}
                    />
                  )}
                  <textarea
                    value={composeBody}
                    onChange={e => setComposeBody(e.target.value)}
                    rows={5}
                    style={{ width: "100%", boxSizing: "border-box", padding: "8px 10px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)", fontSize: 12.5, fontFamily: "inherit", resize: "vertical", marginBottom: 8 }}
                  />
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={() => sendComposedMessage(ins, contact)}
                      disabled={isBusy}
                      style={{ padding: "6px 13px", borderRadius: 10, cursor: isBusy ? "not-allowed" : "pointer", border: "1px solid #1d2d44", background: "#1d2d44", color: "#f0ebd8", fontSize: 11.5, fontWeight: 600 }}
                    >
                      {isBusy ? (fr ? "Envoi…" : "Sending…") : (fr ? "Envoyer" : "Send")}
                    </button>
                    <button
                      onClick={() => setComposeFor(null)}
                      disabled={isBusy}
                      style={{ padding: "6px 13px", borderRadius: 10, cursor: "pointer", border: "1px solid rgba(62,92,118,0.25)", background: "transparent", color: "#3e5c76", fontSize: 11.5, fontWeight: 600 }}
                    >
                      {fr ? "Annuler" : "Cancel"}
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {ins.actions.map(action => {
                    const meta = ACTION_LABEL[action];
                    if (!meta) return null;
                    return (
                      <button
                        key={action}
                        onClick={() => handleAction(ins, action)}
                        disabled={isBusy}
                        style={{
                          padding: "6px 13px", borderRadius: 10, cursor: isBusy ? "not-allowed" : "pointer",
                          border: "1px solid rgba(62,92,118,0.25)",
                          background: action === "ignore" ? "transparent" : "rgba(62,92,118,0.07)",
                          color: "#3e5c76", fontSize: 11.5, fontWeight: 600,
                        }}
                      >
                        {isBusy && action === "create_task" ? (fr ? "Création…" : "Creating…") : (fr ? meta.fr : meta.en)}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {toast && (
        <div style={{ marginTop: 14, padding: "8px 14px", background: "rgba(62,92,118,0.08)", border: "1px solid rgba(62,92,118,0.15)", borderRadius: 10, fontSize: 12, color: "#3e5c76" }}>
          {toast}
        </div>
      )}
    </div>
  );
}
