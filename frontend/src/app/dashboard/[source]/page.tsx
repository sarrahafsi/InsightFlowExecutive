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

const SOURCE_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  gmail:    { label: "Gmail",    icon: "✉",  color: "#EA4335" },
  slack:    { label: "Slack",    icon: "#",  color: "#4A154B" },
  jira:     { label: "Jira",     icon: "J",  color: "#0052CC" },
  clickup:  { label: "ClickUp",  icon: "⬆", color: "#7B68EE" },
  onedrive: { label: "OneDrive", icon: "☁", color: "#0078D4" },
};

const LABEL_COLORS: Record<string, string> = {
  IMPORTANT: "#f59e0b", STARRED: "#3b82f6", SENT: "#22c55e",
  SPAM: "#ef4444", DRAFT: "#94a3b8", PERSONAL: "#8b5cf6",
};

const PERIOD_OPTIONS = [7, 30, 90];

const TABS = [
  { id: "overview",  label: "Vue d'ensemble",  icon: "◈" },
  { id: "alerts",    label: "Alertes & Risques", icon: "🚨" },
  { id: "decisions", label: "Décisions",         icon: "✅" },
  { id: "team",      label: "Équipe & Système",  icon: "🧠" },
] as const;

type TabId = typeof TABS[number]["id"];

export default function SourceDashboard() {
  const { source } = useParams<{ source: string }>();
  const config = SOURCE_CONFIG[source] ?? { label: source, icon: "◈", color: "#748cab" };

  const [sinceDays, setSinceDays]   = useState(30);
  const [activeTab, setActiveTab]   = useState<TabId>("overview");
  const [hoveredTab, setHoveredTab] = useState<TabId | null>(null);
  const [data, setData]             = useState<any>(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

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

  const intel     = data.intelligence ?? {};
  const isGmail   = source === "gmail" && !!data.threads;
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
      <div style={{ marginBottom: "1.5rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: config.color, marginBottom: 6, fontWeight: 600 }}>
            {config.icon} {config.label} Analytics
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 28, color: "#0d1321" }}>
            Analyse {config.label}
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginTop: 4 }}>
            {data.volume.total} messages · Mis à jour {new Date(data.computed_at).toLocaleString("fr-FR")}
          </p>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {PERIOD_OPTIONS.map(d => (
            <button key={d} onClick={() => setSinceDays(d)} style={{
              padding: "5px 13px", borderRadius: 20, cursor: "pointer",
              border: `1px solid ${sinceDays === d ? config.color : "rgba(62,92,118,0.2)"}`,
              background: sinceDays === d ? config.color : "transparent",
              color: sinceDays === d ? "#fff" : "#748cab",
              fontSize: 12, fontWeight: sinceDays === d ? 600 : 400,
            }}>{d}j</button>
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

      {/* ── Tabs nav ──────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 2, borderBottom: "2px solid rgba(62,92,118,0.12)", marginBottom: "2rem", overflowX: "auto" }}>
        {TABS.map(tab => {
          const isActive  = activeTab === tab.id;
          const showBadge = tab.id === "alerts" && alertCount > 0;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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
          TAB 1 — Vue d'ensemble
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "overview" && (
        <div>
          {/* KPI Row */}
          <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 10 }}>
            Volume &amp; Engagement
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "1rem", marginBottom: "1.75rem" }}>
            <KPICard title={`${config.label} (sem.)`} value={data.volume.this_week} icon="📥"
              delta={data.volume.delta_pct} accent={config.color}
              subtitle={`Sem. passée : ${data.volume.last_week}`} />
            <KPICard title="Total analysés" value={data.volume.total} icon="📦"
              accent={config.color} subtitle={`${sinceDays} derniers jours`} />
            <KPICard title="Signaux de risque" value={intel.risk_count ?? 0} icon="⚠️"
              risk={(intel.risk_count ?? 0) > 5 ? "high" : (intel.risk_count ?? 0) > 2 ? "medium" : "low"}
              subtitle={`${intel.risk_rate ?? 0}% des messages`} />
            {isGmail && (
              <>
                <KPICard title="Non lus" value={data.unread.count} icon="🔴"
                  risk={data.unread.rate > 40 ? "high" : data.unread.rate > 20 ? "medium" : "low"}
                  subtitle={`${data.unread.rate}% du total`} />
                <KPICard title="Importants" value={data.important.count} icon="⭐"
                  accent="#f59e0b" subtitle={`${data.important.rate}% du total`} />
                <KPICard title="Tps réponse moy." icon="⚡"
                  value={data.avg_response_hours ? `${data.avg_response_hours}h` : "N/A"}
                  accent="#3e5c76"
                  subtitle={data.avg_response_hours ? "Basé sur les threads" : "Dossier envoyé requis"} />
              </>
            )}
            {!isGmail && (
              <KPICard title="Alertes escalade" value={data.critical_alerts} icon="🚨"
                risk={data.critical_alerts > 5 ? "high" : data.critical_alerts > 2 ? "medium" : "low"}
                subtitle="Mots clés d'urgence" />
            )}
          </div>

          {/* Charts Row — Activity + Sentiment */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
              <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
                Activité (7 jours)
              </div>
              <BarChart data={byDayData} height={140} color={config.color} />
            </div>
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
              <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
                Polarité des communications
              </div>
              <DonutChart data={sentimentSlices} size={150} label="items" />
            </div>
          </div>

          {/* Top senders + Labels */}
          <div style={{ display: "grid", gridTemplateColumns: isGmail ? "1fr 1fr" : "1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
              <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
                {isGmail ? "Top expéditeurs" : "Top auteurs"}
              </div>
              {senderSlices?.length > 0
                ? <DonutChart data={senderSlices} size={150} label="items" />
                : <p style={{ color: "#748cab", fontSize: 13 }}>Pas de données</p>}
            </div>
            {isGmail && labelSlices?.length > 0 && (
              <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
                <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
                  Distribution des labels Gmail
                </div>
                <DonutChart data={labelSlices} size={150} label="labels" />
              </div>
            )}
          </div>

          {/* Gmail: Hour distribution */}
          {isGmail && data.by_hour && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
              <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
                Pic d&apos;activité par heure (6h – 22h)
              </div>
              <BarChart
                data={data.by_hour.slice(6, 22).map((d: any) => ({ label: `${d.hour}h`, value: d.count }))}
                height={120} color="#3e5c76"
              />
            </div>
          )}

          {/* Keywords */}
          {data.keyword_frequency?.length > 0 && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
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
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          TAB 2 — Alertes & Risques
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "alerts" && (
        <div>
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

          {/* Signal Panel */}
          {intel.business_labels && <SignalPanel data={intel} />}

          {/* Risk Feed */}
          {intel.at_risk_items?.length > 0 && (
            <RiskFeed items={intel.at_risk_items} title={`Signaux de Risque — ${config.label}`} />
          )}

          {/* Risk Trend */}
          <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(239,68,68,0.12)", marginBottom: "1.5rem" }}>
            <div style={{ fontSize: 12, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 4 }}>Tendance des risques</div>
            <div style={{ fontSize: 11, color: "#748cab", marginBottom: 12 }}>Blocked · Urgent · Risk</div>
            {intel.risk_trend?.length > 0
              ? <LineChart data={intel.risk_trend} height={130} color="#ef4444" />
              : <p style={{ color: "#748cab", fontSize: 13, paddingTop: 40, textAlign: "center" }}>Aucun signal de risque</p>
            }
          </div>

          {/* Gmail: Escalation items */}
          {isGmail && data.escalation.items.length > 0 && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(239,68,68,0.2)", marginBottom: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <span>🚨</span>
                <div style={{ fontSize: 12, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                  Emails d&apos;escalade — action requise
                </div>
              </div>
              {data.escalation.items.map((item: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "#fef2f2", borderRadius: 10, marginBottom: 8, borderLeft: "3px solid #ef4444" }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", marginBottom: 2 }}>{item.title}</div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>{item.author} · {new Date(item.timestamp).toLocaleString("fr-FR")}</div>
                </div>
              ))}
            </div>
          )}

          {/* Gmail: Long threads */}
          {isGmail && data.threads.long_threads.length > 0 && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(245,158,11,0.2)", marginBottom: "1.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <span>🔁</span>
                <div style={{ fontSize: 12, color: "#f59e0b", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                  Threads à risque de désalignement
                </div>
              </div>
              {data.threads.long_threads.map((t: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "#fffbeb", borderRadius: 10, marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center", borderLeft: "3px solid #f59e0b" }}>
                  <div style={{ fontSize: 13, color: "#0d1321" }}>{(t.subject || "").slice(0, 60)}...</div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", flexShrink: 0, marginLeft: 12 }}>{t.message_count} messages</span>
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!intel.business_labels && !intel.at_risk_items?.length && !isGmail && (
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

          {/* Sentiment trend */}
          <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
              Répartition du sentiment
            </div>
            <div style={{ display: "flex", gap: "2rem", alignItems: "center" }}>
              <DonutChart data={sentimentSlices} size={130} label="msgs" />
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {sentimentSlices.map(s => (
                  <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", background: s.color }} />
                    <span style={{ fontSize: 13, color: "#0d1321", fontWeight: 500 }}>{s.label}</span>
                    <span style={{ fontSize: 13, color: "#748cab" }}>{s.value}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Keywords */}
          {data.keyword_frequency?.length > 0 && (
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
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

          {/* Empty state if no burnout */}
          {!intel.burnout && !data.keyword_frequency?.length && (
            <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>🧠</div>
              <div style={{ fontSize: 14 }}>Pas assez de données pour l&apos;analyse d&apos;équipe</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
