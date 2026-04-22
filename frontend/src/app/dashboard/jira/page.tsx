"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import KPICard from "@/components/KPICard";
import BarChart from "@/components/charts/BarChart";
import DonutChart from "@/components/charts/DonutChart";
import SignalPanel from "@/components/intelligence/SignalPanel";
import RiskFeed from "@/components/intelligence/RiskFeed";

const JIRA_COLOR = "#0052CC";
const PERIOD_OPTIONS = [7, 30, 90];
const TABS = ["Overview", "Flow", "Quality", "Predictive"] as const;
type Tab = typeof TABS[number];

// ── Helpers ──────────────────────────────────────────────

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div style={{ display: "flex", gap: 4, marginBottom: "1.75rem", borderBottom: "1px solid rgba(62,92,118,0.12)", paddingBottom: 0 }}>
      {TABS.map(tab => (
        <button key={tab} onClick={() => onChange(tab)} style={{
          padding: "10px 20px", border: "none", background: "transparent",
          cursor: "pointer", fontSize: 13, fontWeight: active === tab ? 700 : 400,
          color: active === tab ? JIRA_COLOR : "#748cab",
          borderBottom: active === tab ? `2px solid ${JIRA_COLOR}` : "2px solid transparent",
          marginBottom: -1, fontFamily: "DM Sans, sans-serif",
          transition: "all 0.15s ease",
        }}>{tab}</button>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "1.75rem" }}>
      <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 12 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    "Done":        { bg: "rgba(34,197,94,0.1)",  text: "#16a34a" },
    "In Progress": { bg: "rgba(59,130,246,0.1)", text: "#2563eb" },
    "To Do":       { bg: "rgba(148,163,184,0.1)", text: "#64748b" },
  };
  const c = colors[status] ?? { bg: "rgba(245,158,11,0.1)", text: "#d97706" };
  return (
    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: c.bg, color: c.text, fontWeight: 600 }}>
      {status}
    </span>
  );
}

function PriorityDot({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    Highest: "#ef4444", High: "#f97316", Medium: "#f59e0b", Low: "#22c55e", Lowest: "#94a3b8",
  };
  return <span style={{ width: 8, height: 8, borderRadius: "50%", background: colors[priority] ?? "#94a3b8", display: "inline-block", marginRight: 6 }} />;
}

// ── Tabs ─────────────────────────────────────────────────

function TabOverview({ data }: { data: any }) {
  const kpis = data.kpis ?? {};
  const statusDist = data.status_distribution ?? [];
  const priorityDist = data.priority_distribution ?? [];
  const typeDist = data.type_distribution ?? [];

  const statusData = statusDist.map((s: any) => ({ label: s.status, value: s.count }));
  const priorityData = priorityDist.map((p: any) => ({ label: p.priority, value: p.count }));

  return (
    <>
      <Section title="KPIs Projet">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(175px, 1fr))", gap: "1rem" }}>
          <KPICard title="Total Issues" value={kpis.total ?? 0} icon="📦" accent={JIRA_COLOR} subtitle="Toutes périodes" />
          <KPICard title="Done" value={kpis.done ?? 0} icon="✅" accent="#22c55e"
            subtitle={`${kpis.delivery_rate ?? 0}% livré`} />
          <KPICard title="In Progress" value={kpis.in_progress ?? 0} icon="⚡" accent="#3b82f6"
            subtitle="En cours" />
          <KPICard title="Open" value={kpis.open ?? 0} icon="🔵" accent="#94a3b8"
            subtitle="À faire" />
          <KPICard title="Bloquées" value={kpis.blocked ?? 0} icon="🚫"
            risk={kpis.blocked > 2 ? "high" : kpis.blocked > 0 ? "medium" : "low"}
            subtitle="Priorité Highest" />
          <KPICard title="Velocity" value={`${kpis.velocity_sp ?? 0} SP`} icon="🚀" accent={JIRA_COLOR}
            subtitle="Story points livrés" />
          <KPICard title="Sprint Pred." value={`${kpis.sprint_predictability ?? 0}%`} icon="🎯"
            risk={kpis.sprint_predictability < 50 ? "high" : kpis.sprint_predictability < 75 ? "medium" : "low"}
            subtitle={`${kpis.done_sp ?? 0} / ${kpis.total_sp ?? 0} SP`} />
          <KPICard title="Bugs" value={kpis.bugs ?? 0} icon="🐞"
            risk={kpis.bug_rate > 30 ? "high" : kpis.bug_rate > 15 ? "medium" : "low"}
            subtitle={`${kpis.bug_rate ?? 0}% du total`} />
          <KPICard title="Delivery Rate" value={`${kpis.delivery_rate ?? 0}%`} icon="📦" accent="#22c55e"
            subtitle="Issues terminées" />
          {kpis.avg_cycle_time_days && (
            <KPICard title="Cycle Time" value={`${kpis.avg_cycle_time_days}j`} icon="⏱" accent="#8b5cf6"
              subtitle="Durée moyenne" />
          )}
        </div>
      </Section>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Issues par statut</div>
          {statusData.length > 0
            ? <DonutChart data={statusDist.map((s: any) => ({ label: s.status, value: s.count, color: s.color }))} size={130} label="issues" />
            : <p style={{ color: "#748cab", fontSize: 13 }}>Pas de données</p>}
        </div>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Issues par priorité</div>
          {priorityData.length > 0
            ? <DonutChart data={priorityDist.map((p: any) => ({ label: p.priority, value: p.count, color: p.color }))} size={130} label="issues" />
            : <p style={{ color: "#748cab", fontSize: 13 }}>Pas de données</p>}
        </div>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Issues par type</div>
          {typeDist.length > 0
            ? <DonutChart data={typeDist.map((t: any) => ({ label: t.type, value: t.count, color: t.color }))} size={130} label="issues" />
            : <p style={{ color: "#748cab", fontSize: 13 }}>Pas de données</p>}
        </div>
      </div>

      {data.intelligence?.business_labels && (
        <div style={{ marginTop: "1.75rem" }}>
          <SignalPanel data={data.intelligence} />
        </div>
      )}
    </>
  );
}

function TabFlow({ data }: { data: any }) {
  const kpis = data.kpis ?? {};
  const byDay = data.by_day ?? [];
  const topAuthors = data.top_authors ?? [];

  const byDayData = byDay.map((d: any) => ({ label: d.day, value: d.count }));
  const authorData = topAuthors.slice(0, 6).map((a: any, i: number) => ({
    label: (a.name || "?").split(" ")[0], value: a.count,
    color: ["#0052CC", "#3b82f6", "#8b5cf6", "#22c55e", "#f59e0b", "#ef4444"][i],
  }));

  return (
    <>
      <Section title="Flow KPIs">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(175px, 1fr))", gap: "1rem" }}>
          <KPICard title="WIP" value={kpis.in_progress ?? 0} icon="⚙️" accent="#3b82f6"
            subtitle="Work In Progress" />
          <KPICard title="Remaining SP" value={kpis.remaining_sp ?? 0} icon="📊" accent={JIRA_COLOR}
            subtitle="Points restants" />
          <KPICard title="Cycle Time" value={kpis.avg_cycle_time_days ? `${kpis.avg_cycle_time_days}j` : "N/A"} icon="⏱" accent="#8b5cf6"
            subtitle="Durée moy. (Done)" />
          <KPICard title="Delivery Rate" value={`${kpis.delivery_rate ?? 0}%`} icon="🚀" accent="#22c55e"
            subtitle="Taux de livraison" />
        </div>
      </Section>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Activité (7 jours)</div>
          <BarChart data={byDayData} height={140} color={JIRA_COLOR} />
        </div>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Performance équipe</div>
          {authorData.length > 0
            ? <DonutChart data={authorData} size={130} label="issues" />
            : <p style={{ color: "#748cab", fontSize: 13 }}>Pas de données</p>}
        </div>
      </div>

      {/* Story Points breakdown */}
      <div style={{ marginTop: "1.5rem", background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
        <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Story Points — Avancement Sprint</div>
        <div style={{ display: "flex", gap: "2rem", alignItems: "center" }}>
          {[
            { label: "Done", value: kpis.done_sp ?? 0, color: "#22c55e" },
            { label: "In Progress", value: kpis.in_progress ? (kpis.total_sp - kpis.done_sp - kpis.remaining_sp) : 0, color: "#3b82f6" },
            { label: "Remaining", value: kpis.remaining_sp ?? 0, color: "#94a3b8" },
          ].map(item => (
            <div key={item.label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: item.color }}>{item.value}</div>
              <div style={{ fontSize: 12, color: "#748cab", marginTop: 4 }}>{item.label}</div>
            </div>
          ))}
          <div style={{ flex: 1, height: 12, background: "#f1f5f9", borderRadius: 6, overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 6,
              background: `linear-gradient(90deg, #22c55e ${kpis.sprint_predictability ?? 0}%, #94a3b8 0%)`,
              transition: "width 0.5s ease",
            }} />
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: JIRA_COLOR }}>{kpis.sprint_predictability ?? 0}%</div>
        </div>
      </div>
    </>
  );
}

function TabQuality({ data }: { data: any }) {
  const kpis = data.kpis ?? {};
  const typeDist = data.type_distribution ?? [];
  const priorityDist = data.priority_distribution ?? [];
  const keywords = data.keyword_frequency ?? [];

  return (
    <>
      <Section title="Quality KPIs">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(175px, 1fr))", gap: "1rem" }}>
          <KPICard title="Total Bugs" value={kpis.bugs ?? 0} icon="🐞"
            risk={kpis.bugs > 3 ? "high" : kpis.bugs > 1 ? "medium" : "low"}
            subtitle="Issues de type Bug" />
          <KPICard title="Bug Rate" value={`${kpis.bug_rate ?? 0}%`} icon="📉"
            risk={kpis.bug_rate > 30 ? "high" : kpis.bug_rate > 15 ? "medium" : "low"}
            subtitle="% bugs / total" />
          <KPICard title="Haute Priorité" value={kpis.high_priority_count ?? 0} icon="🔴"
            risk={kpis.high_priority_count > 3 ? "high" : kpis.high_priority_count > 1 ? "medium" : "low"}
            subtitle="High + Highest" />
          <KPICard title="Cycle Time" value={kpis.avg_cycle_time_days ? `${kpis.avg_cycle_time_days}j` : "N/A"} icon="⏱" accent="#8b5cf6"
            subtitle="Résolution moy." />
        </div>
      </Section>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Bugs vs Features vs Tasks</div>
          <DonutChart data={typeDist.map((t: any) => ({ label: t.type, value: t.count, color: t.color }))} size={130} label="issues" />
        </div>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Distribution des priorités</div>
          <DonutChart data={priorityDist.map((p: any) => ({ label: p.priority, value: p.count, color: p.color }))} size={130} label="issues" />
        </div>
      </div>

      {keywords.length > 0 && (
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>Mots-clés fréquents</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {keywords.map((k: any, i: number) => (
              <span key={i} style={{
                padding: "4px 12px", borderRadius: 100,
                background: `rgba(0,82,204,${0.06 + (1 - i / keywords.length) * 0.1})`,
                color: JIRA_COLOR, fontSize: 12, fontWeight: 500,
              }}>
                {k.word} <span style={{ color: "#748cab", fontSize: 11 }}>{k.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function TabPredictive({ data }: { data: any }) {
  const kpis = data.kpis ?? {};
  const riskyIssues = data.risky_issues ?? [];

  return (
    <>
      <Section title="Risk KPIs">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(175px, 1fr))", gap: "1rem" }}>
          <KPICard title="Risk Score" value={`${kpis.risk_score ?? 0}/100`} icon="⚠️"
            risk={kpis.risk_score > 50 ? "high" : kpis.risk_score > 25 ? "medium" : "low"}
            subtitle="Score global projet" />
          <KPICard title="Issues Bloquées" value={kpis.blocked ?? 0} icon="🚫"
            risk={kpis.blocked > 0 ? "high" : "low"}
            subtitle="Priorité Highest" />
          <KPICard title="Haute Priorité" value={kpis.high_priority_count ?? 0} icon="🔴"
            risk={kpis.high_priority_count > 3 ? "high" : "medium"}
            subtitle="Attention requise" />
          <KPICard title="Sprint Pred." value={`${kpis.sprint_predictability ?? 0}%`} icon="🎯"
            risk={kpis.sprint_predictability < 50 ? "high" : "low"}
            subtitle={`${kpis.done_sp ?? 0} SP livrés`} />
        </div>
      </Section>

      {/* Risk Matrix visuelle */}
      <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(239,68,68,0.15)", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span style={{ fontSize: 16 }}>⚠️</span>
          <div style={{ fontSize: 12, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
            Issues à Risque — Action Requise
          </div>
        </div>
        {riskyIssues.length > 0 ? riskyIssues.map((issue: any, i: number) => (
          <div key={i} style={{ padding: "12px 16px", background: "#fef2f2", borderRadius: 10, marginBottom: 8, borderLeft: "3px solid #ef4444", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: "#748cab", fontWeight: 600 }}>{issue.key}</span>
                <StatusBadge status={issue.status} />
                <PriorityDot priority={issue.priority} />
                <span style={{ fontSize: 11, color: "#748cab" }}>{issue.priority}</span>
                {issue.type === "Bug" && <span style={{ fontSize: 10, background: "rgba(239,68,68,0.1)", color: "#ef4444", padding: "1px 6px", borderRadius: 4, fontWeight: 700 }}>BUG</span>}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{(issue.title || "").replace(/^\[.*?\]\s*/, "").slice(0, 70)}</div>
              <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                {issue.reasons?.join(" · ")}
              </div>
            </div>
            {issue.sp && <div style={{ fontSize: 12, fontWeight: 700, color: JIRA_COLOR, marginLeft: 12 }}>{issue.sp} SP</div>}
          </div>
        )) : (
          <p style={{ color: "#22c55e", fontSize: 13, textAlign: "center", padding: "1rem" }}>Aucune issue à risque détectée</p>
        )}
      </div>

      {data.intelligence?.at_risk_items?.length > 0 && (
        <RiskFeed items={data.intelligence.at_risk_items} title="Signaux Intelligence — Jira" />
      )}
    </>
  );
}

// ── Main Page ─────────────────────────────────────────────

export default function JiraDashboard() {
  const [sinceDays, setSinceDays] = useState(30);
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [data, setData]     = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    API.get(`/api/analytics/jira?since_days=${sinceDays}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  }, [sinceDays]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: 36, height: 36, border: `3px solid ${JIRA_COLOR}33`, borderTop: `3px solid ${JIRA_COLOR}`, borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        <p style={{ color: "#748cab", fontSize: 13 }}>Analyse Jira...</p>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ background: "#fef2f2", border: "1px solid #ef4444", borderRadius: 12, padding: "1.5rem", color: "#ef4444" }}>
      <strong>Erreur :</strong> {error}
    </div>
  );
  if (!data) return null;

  return (
    <div>
      {/* ── Header ─────────────────────────────────────── */}
      <div style={{ marginBottom: "2rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: JIRA_COLOR, marginBottom: 6, fontWeight: 600 }}>
            J Jira Analytics
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 28, color: "#0d1321" }}>
            Analyse Jira
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginTop: 4 }}>
            {data.volume?.total ?? 0} issues · Mis à jour {new Date(data.computed_at).toLocaleString("fr-FR")}
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {PERIOD_OPTIONS.map(d => (
            <button key={d} onClick={() => setSinceDays(d)} style={{
              padding: "6px 14px", borderRadius: 20, cursor: "pointer",
              border: `1px solid ${sinceDays === d ? JIRA_COLOR : "rgba(62,92,118,0.2)"}`,
              background: sinceDays === d ? JIRA_COLOR : "transparent",
              color: sinceDays === d ? "#fff" : "#748cab",
              fontSize: 12, fontWeight: sinceDays === d ? 600 : 400,
            }}>{d}j</button>
          ))}
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────── */}
      <TabBar active={activeTab} onChange={setActiveTab} />

      {/* ── Tab Content ─────────────────────────────────── */}
      {activeTab === "Overview"   && <TabOverview   data={data} />}
      {activeTab === "Flow"       && <TabFlow       data={data} />}
      {activeTab === "Quality"    && <TabQuality    data={data} />}
      {activeTab === "Predictive" && <TabPredictive data={data} />}
    </div>
  );
}
