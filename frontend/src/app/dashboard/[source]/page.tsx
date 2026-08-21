"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import API from "@/lib/api";
import KPICard from "@/components/KPICard";
import BarChart from "@/components/charts/BarChart";
import DonutChart from "@/components/charts/DonutChart";
import LineChart from "@/components/charts/LineChart";
import SignalPanel from "@/components/intelligence/SignalPanel";
import RiskFeed from "@/components/intelligence/RiskFeed";
import BurnoutCard from "@/components/intelligence/BurnoutCard";
import PriorityInbox from "@/components/PriorityInbox";
import ActionItems from "@/components/ActionItems";
import DecisionLog from "@/components/DecisionLog";
import SearchBar from "@/components/SearchBar";
import AlertToast from "@/components/AlertToast";
import MessageDetailModal from "@/components/MessageDetailModal";

const SOURCE_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  gmail:    { label: "Gmail",    icon: "✉",  color: "#EA4335" },
  slack:    { label: "Slack",    icon: "#",  color: "#4A154B" },
  jira:     { label: "Jira",     icon: "J",  color: "#0052CC" },
  clickup:  { label: "ClickUp",  icon: "⬆", color: "#7B68EE" },
  onedrive: { label: "OneDrive", icon: "☁", color: "#0078D4" },
  teams:    { label: "Teams",    icon: "💬", color: "#6264A7" },
  outlook:  { label: "Outlook",  icon: "📨", color: "#0078D4" },
};

const LABEL_COLORS: Record<string, string> = {
  IMPORTANT: "#f59e0b", STARRED: "#3b82f6", SENT: "#22c55e",
  SPAM: "#ef4444", DRAFT: "#94a3b8", PERSONAL: "#8b5cf6",
};

const PERIOD_OPTIONS = [
  { days: 1,  label: "Aujourd'hui" },
  { days: 7,  label: "7 jours" },
  { days: 30, label: "30 jours" },
  { days: 90, label: "90 jours" },
];

const TABS = [
  { id: "overview",  label: "Vue d'ensemble",   icon: "◈" },
  { id: "alerts",    label: "Alertes & Risques", icon: "🚨" },
  { id: "decisions", label: "Décisions",         icon: "✅" },
  { id: "team",      label: "Équipe & Système",  icon: "🧠" },
] as const;

type TabId = typeof TABS[number]["id"];

/* ── Shared visual components ──────────────────────────────── */

function CanvasSectionHeader({ icon, label, badge }: { icon: string; label: string; badge?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "1rem" }}>
      <span style={{ fontSize: 13, color: "#748cab" }}>{icon}</span>
      <span style={{ fontSize: 11, color: "#3e5c76", textTransform: "uppercase", letterSpacing: "0.15em", fontWeight: 700 }}>
        {label}
      </span>
      {badge && (
        <span style={{ fontSize: 10, color: "#fff", background: "#3e5c76", borderRadius: 8, padding: "2px 8px", fontWeight: 600 }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function CanvasDivider() {
  return (
    <div style={{
      height: 1,
      background: "linear-gradient(90deg, transparent, rgba(62,92,118,0.18), transparent)",
      margin: "1.75rem 0 1.5rem",
    }} />
  );
}

function VisualCard({ title, sub, accent = "#748cab", children }: {
  title: string; sub?: string; accent?: string; children: React.ReactNode;
}) {
  return (
    <div style={{
      background: "var(--bg-card)", borderRadius: 14, padding: "1.25rem",
      boxShadow: "0 2px 10px var(--shadow-card)",
      border: "1px solid var(--border)",
      position: "relative", overflow: "hidden",
      transition: "background 0.25s ease",
    }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg,${accent},${accent}44,transparent)` }} />
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: accent, textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>{title}</div>
        {sub && <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>{sub}</div>}
      </div>
      {children}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p style={{ color: "var(--text-secondary)", fontSize: 13, paddingTop: 44, textAlign: "center" }}>{text}</p>;
}

/* ── Main page ─────────────────────────────────────────────── */

export default function SourceDashboard() {
  const { source } = useParams<{ source: string }>();
  const config = SOURCE_CONFIG[source] ?? { label: source, icon: "◈", color: "#748cab" };

  const [sinceDays, setSinceDays]       = useState(1);
  const [activeTab, setActiveTab]       = useState<TabId>("overview");
  const [hoveredTab, setHoveredTab]     = useState<TabId | null>(null);
  const [data, setData]                 = useState<any>(null);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState<string | null>(null);
  const [expandedThread, setExpanded]   = useState<number | null>(null);
  const [threadDetail, setThreadDetail] = useState<any | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    API.get(`/api/analytics/${source}?since_days=${sinceDays}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  }, [source, sinceDays]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: 36, height: 36, border: `3px solid ${config.color}33`, borderTop: `3px solid ${config.color}`, borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        <p style={{ color: "#748cab", fontSize: 13 }}>Analyse {config.label}...</p>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ background: "#fef2f2", border: "1px solid #ef4444", borderRadius: 12, padding: "1.5rem", color: "#ef4444" }}>
      <strong>Erreur :</strong> {error}
    </div>
  );
  if (!data) return null;

  const intel      = data.intelligence ?? {};
  const isGmail    = source === "gmail" && !!data.threads;
  const isOutlook  = source === "outlook";
  const alertCount = (intel.at_risk_items?.length ?? 0) + (data.critical_alerts ?? 0);

  const senderSlices = isGmail
    ? data.top_senders?.slice(0, 5).map((s: any, i: number) => ({
        label: s.name.split(" ")[0], value: s.count,
        color: ["#EA4335","#3e5c76","#f59e0b","#22c55e","#8b5cf6"][i],
      }))
    : data.top_authors?.slice(0, 5).map((a: any, i: number) => ({
        label: (a.name || "?").split(" ")[0], value: a.count,
        color: [config.color,"#3e5c76","#f59e0b","#22c55e","#748cab"][i],
      }));

  const labelSlices = isGmail
    ? data.label_distribution?.map((l: any) => ({
        label: l.label, value: l.count,
        color: LABEL_COLORS[l.label] ?? "#748cab",
      }))
    : null;

  const sentimentSlices = [
    { label: "Positif", value: data.sentiment.positive, color: "#22c55e" },
    { label: "Neutre",  value: data.sentiment.neutral,  color: "#94a3b8" },
    { label: "Négatif", value: data.sentiment.negative, color: "#ef4444" },
  ];

  const byDayData = data.by_day?.map((d: any) => ({ label: d.day, value: d.count })) ?? [];

  return (
    <div id="dashboard-print">
      <AlertToast />

      {/* ── Header ────────────────────────────────────────────── */}
      <div style={{ marginBottom: "1rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: config.color, marginBottom: 6, fontWeight: 700 }}>
            {config.icon} {config.label} · Analytics
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "var(--text-primary)", margin: 0 }}>
            Analyse {config.label}
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 4 }}>
            {data.volume.total} messages · Mis à jour {new Date(data.computed_at).toLocaleString("fr-FR")}
          </p>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {PERIOD_OPTIONS.map(({ days, label }) => (
            <button key={days} onClick={() => setSinceDays(days)} style={{
              padding: "5px 13px", borderRadius: 20, cursor: "pointer",
              border: `1px solid ${sinceDays === days ? config.color : "rgba(62,92,118,0.2)"}`,
              background: sinceDays === days ? config.color : "transparent",
              color: sinceDays === days ? "#fff" : "#748cab",
              fontSize: 12, fontWeight: sinceDays === days ? 600 : 400, whiteSpace: "nowrap",
            }}>{label}</button>
          ))}
          <button onClick={() => window.print()} style={{
            padding: "5px 13px", borderRadius: 20, cursor: "pointer",
            border: "1px solid rgba(62,92,118,0.3)", background: "transparent",
            color: "#748cab", fontSize: 12,
          }}>⬇ PDF</button>
        </div>
      </div>

      {/* ── Search ────────────────────────────────────────────── */}
      <div style={{ marginBottom: "1.25rem" }}>
        <SearchBar />
      </div>

      {/* ── Tabs ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 2, borderBottom: "2px solid rgba(62,92,118,0.12)", marginBottom: "1.75rem", overflowX: "auto" }}>
        {TABS.map(tab => {
          const isActive  = activeTab === tab.id;
          const showBadge = tab.id === "alerts" && alertCount > 0;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              onMouseEnter={() => setHoveredTab(tab.id)}
              onMouseLeave={() => setHoveredTab(null)}
              style={{
                display: "flex", alignItems: "center", gap: 7,
                padding: "10px 20px", border: "none", background: "none",
                cursor: "pointer", whiteSpace: "nowrap",
                fontSize: 13, fontWeight: isActive ? 600 : 400,
                color: isActive ? config.color : hoveredTab === tab.id ? config.color : "#748cab",
                borderBottom: isActive ? `2px solid ${config.color}` : hoveredTab === tab.id ? "2px solid rgba(62,92,118,0.35)" : "2px solid transparent",
                marginBottom: -2, transition: "all 0.15s",
              }}
            >
              <span>{tab.icon}</span>
              {tab.label}
              {showBadge && (
                <span style={{ background: "#ef4444", color: "#fff", fontSize: 10, fontWeight: 700, borderRadius: 20, padding: "1px 6px" }}>
                  {alertCount}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ══════════════════════════════════════════════════════════
          TAB 1 — Vue d'ensemble (BI Canvas)
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "overview" && (
        <div>

          {/* BI Canvas */}
          <div style={{
            background: "var(--bg-canvas)",
            borderRadius: 20, padding: "1.75rem",
            border: "1px solid rgba(62,92,118,0.1)",
            marginBottom: "1.5rem",
          }}>

            {/* Canvas title bar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.75rem", flexWrap: "wrap", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 4, height: 28, background: `linear-gradient(180deg,${config.color},${config.color}88)`, borderRadius: 4 }} />
                <div>
                  <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.2em", fontWeight: 700 }}>
                    Tableau de bord analytique · {config.label}
                  </div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: "var(--text-primary)", fontFamily: "DM Serif Display, serif" }}>
                    KPIs · Signaux · Graphiques
                  </div>
                </div>
              </div>
              <span style={{ fontSize: 10, color: "var(--text-secondary)", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, padding: "4px 10px" }}>
                Période : {sinceDays === 1 ? "Aujourd'hui" : `${sinceDays} derniers jours`}
              </span>
            </div>

            {/* ─ Section 1 : KPIs ─────────────────────────────── */}
            <CanvasSectionHeader icon="◈" label="Indicateurs Clés de Performance" />

            {/* KPIs communs à toutes les sources */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.875rem", marginBottom: "1.75rem" }}>

              {/* Volume & Activité */}
              <KPICard title={`${config.label} (sem.)`} value={data.volume.this_week} icon="📥"
                delta={data.volume.delta_pct} accent={config.color}
                subtitle={`Sem. passée : ${data.volume.last_week}`} />

              <KPICard title="Total analysés" value={data.volume.total} icon="📦"
                accent={config.color} subtitle={`Sur ${sinceDays} jour(s)`} />

              <KPICard title="Signaux de risque" value={intel.risk_count ?? 0} icon="⚠️"
                risk={(intel.risk_count ?? 0) > 5 ? "high" : (intel.risk_count ?? 0) > 2 ? "medium" : "low"}
                subtitle={`${intel.risk_rate ?? 0}% des messages`} />

              <KPICard title="Taux de risque" value={`${intel.risk_rate ?? 0}%`} icon="📊"
                accent={(intel.risk_rate ?? 0) > 30 ? "#ef4444" : (intel.risk_rate ?? 0) > 15 ? "#f59e0b" : "#22c55e"}
                subtitle="Des messages analysés" />

              <KPICard title="Sentiment positif" value={`${data.sentiment.positive}%`} icon="◉"
                accent="#22c55e" subtitle={`${data.sentiment.neutral}% neutre`} />

              <KPICard title="Sentiment négatif" value={`${data.sentiment.negative}%`} icon="📉"
                risk={data.sentiment.negative > 30 ? "high" : data.sentiment.negative > 15 ? "medium" : "low"}
                subtitle="Communications négatives" />

              <KPICard title="Couverture NLP" value={`${intel.nlp_coverage ?? 0}%`} icon="🧠"
                accent={(intel.nlp_coverage ?? 0) > 80 ? "#22c55e" : "#f59e0b"}
                subtitle={(intel.nlp_coverage ?? 0) > 80 ? "Analyse complète" : "Sync en cours"} />

              {/* Gmail KPIs */}
              {isGmail && <>
                <KPICard title="Non lus" value={data.unread.count} icon="🔴"
                  risk={data.unread.rate > 40 ? "high" : data.unread.rate > 20 ? "medium" : "low"}
                  subtitle={`${data.unread.rate}% du total`} />

                <KPICard title="Importants" value={data.important.count} icon="⭐"
                  accent="#f59e0b" subtitle={`${data.important.rate}% du total`} />

                <KPICard title="Tps réponse moy." icon="⚡"
                  value={data.avg_response_hours ? `${data.avg_response_hours}h` : "N/A"}
                  accent="#3e5c76"
                  subtitle={data.avg_response_hours ? "Basé sur les threads" : "Dossier envoyé requis"} />

                <KPICard title="Escalades" value={data.escalation.count} icon="🚨"
                  risk={data.escalation.count > 5 ? "high" : data.escalation.count > 2 ? "medium" : "low"}
                  subtitle="urgent · ASAP · critique" />

                <KPICard title="Sans réponse +48h" value={data.no_reply_48h.count} icon="⏰"
                  risk={data.no_reply_48h.count > 5 ? "high" : data.no_reply_48h.count > 2 ? "medium" : "low"}
                  subtitle="Importants non traités" />

                <KPICard title="Critiques sans réponse" value={data.unanswered_critical.count} icon="❗"
                  risk={data.unanswered_critical.count > 0 ? "high" : "low"}
                  subtitle="Escalade + pas de réponse" />

                <KPICard title="Threads longs" value={data.threads.long_count} icon="🔁"
                  risk={data.threads.long_count > 5 ? "medium" : "low"}
                  subtitle={`Moy. ${data.threads.avg_length} msg/thread`} />

                <KPICard title="Back-and-forth" value={`${data.threads.back_and_forth_score}/10`} icon="↔"
                  risk={data.threads.back_and_forth_score > 6 ? "high" : data.threads.back_and_forth_score > 3 ? "medium" : "low"}
                  subtitle="Intensité des échanges" />

                <KPICard title="Expéditeurs uniques" value={data.unique_senders} icon="👤"
                  accent="#3e5c76" subtitle="Sources distinctes" />
              </>}

              {/* Outlook KPIs */}
              {isOutlook && <>
                <KPICard title="Non lus" value={data.unread?.count ?? 0} icon="🔴"
                  risk={(data.unread?.rate ?? 0) > 40 ? "high" : (data.unread?.rate ?? 0) > 20 ? "medium" : "low"}
                  subtitle={`${data.unread?.rate ?? 0}% du total`} />

                <KPICard title="Haute importance" value={data.high_importance?.count ?? 0} icon="⭐"
                  accent="#f59e0b" subtitle={`${data.high_importance?.rate ?? 0}% du total`} />

                <KPICard title="Pièces jointes" value={data.attachments?.count ?? 0} icon="📎"
                  accent="#3e5c76" subtitle={`${data.attachments?.rate ?? 0}% du total`} />

                <KPICard title="Escalades" value={data.escalation?.count ?? 0} icon="🚨"
                  risk={(data.escalation?.count ?? 0) > 5 ? "high" : (data.escalation?.count ?? 0) > 2 ? "medium" : "low"}
                  subtitle="Urgence · ASAP · Critique" />

                <KPICard title="Expéditeurs uniques" value={data.unique_senders ?? 0} icon="👤"
                  accent="#3e5c76" subtitle="Sources distinctes" />
              </>}

              {/* Autres sources (Jira, Slack, etc.) */}
              {!isGmail && !isOutlook && (
                <KPICard title="Alertes escalade" value={data.critical_alerts} icon="🚨"
                  risk={data.critical_alerts > 5 ? "high" : data.critical_alerts > 2 ? "medium" : "low"}
                  subtitle="Mots clés d'urgence" />
              )}
            </div>

            {/* ─ Section 2 : Signaux — directement sous les KPIs ── */}
            {intel.business_labels && (
              <>
                <CanvasDivider />
                <CanvasSectionHeader icon="⚡" label="Tableau de bord des signaux" badge="Lié aux KPIs" />
                <div style={{ background: "var(--bg-card)", borderRadius: 16, overflow: "hidden" }}>
                  <SignalPanel data={intel} sinceDays={sinceDays} />
                </div>
              </>
            )}

            {/* ─ Section 3 : Graphiques ───────────────────────── */}
            <CanvasDivider />
            <CanvasSectionHeader icon="◉" label="Analyse temporelle & Distribution" />

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
              <VisualCard title="Activité (par jour)" sub={`${sinceDays} jours`} accent={config.color}>
                <BarChart data={byDayData} height={140} color={config.color} />
              </VisualCard>
              <VisualCard title="Polarité des communications" sub="Sentiment global" accent="#22c55e">
                <DonutChart data={sentimentSlices} size={150} label="items" />
              </VisualCard>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: isGmail && labelSlices?.length > 0 ? "1fr 1fr" : "1fr", gap: "1rem", marginBottom: "1rem" }}>
              <VisualCard title={isGmail ? "Top expéditeurs" : "Top auteurs"} accent={config.color}>
                {senderSlices?.length > 0
                  ? <DonutChart data={senderSlices} size={150} label="msgs" />
                  : <EmptyState text="Pas de données expéditeurs" />}
              </VisualCard>
              {isGmail && labelSlices?.length > 0 && (
                <VisualCard title="Distribution des labels Gmail" accent="#f59e0b">
                  <DonutChart data={labelSlices} size={150} label="labels" />
                </VisualCard>
              )}
            </div>

            {/* Tendance risques */}
            {intel.risk_trend?.length > 0 && (
              <VisualCard title="Tendance des risques" sub="Blocked · Urgent · Risk" accent="#ef4444">
                <LineChart data={intel.risk_trend} height={130} color="#ef4444" />
              </VisualCard>
            )}

            {/* Heure d'activité (Gmail) */}
            {isGmail && data.by_hour && (
              <div style={{ marginTop: "1rem" }}>
                <VisualCard title="Pic d'activité par heure (6h–22h)" sub="Répartition horaire" accent="#3e5c76">
                  <BarChart
                    data={data.by_hour.slice(6, 22).map((d: any) => ({ label: `${d.hour}h`, value: d.count }))}
                    height={120} color="#3e5c76"
                  />
                </VisualCard>
              </div>
            )}

            {/* Mots-clés */}
            {data.keyword_frequency?.length > 0 && (
              <div style={{ marginTop: "1rem", background: "var(--bg-card)", borderRadius: 14, padding: "1.25rem", border: "1px solid var(--border)", boxShadow: "0 2px 10px var(--shadow-card)" }}>
                <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700, marginBottom: 12 }}>
                  Mots-clés fréquents
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {data.keyword_frequency.map((k: any, i: number) => (
                    <span key={i} style={{
                      padding: "4px 12px", borderRadius: 100,
                      background: `rgba(62,92,118,${0.07 + (1 - i / data.keyword_frequency.length) * 0.12})`,
                      color: "#3e5c76", fontSize: 12, fontWeight: 500,
                    }}>
                      {k.word} <span style={{ color: "#748cab", fontSize: 11 }}>{k.count}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

          </div>{/* end BI Canvas */}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          TAB 2 — Alertes & Risques
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "alerts" && (
        <div>
          {/* Risk KPIs (Outlook) */}
          {isOutlook && (
            <>
              <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 10 }}>
                Risques &amp; Alertes Outlook
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "1rem", marginBottom: "1.75rem" }}>
                <KPICard title="Escalades" value={data.escalation?.count ?? 0} icon="🚨"
                  risk={(data.escalation?.count ?? 0) > 5 ? "high" : (data.escalation?.count ?? 0) > 2 ? "medium" : "low"}
                  subtitle="urgent · ASAP · critical" />
                <KPICard title="Non lus" value={data.unread?.count ?? 0} icon="🔴"
                  risk={(data.unread?.rate ?? 0) > 40 ? "high" : (data.unread?.rate ?? 0) > 20 ? "medium" : "low"}
                  subtitle={`${data.unread?.rate ?? 0}% du total`} />
                <KPICard title="Haute importance" value={data.high_importance?.count ?? 0} icon="⭐"
                  accent="#f59e0b" subtitle="High · Urgent" />
                <KPICard title="Expéditeurs uniques" value={data.unique_senders ?? 0} icon="👤"
                  accent="#3e5c76" subtitle="Sources distinctes" />
              </div>
            </>
          )}

          {/* Risk KPIs (Gmail) */}
          {isGmail && (
            <>
              <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 10 }}>
                Risques &amp; Alertes décisionnelles
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "1rem", marginBottom: "1.75rem" }}>
                <KPICard title="Escalades" value={data.escalation.count} icon="🚨"
                  risk={data.escalation.count > 5 ? "high" : data.escalation.count > 2 ? "medium" : "low"}
                  subtitle="urgent · ASAP · critical" />
                <KPICard title="Sans réponse +48h" value={data.no_reply_48h.count} icon="⏰"
                  risk={data.no_reply_48h.count > 5 ? "high" : data.no_reply_48h.count > 2 ? "medium" : "low"}
                  subtitle="Importants non traités" />
                <KPICard title="Critiques non résolus" value={data.unanswered_critical.count} icon="❗"
                  risk={data.unanswered_critical.count > 0 ? "high" : "low"}
                  subtitle="Escalade + pas de réponse" />
                <KPICard title="Threads longs" value={data.threads.long_count} icon="🔁"
                  risk={data.threads.long_count > 5 ? "medium" : "low"}
                  subtitle={`Moy. ${data.threads.avg_length} msg/thread`} />
                <KPICard title="Back-and-forth" value={`${data.threads.back_and_forth_score}/10`} icon="↔"
                  risk={data.threads.back_and_forth_score > 6 ? "high" : data.threads.back_and_forth_score > 3 ? "medium" : "low"}
                  subtitle="Intensité des échanges" />
                <KPICard title="Expéditeurs uniques" value={data.unique_senders} icon="👤"
                  accent="#3e5c76" subtitle="Sources distinctes" />
              </div>
            </>
          )}

          {intel.business_labels && <SignalPanel data={intel} sinceDays={sinceDays} />}

          {intel.at_risk_items?.length > 0 && (
            <RiskFeed items={intel.at_risk_items} title={`Signaux de Risque — ${config.label}`} />
          )}

          <div style={{ background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px var(--shadow-card)", border: "1px solid rgba(239,68,68,0.2)", marginBottom: "1.5rem" }}>
            <div style={{ fontSize: 12, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 4 }}>Tendance des risques</div>
            <div style={{ fontSize: 11, color: "#748cab", marginBottom: 12 }}>Blocked · Urgent · Risk</div>
            {intel.risk_trend?.length > 0
              ? <LineChart data={intel.risk_trend} height={130} color="#ef4444" />
              : <p style={{ color: "#748cab", fontSize: 13, paddingTop: 40, textAlign: "center" }}>Aucun signal de risque</p>
            }
          </div>

          {isGmail && data.escalation.items.length > 0 && (
            <div style={{ background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px var(--shadow-card)", border: "1px solid rgba(239,68,68,0.2)", marginBottom: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <span>🚨</span>
                <div style={{ fontSize: 12, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                  Emails d&apos;escalade — action requise
                </div>
              </div>
              {data.escalation.items.map((item: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "#fef2f2", borderRadius: 10, marginBottom: 8, borderLeft: "3px solid #ef4444" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>{item.title}</div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>{item.author} · {new Date(item.timestamp).toLocaleString("fr-FR")}</div>
                </div>
              ))}
            </div>
          )}

          {isGmail && data.threads.long_threads.length > 0 && (
            <div style={{ background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px var(--shadow-card)", border: "1px solid rgba(245,158,11,0.2)", marginBottom: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <span>🔁</span>
                <div style={{ fontSize: 12, color: "#f59e0b", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                  Threads à risque de désalignement
                </div>
              </div>
              {data.threads.long_threads.map((t: any, i: number) => (
                <div key={i} style={{ marginBottom: 8 }}>
                  {/* Thread header — click to expand */}
                  <div
                    onClick={() => setExpanded(expandedThread === i ? null : i)}
                    style={{ padding: "10px 14px", background: "#fffbeb", borderRadius: expandedThread === i ? "10px 10px 0 0" : 10, display: "flex", justifyContent: "space-between", alignItems: "center", borderLeft: "3px solid #f59e0b", cursor: "pointer" }}
                  >
                    <div style={{ fontSize: 13, color: "var(--text-primary)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {(t.subject || "").slice(0, 60)}{t.subject?.length > 60 ? "…" : ""}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, marginLeft: 12 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b" }}>{t.message_count} messages</span>
                      <span style={{ fontSize: 11, color: "#f59e0b" }}>{expandedThread === i ? "▲" : "▼"}</span>
                    </div>
                  </div>

                  {/* Thread emails list */}
                  {expandedThread === i && (
                    <div style={{ border: "1px solid rgba(245,158,11,0.2)", borderTop: "none", borderRadius: "0 0 10px 10px", overflow: "hidden" }}>
                      {(t.items || []).map((msg: any, j: number) => (
                        <div
                          key={j}
                          onClick={() => setThreadDetail(msg)}
                          style={{ padding: "9px 14px", borderTop: j > 0 ? "1px solid rgba(245,158,11,0.1)" : "none", display: "flex", alignItems: "center", gap: 10, cursor: "pointer", background: "#fff", transition: "background 0.1s" }}
                          onMouseEnter={e => (e.currentTarget.style.background = "#fffbeb")}
                          onMouseLeave={e => (e.currentTarget.style.background = "#fff")}
                        >
                          <span style={{ fontSize: 11, color: "#94a3b8", width: 16, textAlign: "center", flexShrink: 0 }}>{j + 1}</span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{msg.title}</div>
                            <div style={{ fontSize: 11, color: "#748cab", marginTop: 1 }}>{msg.author} · {new Date(msg.timestamp).toLocaleString("fr-FR")}</div>
                          </div>
                          {msg.sentiment_label && (
                            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 20, background: msg.sentiment_label === "NEGATIVE" ? "#fef2f2" : msg.sentiment_label === "POSITIVE" ? "#f0fdf4" : "#f1f5f9", color: msg.sentiment_label === "NEGATIVE" ? "#ef4444" : msg.sentiment_label === "POSITIVE" ? "#16a34a" : "#64748b", flexShrink: 0 }}>
                              {msg.sentiment_label}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {threadDetail && (
            <MessageDetailModal item={threadDetail} onClose={() => setThreadDetail(null)} />
          )}

          {isOutlook && (data.escalation?.items?.length ?? 0) > 0 && (
            <div style={{ background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px var(--shadow-card)", border: "1px solid rgba(239,68,68,0.2)", marginBottom: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <span>🚨</span>
                <div style={{ fontSize: 12, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                  Emails d&apos;escalade Outlook — action requise
                </div>
              </div>
              {data.escalation.items.map((item: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "#fef2f2", borderRadius: 10, marginBottom: 8, borderLeft: "3px solid #ef4444" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>{item.title}</div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>{item.author} · {new Date(item.timestamp).toLocaleString("fr-FR")}</div>
                </div>
              ))}
            </div>
          )}

          {!intel.business_labels && !intel.at_risk_items?.length && !isGmail && !isOutlook && (
            <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>✅</div>
              <div style={{ fontSize: 14 }}>Aucune alerte détectée sur {config.label}</div>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          TAB 3 — Décisions
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "decisions" && (
        <div>
          <PriorityInbox sinceDays={sinceDays} source={source} />
          <div style={{ marginTop: "1.5rem" }}>
            <ActionItems />
          </div>
          <div style={{ marginTop: "1.5rem" }}>
            <DecisionLog />
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          TAB 4 — Équipe & Système
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "team" && (
        <div>
          {intel.burnout && (
            <div style={{ marginBottom: "1.5rem" }}>
              <BurnoutCard data={intel.burnout} />
            </div>
          )}
          <div style={{ background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px var(--shadow-card)", border: "1px solid var(--border)", marginBottom: "1.5rem" }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
              Répartition du sentiment
            </div>
            <div style={{ display: "flex", gap: "2rem", alignItems: "center" }}>
              <DonutChart data={sentimentSlices} size={130} label="msgs" />
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {sentimentSlices.map(s => (
                  <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", background: s.color }} />
                    <span style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500 }}>{s.label}</span>
                    <span style={{ fontSize: 13, color: "#748cab" }}>{s.value}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {data.keyword_frequency?.length > 0 && (
            <div style={{ background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px var(--shadow-card)", border: "1px solid var(--border)", marginBottom: "1.5rem" }}>
              <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
                Mots-clés fréquents
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {data.keyword_frequency.map((k: any, i: number) => (
                  <span key={i} style={{
                    padding: "4px 12px", borderRadius: 100,
                    background: `rgba(62,92,118,${0.07 + (1 - i / data.keyword_frequency.length) * 0.12})`,
                    color: "#3e5c76", fontSize: 12, fontWeight: 500,
                  }}>
                    {k.word} <span style={{ color: "#748cab", fontSize: 11 }}>{k.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {!intel.burnout && !data.keyword_frequency?.length && (
            <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>🧠</div>
              <div style={{ fontSize: 14 }}>Pas assez de données pour l&apos;analyse d&apos;équipe</div>
            </div>
          )}
        </div>
      )}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
