"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import API from "@/lib/api";
import KPICard from "@/components/KPICard";
import BarChart from "@/components/charts/BarChart";
import DonutChart from "@/components/charts/DonutChart";

const SOURCE_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  gmail: { label: "Gmail",  icon: "✉", color: "#EA4335" },
  slack: { label: "Slack",  icon: "#", color: "#4A154B" },
  jira:  { label: "Jira",   icon: "J", color: "#0052CC" },
};

const LABEL_COLORS: Record<string, string> = {
  IMPORTANT: "#f59e0b", STARRED: "#3b82f6", SENT: "#22c55e",
  SPAM: "#ef4444", DRAFT: "#94a3b8", PERSONAL: "#8b5cf6",
  CATEGORY_PROMOTIONS: "#f97316", CATEGORY_UPDATES: "#06b6d4",
};

const PERIOD_OPTIONS = [7, 30, 90];

export default function SourceDashboard() {
  const { source } = useParams<{ source: string }>();
  const config = SOURCE_CONFIG[source] ?? { label: source, icon: "◈", color: "#748cab" };

  const [sinceDays, setSinceDays] = useState(30);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  // ── Gmail-specific derived data ────────────────────────────
  const isGmail = source === "gmail" && !!data.threads;

  const senderSlices = isGmail
    ? data.top_senders?.slice(0, 5).map((s: any, i: number) => ({
        label: s.name.split(" ")[0],
        value: s.count,
        color: ["#EA4335","#3e5c76","#f59e0b","#22c55e","#8b5cf6"][i],
      }))
    : data.top_authors?.slice(0, 5).map((a: any, i: number) => ({
        label: a.name.split(" ")[0] ?? a.name,
        value: a.count,
        color: ["#4A154B","#3e5c76","#f59e0b","#22c55e","#0052CC"][i],
      }));

  const labelSlices = isGmail
    ? data.label_distribution?.map((l: any) => ({
        label: l.label,
        value: l.count,
        color: LABEL_COLORS[l.label] ?? "#748cab",
      }))
    : null;

  const sentimentSlices = [
    { label: "Positif",  value: data.sentiment.positive, color: "#22c55e" },
    { label: "Neutre",   value: data.sentiment.neutral,  color: "#94a3b8" },
    { label: "Négatif",  value: data.sentiment.negative, color: "#ef4444" },
  ];

  const byDayData = data.by_day?.map((d: any) => ({ label: d.day, value: d.count })) ?? [];

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "2rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: config.color, marginBottom: 6, fontWeight: 600 }}>
            {config.icon} {config.label} Analytics
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 28, color: "#0d1321" }}>
            Analyse {config.label}
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginTop: 4 }}>
            {data.volume.total} items analysés · Mis à jour {new Date(data.computed_at).toLocaleString("fr-FR")}
          </p>
        </div>

        {/* Period filter */}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {PERIOD_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setSinceDays(d)}
              style={{
                padding: "6px 14px", borderRadius: 20, cursor: "pointer",
                border: `1px solid ${sinceDays === d ? config.color : "rgba(62,92,118,0.2)"}`,
                background: sinceDays === d ? config.color : "transparent",
                color: sinceDays === d ? "#fff" : "#748cab",
                fontSize: 12, fontWeight: sinceDays === d ? 600 : 400,
              }}
            >
              {d}j
            </button>
          ))}
        </div>
      </div>

      {/* KPI Row 1 — Volume & Engagement */}
      <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 10 }}>
        Volume &amp; Engagement
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "1rem", marginBottom: "1.75rem" }}>
        <KPICard title={`${config.label} reçus (sem.)`} value={data.volume.this_week} icon="📥"
          delta={data.volume.delta_pct} accent={config.color}
          subtitle={`Sem. passée : ${data.volume.last_week}`} />
        <KPICard title="Total items" value={data.volume.total} icon="📦"
          accent={config.color} subtitle={`Sur ${sinceDays} derniers jours`} />
        {isGmail && (
          <>
            <KPICard title="Non lus" value={data.unread.count} icon="🔴"
              risk={data.unread.rate > 40 ? "high" : data.unread.rate > 20 ? "medium" : "low"}
              subtitle={`${data.unread.rate}% du total`} />
            <KPICard title="Marqués importants" value={data.important.count} icon="⭐"
              accent="#f59e0b" subtitle={`${data.important.rate}% du total`} />
            <KPICard title="Expéditeurs uniques" value={data.unique_senders} icon="👤"
              accent="#3e5c76" subtitle="Sources distinctes" />
            <KPICard title="Threads actifs" value={data.threads.total} icon="🧵"
              accent="#3e5c76" subtitle={`Moy. ${data.threads.avg_length} msg/thread`} />
          </>
        )}
        {!isGmail && (
          <KPICard title="Alertes critiques" value={data.critical_alerts} icon="⚠"
            risk={data.critical_alerts > 5 ? "high" : data.critical_alerts > 2 ? "medium" : "low"}
            subtitle="Mots clés d'escalade" />
        )}
      </div>

      {/* KPI Row 2 — Risques (Gmail only) */}
      {isGmail && (
        <>
          <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, marginBottom: 10 }}>
            Risques &amp; Alertes décisionnelles
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "1rem", marginBottom: "1.75rem" }}>
            <KPICard title="Mots d'escalade" value={data.escalation.count} icon="🚨"
              risk={data.escalation.count > 5 ? "high" : data.escalation.count > 2 ? "medium" : "low"}
              subtitle="urgent · ASAP · critical" />
            <KPICard title="Sans réponse +48h" value={data.no_reply_48h.count} icon="⏰"
              risk={data.no_reply_48h.count > 5 ? "high" : data.no_reply_48h.count > 2 ? "medium" : "low"}
              subtitle="Emails importants non traités" />
            <KPICard title="Critiques non résolus" value={data.unanswered_critical.count} icon="❗"
              risk={data.unanswered_critical.count > 0 ? "high" : "low"}
              subtitle="Escalade + aucune réponse" />
            <KPICard title="Threads longs" value={data.threads.long_count} icon="🔁"
              risk={data.threads.long_count > 5 ? "medium" : "low"}
              subtitle="+3 échanges = risque désalignement" />
            <KPICard title="Score back-and-forth" value={`${data.threads.back_and_forth_score}/10`} icon="↔"
              risk={data.threads.back_and_forth_score > 6 ? "high" : data.threads.back_and_forth_score > 3 ? "medium" : "low"}
              subtitle="Intensité des échanges" />
            <KPICard title="Tps réponse moyen" icon="⚡"
              value={data.avg_response_hours ? `${data.avg_response_hours}h` : "N/A"}
              accent="#3e5c76"
              subtitle={data.avg_response_hours ? "Basé sur les threads" : "Dossier envoyé requis"} />
          </div>
        </>
      )}

      {/* Charts Row 1 — Activity + Senders */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
            Activité par jour (7 jours)
          </div>
          <BarChart data={byDayData} height={140} color={config.color} />
        </div>

        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
            {isGmail ? "Top expéditeurs" : "Top auteurs"}
          </div>
          {senderSlices?.length > 0
            ? <DonutChart data={senderSlices} size={150} label="items" />
            : <p style={{ color: "#748cab", fontSize: 13 }}>Pas de données</p>}
        </div>
      </div>

      {/* Charts Row 2 — Sentiment + Labels/Hour */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
            Analyse sentimentale
          </div>
          <DonutChart data={sentimentSlices} size={150} label="items" />
        </div>

        {isGmail && labelSlices?.length > 0 && (
          <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
              Distribution des labels
            </div>
            <DonutChart data={labelSlices} size={150} label="labels" />
          </div>
        )}

        {isGmail && data.by_hour && (
          <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
            <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
              Pic d&apos;activité par heure (6h–22h)
            </div>
            <BarChart
              data={data.by_hour.slice(6, 22).map((d: any) => ({ label: `${d.hour}h`, value: d.count }))}
              height={140} color="#3e5c76"
            />
          </div>
        )}
      </div>

      {/* Alertes escalade (Gmail) */}
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

      {/* Threads longs (Gmail) */}
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
              <div style={{ fontSize: 13, color: "#0d1321" }}>{t.subject.slice(0, 60)}...</div>
              <span style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", flexShrink: 0, marginLeft: 12 }}>{t.message_count} messages</span>
            </div>
          ))}
        </div>
      )}

      {/* Keywords */}
      {data.keyword_frequency?.length > 0 && (
        <div style={{ background: "#fff", borderRadius: 16, padding: "1.5rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 16 }}>
            Mots-clés fréquents
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {data.keyword_frequency.map((k: any, i: number) => (
              <span key={i} style={{
                padding: "4px 12px", borderRadius: 100,
                background: `rgba(62,92,118,${0.08 + (1 - i / data.keyword_frequency.length) * 0.12})`,
                color: "#3e5c76", fontSize: 12, fontWeight: 500,
              }}>
                {k.word} <span style={{ color: "#748cab", fontSize: 11 }}>{k.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
