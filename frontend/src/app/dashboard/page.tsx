"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import KPICard from "@/components/KPICard";
import LineChart from "@/components/charts/LineChart";
import BarChart from "@/components/charts/BarChart";
import DonutChart from "@/components/charts/DonutChart";
import SignalPanel from "@/components/intelligence/SignalPanel";
import RiskFeed from "@/components/intelligence/RiskFeed";
import BurnoutCard from "@/components/intelligence/BurnoutCard";
import MondayBrief from "@/components/MondayBrief";
import PriorityInbox from "@/components/PriorityInbox";
import ActionItems from "@/components/ActionItems";
import CompareMode from "@/components/CompareMode";
import DecisionLog from "@/components/DecisionLog";
import AlertToast from "@/components/AlertToast";
import SearchBar from "@/components/SearchBar";
import MLStatusCard from "@/components/MLStatusCard";

const SOURCE_COLORS: Record<string, string> = {
  gmail: "#EA4335", slack: "#4A154B", jira: "#0052CC",
  notion: "#333", outlook: "#0078D4",
};

const PERIOD_OPTIONS = [7, 30, 90];

const TABS = [
  { id: "overview",  label: "Vue d'ensemble", icon: "◈" },
  { id: "alerts",    label: "Alertes & Risques", icon: "🚨" },
  { id: "decisions", label: "Décisions", icon: "✅" },
  { id: "team",      label: "Équipe & Système", icon: "🧠" },
] as const;

type TabId = typeof TABS[number]["id"];

const SOURCE_META: Record<string, { label: string; icon: string; color: string; description: string }> = {
  gmail:    { label: "Gmail",    icon: "✉️",  color: "#EA4335", description: "Emails & threads" },
  slack:    { label: "Slack",    icon: "💬",  color: "#4A154B", description: "Messages & canaux" },
  jira:     { label: "Jira",     icon: "📋",  color: "#0052CC", description: "Tickets & sprints" },
  clickup:  { label: "ClickUp",  icon: "⬆️", color: "#7B68EE", description: "Tâches & projets" },
  onedrive: { label: "OneDrive", icon: "☁️", color: "#0078D4", description: "Fichiers & docs" },
  notion:   { label: "Notion",   icon: "📝",  color: "#333333", description: "Notes & wikis" },
};

export default function DashboardOverview() {
  const { t } = useI18n();
  const router = useRouter();
  const [sinceDays, setSinceDays] = useState(30);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [data, setData]     = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [hoveredTab, setHoveredTab] = useState<TabId | null>(null);

  const fetchData = () => {
    setLoading(true);
    setError(null);
    API.get(`/api/analytics/overview?since_days=${sinceDays}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [sinceDays]);

  const handleSync = async () => {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const r = await API.post("/api/sync", { since_days: 90 });
      const total = r.data.total_items_stored ?? 0;
      setSyncMsg(`Sync terminé — ${total} messages`);
      fetchData();
    } catch (e: any) {
      setSyncMsg(`Erreur : ${e.message}`);
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: 36, height: 36, border: "3px solid rgba(62,92,118,0.2)", borderTop: "3px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        <p style={{ color: "#748cab", fontSize: 13 }}>{t.loading}</p>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ background: "#fef2f2", border: "1px solid #ef4444", borderRadius: 12, padding: "1.5rem", color: "#ef4444" }}>
      <strong>Error:</strong> {error}<br />
      <small style={{ color: "#748cab" }}>{t.error_backend}</small>
    </div>
  );
  if (!data) return null;

  const intel = data.intelligence ?? {};
  const riskLevel = data.risk_index > 60 ? "high" : data.risk_index > 30 ? "medium" : "low";
  const riskLabel = riskLevel === "high" ? "Critique" : riskLevel === "medium" ? "Modéré" : "Faible";
  const alertCount = (intel.at_risk_items?.length ?? 0) + (data.critical_alerts ?? 0);

  const sourceSlices = Object.entries(data.by_source as Record<string, number>).map(([k, v]) => ({
    label: k.charAt(0).toUpperCase() + k.slice(1),
    value: v as number,
    color: SOURCE_COLORS[k] ?? "#748cab",
  }));

  const sentimentSlices = [
    { label: t.positif, value: data.sentiment.positive, color: "#22c55e" },
    { label: t.neutre,  value: data.sentiment.neutral,  color: "#94a3b8" },
    { label: t.negatif, value: data.sentiment.negative, color: "#ef4444" },
  ];

  return (
    <div id="dashboard-print">
      <AlertToast />

      {/* ── Header ───────────────────────────────────────────────── */}
      <div style={{ marginBottom: "1.5rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", marginBottom: 4 }}>
            {t.page_overview}
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", letterSpacing: "-0.02em", margin: 0 }}>
            {t.dashboard_title}
          </h1>
          <p style={{ color: "#748cab", fontSize: 12, marginTop: 4 }}>
            {t.dashboard_sub(data.total_items, new Date(data.computed_at).toLocaleString("fr-FR"))}
          </p>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {PERIOD_OPTIONS.map(d => (
            <button key={d} onClick={() => setSinceDays(d)} style={{
              padding: "5px 13px", borderRadius: 20, cursor: "pointer",
              border: `1px solid ${sinceDays === d ? "#3e5c76" : "rgba(62,92,118,0.2)"}`,
              background: sinceDays === d ? "#3e5c76" : "transparent",
              color: sinceDays === d ? "#fff" : "#748cab",
              fontSize: 12, fontWeight: sinceDays === d ? 600 : 400,
            }}>{d}j</button>
          ))}
          <button onClick={handleSync} disabled={syncing} style={{
            marginLeft: 4, padding: "5px 13px", borderRadius: 20, cursor: syncing ? "not-allowed" : "pointer",
            border: "1px solid rgba(62,92,118,0.3)", background: "rgba(62,92,118,0.08)",
            color: "#3e5c76", fontSize: 12, fontWeight: 500,
            display: "flex", alignItems: "center", gap: 5,
          }}>
            <span style={{ display: "inline-block", animation: syncing ? "spin 0.8s linear infinite" : "none" }}>↻</span>
            {syncing ? t.btn_syncing : t.btn_sync}
          </button>
          {syncMsg && (
            <span style={{ fontSize: 11, color: syncMsg.startsWith("Erreur") ? "#ef4444" : "#22c55e" }}>
              {syncMsg}
            </span>
          )}
          <button onClick={() => window.print()} style={{
            padding: "5px 13px", borderRadius: 20, cursor: "pointer",
            border: "1px solid rgba(62,92,118,0.3)", background: "transparent",
            color: "#748cab", fontSize: 12,
          }}>⬇ PDF</button>
        </div>
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
      <div style={{ marginBottom: "1.25rem" }}>
        <SearchBar />
      </div>

      {/* ── Tabs nav ─────────────────────────────────────────────── */}
      <div style={{
        display: "flex", gap: 2, borderBottom: "2px solid rgba(62,92,118,0.12)",
        marginBottom: "2rem", overflowX: "auto",
      }}>
        {TABS.map(tab => {
          const isActive = activeTab === tab.id;
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
                color: isActive ? "#3e5c76" : hoveredTab === tab.id ? "#3e5c76" : "#748cab",
                borderBottom: isActive ? "2px solid #3e5c76" : hoveredTab === tab.id ? "2px solid rgba(62,92,118,0.35)" : "2px solid transparent",
                marginBottom: -2, transition: "all 0.15s",
              }}
            >
              <span>{tab.icon}</span>
              {tab.label}
              {showBadge && (
                <span style={{
                  background: "#ef4444", color: "#fff",
                  fontSize: 10, fontWeight: 700,
                  borderRadius: 20, padding: "1px 6px", lineHeight: "16px",
                }}>{alertCount}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* ══════════════════════════════════════════════════════════
          ONGLET 1 — VUE D'ENSEMBLE
          KPIs + Graphiques + Résumé exécutif
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "overview" && (
        <div>
          {/* Résumé exécutif */}
          <div style={{ marginBottom: "2rem" }}>
            <MondayBrief sinceDays={sinceDays} />
          </div>

          {/* KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
            <KPICard title={t.kpi_total} value={data.total_items} icon="◈"
              subtitle={t.kpi_total_sub(data.since_days)} />
            <KPICard title={t.kpi_sources} value={`${data.connected_sources}/${data.total_sources}`} icon="⊕"
              accent="#22c55e" subtitle={t.kpi_sources_sub} />
            <KPICard title={t.kpi_alerts} value={data.critical_alerts} icon="🚨"
              risk={data.critical_alerts > 5 ? "high" : data.critical_alerts > 2 ? "medium" : "low"}
              subtitle={t.kpi_alerts_sub} />
            <KPICard title={t.kpi_risk} value={`${data.risk_index}/100`} icon="🎯"
              risk={riskLevel} subtitle={t.kpi_risk_sub(riskLabel)} />
            <KPICard title={t.kpi_signals} value={intel.risk_count ?? 0} icon="⚠️"
              risk={(intel.risk_count ?? 0) > 10 ? "high" : (intel.risk_count ?? 0) > 4 ? "medium" : "low"}
              subtitle={t.kpi_signals_sub(intel.risk_rate ?? 0)} />
            <KPICard title={t.kpi_velocity} value={data.velocity.this_week} icon="⚡"
              delta={Number(data.velocity.delta_pct)}
              subtitle={t.kpi_velocity_sub(data.velocity.last_week)} />
            <KPICard title={t.kpi_sentiment} value={`${data.sentiment.positive}%`} icon="◉"
              accent="#22c55e"
              subtitle={t.kpi_sentiment_sub(data.sentiment.negative, data.sentiment.neutral)} />
            <KPICard title={t.kpi_nlp} value={`${intel.nlp_coverage ?? 0}%`} icon="🧠"
              accent={(intel.nlp_coverage ?? 0) > 80 ? "#22c55e" : "#f59e0b"}
              subtitle={(intel.nlp_coverage ?? 0) > 80 ? t.kpi_nlp_active : t.kpi_nlp_sync} />
          </div>

          {/* Analyse business de communication */}
          {intel.business_labels && (
            <div style={{ marginBottom: "2rem" }}>
              <SignalPanel data={intel} />
            </div>
          )}

          {/* Graphiques — ligne 1 : courbes temporelles */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
            <div style={cardStyle}>
              <ChartLabel title="Activité globale" sub="Messages par jour" />
              <LineChart data={data.activity_timeline} height={140} />
            </div>
            <div style={{ ...cardStyle, border: "1px solid rgba(239,68,68,0.15)" }}>
              <ChartLabel title="Tendance des risques" sub="Blocked · Urgent · Conflict · Overload" color="#ef4444" />
              {intel.risk_trend?.length > 0
                ? <LineChart data={intel.risk_trend} height={140} color="#ef4444" />
                : <EmptyState text="Aucun signal de risque détecté" />
              }
            </div>
          </div>

          {/* Graphiques — ligne 2 : volumes + répartition */}
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "1.5rem", marginBottom: "2rem" }}>
            <div style={cardStyle}>
              <ChartLabel title="Volume par source" sub="Nombre de messages" />
              <BarChart
                data={Object.entries(data.by_source as Record<string, number>).map(([k, v]) => ({
                  label: k.charAt(0).toUpperCase() + k.slice(1),
                  value: v as number,
                  color: SOURCE_COLORS[k] ?? "#748cab",
                }))}
                height={130}
              />
            </div>
            <div style={cardStyle}>
              <ChartLabel title="Répartition sources" />
              <DonutChart data={sourceSlices} size={145} label="items" />
            </div>
            <div style={cardStyle}>
              <ChartLabel title="Polarité" sub="Sentiment global" />
              <DonutChart data={sentimentSlices} size={145} label="msgs" />
            </div>
          </div>

          {/* ── Tableau de bord par source ─────────────────────── */}
          <div style={{ marginBottom: "2rem" }}>
            <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.15em", fontWeight: 600, marginBottom: 14 }}>
              Explorer par source
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem" }}>
              {Object.entries(data.by_source as Record<string, number>)
                .filter(([, count]) => count > 0)
                .sort(([, a], [, b]) => b - a)
                .map(([src, count]) => {
                  const meta = SOURCE_META[src] ?? { label: src, icon: "◈", color: "#748cab", description: "Messages" };
                  return (
                    <div
                      key={src}
                      onClick={() => router.push(`/dashboard/${src}`)}
                      style={{
                        background: "#fff",
                        borderRadius: 16,
                        padding: "1.25rem",
                        boxShadow: "0 2px 12px rgba(13,19,33,0.06)",
                        border: `1px solid ${meta.color}22`,
                        cursor: "pointer",
                        transition: "all 0.18s",
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                      }}
                      onMouseEnter={e => {
                        (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
                        (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 24px ${meta.color}22`;
                        (e.currentTarget as HTMLDivElement).style.borderColor = `${meta.color}55`;
                      }}
                      onMouseLeave={e => {
                        (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
                        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 2px 12px rgba(13,19,33,0.06)";
                        (e.currentTarget as HTMLDivElement).style.borderColor = `${meta.color}22`;
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 20 }}>{meta.icon}</span>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>{meta.label}</div>
                            <div style={{ fontSize: 11, color: "#748cab" }}>{meta.description}</div>
                          </div>
                        </div>
                        <span style={{ fontSize: 11, color: meta.color, fontWeight: 700 }}>→</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                        <span style={{ fontSize: 24, fontWeight: 700, color: meta.color }}>{count}</span>
                        <span style={{ fontSize: 11, color: "#748cab" }}>messages</span>
                      </div>
                      <div style={{
                        fontSize: 11, fontWeight: 600, color: meta.color,
                        background: `${meta.color}12`, borderRadius: 8,
                        padding: "4px 10px", textAlign: "center",
                      }}>
                        Voir le dashboard →
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>

        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          ONGLET 2 — ALERTES & RISQUES
          Signaux prioritaires + messages à risques + inbox
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "alerts" && (
        <div>
          {alertCount === 0 && (
            <div style={{ ...cardStyle, textAlign: "center", padding: "3rem", color: "#22c55e" }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>Aucune alerte critique</div>
              <div style={{ fontSize: 13, color: "#748cab", marginTop: 4 }}>Tous les indicateurs sont dans les normes</div>
            </div>
          )}

          {intel.at_risk_items?.length > 0 && (
            <div style={{ marginBottom: "1.5rem" }}>
              <RiskFeed items={intel.at_risk_items} />
            </div>
          )}

          <PriorityInbox sinceDays={sinceDays} />
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          ONGLET 3 — DÉCISIONS
          Actions à mener + mode comparaison
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "decisions" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
            <DecisionLog />
            <ActionItems />
          </div>
          <CompareMode />
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          ONGLET 4 — ÉQUIPE & SYSTÈME
          Burnout + moteur ML
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "team" && (
        <div style={{ display: "grid", gridTemplateColumns: intel.burnout ? "1fr 1fr" : "1fr", gap: "1.5rem" }}>
          {intel.burnout
            ? <BurnoutCard data={intel.burnout} />
            : (
              <div style={{ ...cardStyle, textAlign: "center", padding: "2.5rem", color: "#748cab" }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>🧘</div>
                <div style={{ fontWeight: 600 }}>Pas de signal de surcharge détecté</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>L'équipe semble opérer normalement</div>
              </div>
            )
          }
          <MLStatusCard />
        </div>
      )}

      <style>{`
        @media print {
          aside, button, .no-print { display: none !important; }
          body { background: #fff !important; }
          #dashboard-print { margin: 0; padding: 0; }
        }
      `}</style>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 16,
  padding: "1.5rem",
  boxShadow: "0 2px 12px rgba(13,19,33,0.06)",
  border: "1px solid rgba(62,92,118,0.1)",
};

function ChartLabel({ title, sub, color = "#748cab" }: { title: string; sub?: string; color?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, color, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{title}</div>
      {sub && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p style={{ color: "#748cab", fontSize: 13, paddingTop: 50, textAlign: "center" }}>{text}</p>;
}
