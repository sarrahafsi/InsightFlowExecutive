"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getUser, isCEO } from "@/lib/auth";
import { useWS } from "@/lib/WebSocketContext";
import KPICard from "@/components/KPICard";
import {
  IconLayers, IconLink, IconAlertTriangle, IconTarget,
  IconActivity, IconZap, IconSmile, IconBrain,
  IconTrendingDown, IconStar, IconFlag, IconBarChart,
} from "@/components/icons";
import LineChart from "@/components/charts/LineChart";
import BarChart from "@/components/charts/BarChart";
import DonutChart from "@/components/charts/DonutChart";
import SignalPanel from "@/components/intelligence/SignalPanel";
import RiskFeed from "@/components/intelligence/RiskFeed";
import BurnoutCard from "@/components/intelligence/BurnoutCard";
import AnomalyCard from "@/components/intelligence/AnomalyCard";
import OrganizationHealthPanel from "@/components/intelligence/OrganizationHealthPanel";
import PriorityInbox from "@/components/PriorityInbox";
import ActionItems from "@/components/ActionItems";
import CompareMode from "@/components/CompareMode";
import DecisionLog from "@/components/DecisionLog";
import AlertToast from "@/components/AlertToast";
import SearchBar from "@/components/SearchBar";
import MLStatusCard from "@/components/MLStatusCard";
import TeamOverloadCard from "@/components/intelligence/TeamOverloadCard";
import PriorityMessages from "@/components/PriorityMessages";
import AttributionPanel from "@/components/AttributionPanel";
import AIRecommendations from "@/components/AIRecommendations";
import HeatmapChart from "@/components/charts/HeatmapChart";

const SOURCE_COLORS: Record<string, string> = {
  gmail: "#EA4335", slack: "#4A154B", jira: "#0052CC",
  notion: "#333333", outlook: "#0078D4", teams: "#6264A7",
  clickup: "#7B68EE", onedrive: "#0078D4",
};

const SOURCE_META: Record<string, { label: string; icon: string; color: string; description: string }> = {
  gmail:    { label: "Gmail",    icon: "✉️",  color: "#EA4335", description: "Emails & threads" },
  slack:    { label: "Slack",    icon: "💬",  color: "#4A154B", description: "Messages & canaux" },
  jira:     { label: "Jira",     icon: "📋",  color: "#0052CC", description: "Tickets & sprints" },
  clickup:  { label: "ClickUp",  icon: "⬆️", color: "#7B68EE", description: "Tâches & projets" },
  onedrive: { label: "OneDrive", icon: "☁️", color: "#0078D4", description: "Fichiers & docs" },
  notion:   { label: "Notion",   icon: "📝",  color: "#333333", description: "Notes & wikis" },
  outlook:  { label: "Outlook",  icon: "📨",  color: "#0078D4", description: "Emails Microsoft" },
  teams:    { label: "Teams",    icon: "🟣",  color: "#6264A7", description: "Messages Teams" },
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

/* ── Drill-through drawer ─────────────────────────────────────── */

interface DrillItem { kpiId: string; title: string; value: string | number }

function DrillDrawer({ item, data, intel, onClose }: {
  item: DrillItem; data: any; intel: any; onClose: () => void;
}) {
  const sourceSlices = Object.entries(data.by_source as Record<string, number>).map(([k, v]) => ({
    label: k.charAt(0).toUpperCase() + k.slice(1),
    value: v as number,
    color: SOURCE_COLORS[k] ?? "#748cab",
  }));

  const sentimentSlices = [
    { label: "Positif", value: data.sentiment.positive, color: "#22c55e" },
    { label: "Neutre",  value: data.sentiment.neutral,  color: "#94a3b8" },
    { label: "Négatif", value: data.sentiment.negative, color: "#ef4444" },
  ];

  const velocityData = [
    { label: "Sem. passée", value: data.velocity.last_week, color: "#94a3b8" },
    { label: "Cette sem.",  value: data.velocity.this_week, color: "#3e5c76" },
  ];

  const CONTENT: Record<string, { desc: string; node: React.ReactNode }> = {
    total: {
      desc: "Volume total des communications sur la période sélectionnée, réparti par source.",
      node: (
        <div>
          <SectionLabel>Répartition par source</SectionLabel>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
            <DonutChart data={sourceSlices} size={160} label="items" />
          </div>
          {sourceSlices.sort((a, b) => b.value - a.value).map(s => (
            <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, padding: "8px 10px", background: `${s.color}08`, borderRadius: 8, borderLeft: `3px solid ${s.color}` }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
              <span style={{ fontSize: 13, flex: 1, fontWeight: 600, color: "#0d1321" }}>{s.label}</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: s.color }}>{s.value}</span>
              <span style={{ fontSize: 11, color: "#748cab", width: 36, textAlign: "right" }}>
                {data.total_items ? Math.round((s.value / data.total_items) * 100) : 0}%
              </span>
            </div>
          ))}
        </div>
      ),
    },
    sources: {
      desc: "Sources de données connectées et leur volume de synchronisation.",
      node: (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {Object.entries(data.by_source as Record<string, number>).map(([src, count]) => {
            const m = SOURCE_META[src] ?? { label: src, icon: "·", color: "#748cab", description: "" };
            return (
              <div key={src} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
                borderRadius: 12, background: count > 0 ? `${m.color}08` : "#f8fafc",
                border: `1px solid ${count > 0 ? m.color + "22" : "rgba(62,92,118,0.08)"}`,
              }}>
                <span style={{ fontSize: 20 }}>{m.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>{m.label}</div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>{m.description}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: m.color }}>{count}</div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: count > 0 ? "#22c55e" : "#94a3b8", background: count > 0 ? "#f0fdf4" : "#f8fafc", borderRadius: 6, padding: "2px 6px", marginTop: 2 }}>
                    {count > 0 ? "Actif" : "Inactif"}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ),
    },
    alerts: {
      desc: "Alertes critiques détectées par l'analyse NLP sur vos communications.",
      node: intel.at_risk_items?.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {intel.at_risk_items.slice(0, 7).map((it: any, i: number) => (
            <div key={i} style={{ padding: "10px 12px", borderRadius: 10, background: "#fef2f2", border: "1px solid rgba(239,68,68,0.15)", borderLeft: "3px solid #ef4444" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", marginBottom: 4 }}>
                {it.subject ?? it.content?.slice(0, 65) ?? "Message à risque"}
              </div>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {it.risk_labels?.map((l: string) => (
                  <span key={l} style={{ fontSize: 10, background: "#ef444420", color: "#ef4444", borderRadius: 6, padding: "2px 7px", fontWeight: 600 }}>{l}</span>
                ))}
                {it.source && <span style={{ fontSize: 10, color: "#748cab" }}>{it.source}</span>}
              </div>
            </div>
          ))}
          {intel.at_risk_items.length > 7 && (
            <div style={{ fontSize: 12, color: "#748cab", textAlign: "center", padding: 8 }}>
              +{intel.at_risk_items.length - 7} alertes supplémentaires
            </div>
          )}
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "2.5rem", color: "#22c55e" }}>
          <div style={{ fontSize: 36 }}>✓</div>
          <div style={{ fontWeight: 600, marginTop: 8 }}>Aucune alerte critique</div>
        </div>
      ),
    },
    risk: {
      desc: "Indice de risque composite calculé à partir de l'ensemble des signaux détectés.",
      node: (
        <div>
          <div style={{
            display: "flex", alignItems: "center", gap: 16, marginBottom: 20,
            padding: "16px", borderRadius: 12,
            background: data.risk_index > 60 ? "#fef2f2" : data.risk_index > 30 ? "#fffbeb" : "#f0fdf4",
          }}>
            <div style={{ fontSize: 40, fontWeight: 700, color: data.risk_index > 60 ? "#ef4444" : data.risk_index > 30 ? "#f59e0b" : "#22c55e" }}>
              {data.risk_index}
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#0d1321" }}>
                {data.risk_index > 60 ? "Risque Critique" : data.risk_index > 30 ? "Risque Modéré" : "Risque Faible"}
              </div>
              <div style={{ fontSize: 12, color: "#748cab", marginTop: 3 }}>Score composite /100</div>
            </div>
          </div>
          {intel.risk_trend?.length > 0 && (
            <>
              <SectionLabel>Tendance des risques</SectionLabel>
              <LineChart data={intel.risk_trend} height={120} color="#ef4444" />
            </>
          )}
        </div>
      ),
    },
    signals: {
      desc: "Signaux de risque et catégories business détectés dans vos communications.",
      node: (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(intel.business_labels ?? []).filter((b: any) => b.count > 0)
            .sort((a: any, b: any) => b.count - a.count)
            .map((b: any) => (
              <div key={b.label} style={{
                display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                borderRadius: 10, background: `${b.color}0d`, borderLeft: `3px solid ${b.color}`,
              }}>
                <span style={{ fontSize: 18 }}>{b.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>{b.label}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: b.color }}>{b.count}</div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>{b.pct}%</div>
                </div>
              </div>
            ))}
        </div>
      ),
    },
    velocity: {
      desc: "Volume de messages cette semaine comparé à la semaine précédente.",
      node: (
        <div>
          <BarChart data={velocityData} height={150} />
          <div style={{ display: "flex", gap: 24, justifyContent: "center", marginTop: 20 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: "#94a3b8" }}>{data.velocity.last_week}</div>
              <div style={{ fontSize: 12, color: "#748cab" }}>Sem. passée</div>
            </div>
            <div style={{ display: "flex", alignItems: "center" }}>
              <span style={{ fontSize: 24, color: Number(data.velocity.delta_pct) >= 0 ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                {Number(data.velocity.delta_pct) >= 0 ? "↑" : "↓"} {Math.abs(Number(data.velocity.delta_pct))}%
              </span>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: "#3e5c76" }}>{data.velocity.this_week}</div>
              <div style={{ fontSize: 12, color: "#748cab" }}>Cette sem.</div>
            </div>
          </div>
        </div>
      ),
    },
    sentiment: {
      desc: "Analyse de la polarité émotionnelle globale des communications.",
      node: (
        <div>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
            <DonutChart data={sentimentSlices} size={160} label="msgs" />
          </div>
          {sentimentSlices.map(s => (
            <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, padding: "10px 12px", background: `${s.color}0d`, borderRadius: 10, borderLeft: `3px solid ${s.color}` }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
              <span style={{ fontSize: 13, flex: 1, fontWeight: 600, color: "#0d1321" }}>{s.label}</span>
              <span style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.value}%</span>
            </div>
          ))}
        </div>
      ),
    },
    nlp: {
      desc: "Taux de couverture de l'analyse NLP sur l'ensemble des messages traités.",
      node: (() => {
        const pct = intel.nlp_coverage ?? 0;
        const color = pct > 80 ? "#22c55e" : pct > 50 ? "#f59e0b" : "#ef4444";
        return (
          <div style={{ textAlign: "center", padding: "1rem" }}>
            <div style={{ position: "relative", width: 120, height: 120, margin: "0 auto 20px" }}>
              <svg width={120} height={120}>
                <circle cx={60} cy={60} r={50} fill="none" stroke="#f0f0f0" strokeWidth={10} />
                <circle cx={60} cy={60} r={50} fill="none" stroke={color} strokeWidth={10}
                  strokeDasharray={`${pct * 3.14} ${314 - pct * 3.14}`}
                  strokeLinecap="round"
                  transform="rotate(-90 60 60)"
                  style={{ transition: "stroke-dasharray 0.8s ease" }}
                />
                <text x={60} y={60} textAnchor="middle" dominantBaseline="middle" fontSize={22} fontWeight={700} fill={color}>{pct}%</text>
              </svg>
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#0d1321", marginBottom: 8 }}>
              {pct > 80 ? "Couverture excellente" : pct > 50 ? "Couverture partielle" : "Synchronisation requise"}
            </div>
            <div style={{ fontSize: 12, color: "#748cab", lineHeight: 1.6, maxWidth: 260, margin: "0 auto" }}>
              {pct > 80
                ? "Le moteur NLP analyse en temps réel toutes vos communications."
                : "Synchronisez vos sources pour améliorer la couverture de l'analyse NLP."
              }
            </div>
          </div>
        );
      })(),
    },
  };

  const cfg = CONTENT[item.kpiId] ?? { desc: "", node: <p style={{ color: "#748cab" }}>Détails non disponibles.</p> };

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(13,19,33,0.4)", zIndex: 1000, backdropFilter: "blur(3px)" }} />
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 420,
        background: "#fff", boxShadow: "-8px 0 48px rgba(13,19,33,0.18)",
        zIndex: 1001, display: "flex", flexDirection: "column",
        animation: "slideInRight 0.25s cubic-bezier(0.16,1,0.3,1)",
      }}>
        {/* Drawer header */}
        <div style={{ padding: "1.5rem", borderBottom: "1px solid rgba(62,92,118,0.1)", background: "linear-gradient(135deg,#1d2d44,#3e5c76)", color: "#f0ebd8" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(240,235,216,0.55)", marginBottom: 4 }}>
                Drill-through · {item.title}
              </div>
              <div style={{ fontSize: 32, fontWeight: 700, fontFamily: "DM Serif Display, serif" }}>{item.value}</div>
            </div>
            <button onClick={onClose} style={{
              width: 32, height: 32, borderRadius: 8, border: "1px solid rgba(240,235,216,0.25)",
              background: "rgba(240,235,216,0.1)", cursor: "pointer", fontSize: 18,
              color: "#f0ebd8", display: "flex", alignItems: "center", justifyContent: "center",
            }}>×</button>
          </div>
        </div>
        {/* Description */}
        {cfg.desc && (
          <div style={{ padding: "0.875rem 1.5rem", background: "rgba(62,92,118,0.04)", borderBottom: "1px solid rgba(62,92,118,0.06)" }}>
            <p style={{ fontSize: 12, color: "#748cab", margin: 0, lineHeight: 1.65 }}>{cfg.desc}</p>
          </div>
        )}
        {/* Scrollable content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>
          {cfg.node}
        </div>
      </div>
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 700, marginBottom: 10 }}>
      {children}
    </div>
  );
}

/* ── Main Dashboard Page ─────────────────────────────────────── */

export default function DashboardOverview() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const currentUser = getUser();
  const isManager   = currentUser ? isCEO(currentUser) : false;

  // Superadmin has no org data — send them to their own console
  useEffect(() => {
    if (currentUser?.role === "superadmin") router.replace("/dashboard/admin");
  }, []);

  const { syncSignal } = useWS();
  const [sinceDays, setSinceDays] = useState(1);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [data, setData]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [hoveredTab, setHoveredTab] = useState<TabId | null>(null);
  const [drillItem, setDrillItem]   = useState<DrillItem | null>(null);

  const drill = (kpiId: string, title: string, value: string | number) =>
    setDrillItem({ kpiId, title, value });

  const fetchData = () => {
    setLoading(true);
    setError(null);
    API.get(`/api/analytics/overview?since_days=${sinceDays}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [sinceDays, syncSignal]);

  const handleSync = async () => {
    setSyncing(true); setSyncMsg(null);
    try {
      const r = await API.post("/api/sync", { since_days: 90 });
      setSyncMsg(`Sync terminé — ${r.data.total_items_stored ?? 0} messages`);
      fetchData();
    } catch (e: any) {
      setSyncMsg(`Erreur : ${e.message}`);
    } finally { setSyncing(false); }
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

  const topSourceEntry = Object.entries(data.by_source as Record<string, number>)
    .sort(([, a], [, b]) => b - a)[0];

  return (
    <div id="dashboard-print">
      <AlertToast />

      {drillItem && (
        <DrillDrawer item={drillItem} data={data} intel={intel} onClose={() => setDrillItem(null)} />
      )}

      {/* ── Page Header ───────────────────────────────────────── */}
      <div style={{ marginBottom: "1rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", marginBottom: 4 }}>
            {t.page_overview}
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", letterSpacing: "-0.02em", margin: 0 }}>
            {t.dashboard_title}
          </h1>
          <p style={{ color: "#748cab", fontSize: 12, marginTop: 4 }}>
            {t.dashboard_sub(data.total_items, new Date(data.computed_at).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB"))}
          </p>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {PERIOD_OPTIONS.map(({ days, label }) => (
            <button key={days} onClick={() => setSinceDays(days)} style={{
              padding: "5px 13px", borderRadius: 20, cursor: "pointer",
              border: `1px solid ${sinceDays === days ? "#3e5c76" : "rgba(62,92,118,0.2)"}`,
              background: sinceDays === days ? "#3e5c76" : "transparent",
              color: sinceDays === days ? "#fff" : "#748cab",
              fontSize: 12, fontWeight: sinceDays === days ? 600 : 400, whiteSpace: "nowrap",
            }}>{label}</button>
          ))}
          <button onClick={handleSync} disabled={syncing} style={{
            marginLeft: 4, padding: "5px 13px", borderRadius: 20, cursor: syncing ? "not-allowed" : "pointer",
            border: "1px solid rgba(62,92,118,0.3)", background: "rgba(62,92,118,0.08)",
            color: "#3e5c76", fontSize: 12, fontWeight: 500, display: "flex", alignItems: "center", gap: 5,
          }}>
            <span style={{ display: "inline-block", animation: syncing ? "spin 0.8s linear infinite" : "none" }}>↻</span>
            {syncing ? t.btn_syncing : t.btn_sync}
          </button>
          {syncMsg && (
            <span style={{ fontSize: 11, color: syncMsg.startsWith("Erreur") ? "#ef4444" : "#22c55e" }}>{syncMsg}</span>
          )}
          <button onClick={() => window.print()} style={{
            padding: "5px 13px", borderRadius: 20, cursor: "pointer",
            border: "1px solid rgba(62,92,118,0.3)", background: "transparent",
            color: "#748cab", fontSize: 12,
            display: "flex", alignItems: "center", gap: 5,
          }}>
            ⬇ PDF
          </button>
        </div>
      </div>

      {/* ── Search ─────────────────────────────────────────────── */}
      <div style={{ marginBottom: "1.25rem" }}>
        <SearchBar />
      </div>

      {/* ══════════════════════════════════════════════════════════
          SOURCE STRIP — EN HAUT, CLIQUABLE
      ══════════════════════════════════════════════════════════ */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.15em", fontWeight: 700, marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
          <span>Sources connectées</span>
          <span style={{ background: "#3e5c76", color: "#fff", borderRadius: 10, padding: "1px 8px", fontSize: 10 }}>
            {data.connected_sources}/{data.total_sources}
          </span>
        </div>
        <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4, scrollbarWidth: "none" }}>
          {Object.entries(data.by_source as Record<string, number>)
            .sort(([, a], [, b]) => b - a)
            .map(([src, count]) => {
              const m = SOURCE_META[src] ?? { label: src, icon: "·", color: "#748cab", description: "Messages" };
              const active = count > 0;
              return (
                <SourceCard
                  key={src}
                  meta={m}
                  count={count}
                  active={active}
                  onClick={() => router.push(`/dashboard/${src}`)}
                />
              );
            })}
        </div>
      </div>

      {/* ── Tabs ───────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 2, borderBottom: "2px solid rgba(62,92,118,0.12)", marginBottom: "1.75rem", overflowX: "auto" }}>
        {TABS.filter(tab => tab.id !== "team" || isManager).map(tab => {
          const isActive = activeTab === tab.id;
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
                color: isActive ? "#3e5c76" : hoveredTab === tab.id ? "#3e5c76" : "#748cab",
                borderBottom: isActive ? "2px solid #3e5c76" : hoveredTab === tab.id ? "2px solid rgba(62,92,118,0.35)" : "2px solid transparent",
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
          ONGLET 1 — VUE D'ENSEMBLE (Power BI Canvas)
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "overview" && (
        <div>

          {/* Executive summary */}
          <OrganizationHealthPanel sinceDays={sinceDays} />

          {/* BI Canvas */}
          <div style={{
            background: "var(--bg-canvas)",
            borderRadius: 20, padding: "1.75rem",
            border: "1px solid var(--border)",
            marginBottom: "1.5rem",
          }}>
            {/* Canvas title bar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.75rem", flexWrap: "wrap", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 4, height: 28, background: "linear-gradient(180deg,#3e5c76,#748cab)", borderRadius: 4 }} />
                <div>
                  <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.2em", fontWeight: 700 }}>
                    Tableau de bord analytique
                  </div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>
                    KPIs · Graphiques · Signaux
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 10, color: "#748cab", background: "#fff", border: "1px solid rgba(62,92,118,0.15)", borderRadius: 8, padding: "4px 10px" }}>
                  Période : {sinceDays === 1 ? "Aujourd'hui" : `${sinceDays} derniers jours`}
                </span>
                <span style={{ fontSize: 10, color: "#748cab", background: "#fff", border: "1px solid rgba(62,92,118,0.15)", borderRadius: 8, padding: "4px 10px" }}>
                  Cliquez sur un KPI → Drill-through ⤢
                </span>
              </div>
            </div>

            {/* ─ Section 1 : KPIs ─────────────────────────────── */}
            <CanvasSectionHeader icon="◈" label="Indicateurs Clés de Performance (KPIs)" />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(162px, 1fr))", gap: "0.875rem", marginBottom: "1.75rem" }}>
              <KPICard title={t.kpi_total} value={data.total_items}
                icon={<IconLayers size={18} />}
                subtitle={t.kpi_total_sub(data.since_days)}
                onClick={() => drill("total", "Messages totaux", data.total_items)} />

              <KPICard title={t.kpi_sources} value={`${data.connected_sources}/${data.total_sources}`}
                icon={<IconLink size={18} />}
                accent="#22c55e" subtitle={t.kpi_sources_sub}
                onClick={() => drill("sources", "Sources connectées", `${data.connected_sources}/${data.total_sources}`)} />

              <KPICard title={t.kpi_alerts} value={data.critical_alerts}
                icon={<IconAlertTriangle size={18} />}
                risk={data.critical_alerts > 5 ? "high" : data.critical_alerts > 2 ? "medium" : "low"}
                subtitle={t.kpi_alerts_sub}
                onClick={() => drill("alerts", "Alertes critiques", data.critical_alerts)} />

              <KPICard title={t.kpi_risk} value={`${data.risk_index}/100`}
                icon={<IconTarget size={18} />}
                risk={riskLevel} subtitle={t.kpi_risk_sub(riskLabel)}
                onClick={() => drill("risk", "Indice de risque", `${data.risk_index}/100`)} />

              <KPICard title={t.kpi_signals} value={intel.risk_count ?? 0}
                icon={<IconActivity size={18} />}
                risk={(intel.risk_count ?? 0) > 10 ? "high" : (intel.risk_count ?? 0) > 4 ? "medium" : "low"}
                subtitle={t.kpi_signals_sub(intel.risk_rate ?? 0)}
                onClick={() => drill("signals", "Signaux de risque", intel.risk_count ?? 0)} />

              <KPICard title={t.kpi_velocity} value={data.velocity.this_week}
                icon={<IconZap size={18} />}
                delta={Number(data.velocity.delta_pct)}
                subtitle={t.kpi_velocity_sub(data.velocity.last_week)}
                onClick={() => drill("velocity", "Vélocité hebdo", data.velocity.this_week)} />

              <KPICard title={t.kpi_sentiment} value={`${data.sentiment.positive}%`}
                icon={<IconSmile size={18} />}
                accent="#22c55e"
                subtitle={t.kpi_sentiment_sub(data.sentiment.negative, data.sentiment.neutral)}
                onClick={() => drill("sentiment", "Sentiment positif", `${data.sentiment.positive}%`)} />

              <KPICard title={t.kpi_nlp} value={`${intel.nlp_coverage ?? 0}%`}
                icon={<IconBrain size={18} />}
                accent={(intel.nlp_coverage ?? 0) > 80 ? "#22c55e" : "#f59e0b"}
                subtitle={(intel.nlp_coverage ?? 0) > 80 ? t.kpi_nlp_active : t.kpi_nlp_sync}
                onClick={() => drill("nlp", "Couverture NLP", `${intel.nlp_coverage ?? 0}%`)} />

              <KPICard title="Sentiment négatif" value={`${data.sentiment.negative}%`}
                icon={<IconTrendingDown size={18} />}
                risk={data.sentiment.negative > 30 ? "high" : data.sentiment.negative > 15 ? "medium" : "low"}
                subtitle={`${data.sentiment.neutral}% neutre dans la période`}
                onClick={() => drill("sentiment", "Analyse de sentiment", `${data.sentiment.negative}% négatif`)} />

              <KPICard
                title="Source principale"
                value={topSourceEntry ? topSourceEntry[0].charAt(0).toUpperCase() + topSourceEntry[0].slice(1) : "—"}
                icon={<IconStar size={18} />}
                accent={SOURCE_COLORS[topSourceEntry?.[0]] ?? "#3e5c76"}
                subtitle={topSourceEntry ? `${topSourceEntry[1]} messages` : "Aucune source active"}
                onClick={() => drill("total", "Répartition sources", topSourceEntry?.[0] ?? "—")} />

              <KPICard title="Items à risque" value={intel.at_risk_items?.length ?? 0}
                icon={<IconFlag size={18} />}
                risk={(intel.at_risk_items?.length ?? 0) > 5 ? "high" : (intel.at_risk_items?.length ?? 0) > 2 ? "medium" : "low"}
                subtitle="Messages nécessitant attention"
                onClick={() => drill("alerts", "Items à risque", intel.at_risk_items?.length ?? 0)} />

              <KPICard title="Taux de risque" value={`${intel.risk_rate ?? 0}%`}
                icon={<IconBarChart size={18} />}
                accent={(intel.risk_rate ?? 0) > 30 ? "#ef4444" : (intel.risk_rate ?? 0) > 15 ? "#f59e0b" : "#22c55e"}
                subtitle="Des messages analysés"
                onClick={() => drill("signals", "Taux de risque", `${intel.risk_rate ?? 0}%`)} />
            </div>

            {/* ─ Section 2 : Signal Board ────────────────────────────── */}
            <CanvasDivider />
            <CanvasSectionHeader icon="⚡" label="Tableau de bord des signaux" badge="Lié aux KPIs" />
            {intel.business_labels ? (
              <div style={{ background: "#fff", borderRadius: 16, overflow: "hidden", marginBottom: "0.25rem" }}>
                <SignalPanel data={intel} sinceDays={sinceDays} />
              </div>
            ) : (
              <div style={{ background: "#fff", borderRadius: 14, padding: "2rem", textAlign: "center", color: "#748cab", fontSize: 13, marginBottom: "0.25rem" }}>
                Aucune donnée de signaux — synchronisez vos sources
              </div>
            )}

            {/* ─ Section 3 : Charts ───────────────────────────── */}
            <CanvasDivider />
            <CanvasSectionHeader icon="◉" label="Analyse temporelle & Distribution" />

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
              <VisualCard title="Activité globale" sub="Messages par jour" accent="#3e5c76">
                <LineChart data={data.activity_timeline} height={140} />
              </VisualCard>
              <VisualCard title="Tendance des risques" sub="Blocked · Urgent · Conflict · Overload" accent="#ef4444">
                {intel.risk_trend?.length > 0
                  ? <LineChart data={intel.risk_trend} height={140} color="#ef4444" />
                  : <EmptyState text="Aucun signal de risque détecté" />
                }
              </VisualCard>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
              <VisualCard title="Volume par source" sub="Nombre de messages" accent="#3e5c76">
                <BarChart
                  data={Object.entries(data.by_source as Record<string, number>).map(([k, v]) => ({
                    label: k.charAt(0).toUpperCase() + k.slice(1),
                    value: v as number,
                    color: SOURCE_COLORS[k] ?? "#748cab",
                  }))}
                  height={130}
                />
              </VisualCard>
              <VisualCard title="Répartition sources" accent="#7B68EE">
                <DonutChart data={sourceSlices} size={145} label="items" />
              </VisualCard>
              <VisualCard title="Polarité" sub="Sentiment global" accent="#22c55e">
                <DonutChart data={sentimentSlices} size={145} label="msgs" />
              </VisualCard>
            </div>

            <VisualCard title="Heatmap des tensions" sub="Heure × Jour — tensions et frustrations détectées" accent="#8b5cf6">
              <HeatmapChart sinceDays={sinceDays} />
            </VisualCard>

            {/* ─ Section 4 : CEO Intelligence ────────────────── */}
            <CanvasDivider />
            <CanvasSectionHeader icon="🎯" label="Intelligence CEO" badge="IA" />

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
              <VisualCard title="Messages à lire maintenant" sub="Top 3 messages critiques" accent="#ef4444">
                <PriorityMessages sinceDays={sinceDays} />
              </VisualCard>
              <VisualCard title="Recommandations IA" sub="Actions suggérées par l'IA" accent="#3e5c76">
                <AIRecommendations sinceDays={sinceDays} />
              </VisualCard>
            </div>

            <div style={{ marginBottom: "1.75rem" }}>
              <VisualCard title="Attribution des alertes" sub="Qui génère le plus d'urgences ?" accent="#f97316">
                <AttributionPanel sinceDays={sinceDays} />
              </VisualCard>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          ONGLET 2 — ALERTES & RISQUES
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
          <AnomalyCard />
          <PriorityInbox sinceDays={sinceDays} />
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════
          ONGLET 3 — DÉCISIONS
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
      ══════════════════════════════════════════════════════════ */}
      {activeTab === "team" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: intel.burnout ? "1fr 1fr" : "1fr", gap: "1.5rem" }}>
            {intel.burnout ? (
              <BurnoutCard data={intel.burnout} />
            ) : (
              <div style={{ ...cardStyle, textAlign: "center", padding: "2.5rem", color: "#748cab" }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>🧘</div>
                <div style={{ fontWeight: 600 }}>Pas de signal de surcharge collectif</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>L'équipe semble opérer normalement</div>
              </div>
            )}
            <MLStatusCard />
          </div>
          <TeamOverloadCard sinceDays={sinceDays} />
        </div>
      )}

      <style>{`
        @keyframes slideInRight { from { transform: translateX(100%); } to { transform: translateX(0); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media print {
          aside, button, .no-print { display: none !important; }
          body { background: #fff !important; }
          #dashboard-print { margin: 0; padding: 0; }
        }
      `}</style>
    </div>
  );
}

/* ── Shared sub-components ───────────────────────────────────── */

const cardStyle: React.CSSProperties = {
  background: "var(--bg-card)", borderRadius: 16, padding: "1.5rem",
  boxShadow: "0 2px 12px var(--shadow-card)",
  border: "1px solid var(--border)",
};

function CanvasSectionHeader({ icon, label, badge }: { icon: string; label: string; badge?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "1.1rem" }}>
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
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${accent}, ${accent}44, transparent)` }} />
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: accent, textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>{title}</div>
        {sub && <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>{sub}</div>}
      </div>
      {children}
    </div>
  );
}

function SourceCard({ meta, count, active, onClick }: {
  meta: { label: string; icon: string; color: string; description: string };
  count: number; active: boolean; onClick: () => void;
}) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "10px 16px", background: active ? "#fff" : "#f8fafc",
        borderRadius: 14, flexShrink: 0, minWidth: 148,
        border: `1px solid ${hov ? meta.color + "55" : active ? meta.color + "28" : "rgba(62,92,118,0.1)"}`,
        boxShadow: hov ? `0 6px 20px ${meta.color}22` : active ? `0 2px 10px ${meta.color}12` : "none",
        cursor: "pointer",
        transform: hov ? "translateY(-2px)" : "none",
        transition: "all 0.18s",
      }}
    >
      <span style={{ fontSize: 22 }}>{meta.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: active ? "#0d1321" : "#748cab", whiteSpace: "nowrap" }}>
          {meta.label}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 1 }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
            background: active ? meta.color : "#94a3b8", display: "inline-block",
          }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: active ? meta.color : "#94a3b8" }}>
            {count} msgs
          </span>
        </div>
      </div>
      <span style={{ fontSize: 11, color: hov ? meta.color : "#748cab", transition: "color 0.15s" }}>→</span>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p style={{ color: "#748cab", fontSize: 13, paddingTop: 50, textAlign: "center" }}>{text}</p>;
}
