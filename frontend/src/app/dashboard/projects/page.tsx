"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getUser, isCEO } from "@/lib/auth";

interface Project {
  id: string;
  name: string;
  description?: string;
  color: string;
  created_by: string;
  status: "on_track" | "at_risk" | "off_track";
  progress: number;
  created_at: string;
  updated_at: string;
  members: { id: number; name: string; role: string }[];
  sources: { id: number; source_type: string }[];
  notes_count: number;
  files_count: number;
  blockers: number;
  risk_level: string;
  sentiment: string;
}

const STATUS_META = {
  on_track:  { label: "ON TRACK",  color: "#16a34a", bg: "#f0fdf4", border: "#86efac" },
  at_risk:   { label: "AT RISK",   color: "#d97706", bg: "#fffbeb", border: "#fde68a" },
  off_track: { label: "OFF TRACK", color: "#dc2626", bg: "#fef2f2", border: "#fecaca" },
};

const SOURCE_ABBREV: Record<string, string> = {
  onedrive: "OD", teams: "TM", clickup: "CU", gmail: "GM", slack: "SL", outlook: "OL",
};
const SOURCE_COLOR: Record<string, string> = {
  onedrive: "#0078D4", teams: "#6264A7", clickup: "#7B68EE",
  gmail: "#EA4335", slack: "#4A154B", outlook: "#0078D4",
};

const SENTIMENT_COLOR: Record<string, string> = {
  Positive: "#16a34a", Neutral: "#d97706", Negative: "#dc2626",
};

const RISK_COLOR: Record<string, string> = {
  Low: "#16a34a", Medium: "#d97706", High: "#dc2626",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

export default function ProjectsPage() {
  const router = useRouter();
  const { t, locale } = useI18n();
  const currentUser = getUser();
  const canCreate   = currentUser ? isCEO(currentUser) : false;
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState<"all" | "on_track" | "at_risk" | "off_track">("all");

  useEffect(() => {
    API.get("/api/projects")
      .then(r => setProjects(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = filter === "all" ? projects : projects.filter(p => p.status === filter);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", flexDirection: "column", gap: 12 }}>
      <div style={{ width: 32, height: 32, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes fadeUp { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:translateY(0) } }
        @keyframes spin   { to { transform:rotate(360deg) } }
        .pcard { transition: box-shadow 0.2s ease, transform 0.2s ease; cursor: pointer; }
        .pcard:hover { transform: translateY(-2px); box-shadow: 0 16px 40px rgba(13,19,33,0.1) !important; }
        .new-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(29,45,68,0.3) !important; }
        .filter-btn:hover { background: rgba(62,92,118,0.08) !important; }
      `}</style>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: "2rem", animation: "fadeUp 0.3s ease" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase", color: "#748cab", fontWeight: 600, marginBottom: 6 }}>
            {locale === "fr" ? "Espace de travail" : "Workspace"}
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 30, color: "#0d1321", margin: 0, lineHeight: 1.1 }}>
            {locale === "fr" ? "Mes projets" : "My Projects"}
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginTop: 6 }}>
            {projects.length === 0
              ? (locale === "fr" ? "Aucun projet" : "No projects yet")
              : `${projects.length} projet${projects.length > 1 ? "s" : ""}`
            }
          </p>
        </div>
        {canCreate && (
          <button
            className="new-btn"
            onClick={() => router.push("/dashboard/projects/new")}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "linear-gradient(135deg, #1d2d44, #3e5c76)",
              color: "#f0ebd8", border: "none", borderRadius: 11,
              padding: "11px 22px", fontSize: 13, fontWeight: 600,
              cursor: "pointer", fontFamily: "DM Sans, sans-serif",
              boxShadow: "0 4px 14px rgba(29,45,68,0.2)", transition: "all 0.2s",
            }}
          >
            <span style={{ fontSize: 16 }}>＋</span>
            {locale === "fr" ? "Nouveau projet" : "New Project"}
          </button>
        )}
      </div>

      {/* ── Filter tabs ─────────────────────────────────────────────── */}
      {projects.length > 0 && (
        <div style={{ display: "flex", gap: 6, marginBottom: "1.75rem" }}>
          {(["all", "on_track", "at_risk", "off_track"] as const).map(f => {
            const isActive = filter === f;
            const meta = f !== "all" ? STATUS_META[f] : null;
            const count = f === "all" ? projects.length : projects.filter(p => p.status === f).length;
            return (
              <button
                key={f}
                className="filter-btn"
                onClick={() => setFilter(f)}
                style={{
                  padding: "6px 14px", borderRadius: 20, cursor: "pointer", transition: "all 0.15s",
                  border: `1px solid ${isActive ? (meta?.border ?? "#3e5c76") : "rgba(62,92,118,0.18)"}`,
                  background: isActive ? (meta?.bg ?? "#3e5c76") : "transparent",
                  color: isActive ? (meta?.color ?? "#fff") : "#748cab",
                  fontSize: 12, fontWeight: isActive ? 700 : 400,
                  display: "flex", alignItems: "center", gap: 6,
                }}
              >
                {f === "all" ? "Tous" : meta!.label}
                <span style={{ fontSize: 11, background: "rgba(0,0,0,0.08)", borderRadius: 10, padding: "0 5px" }}>{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────── */}
      {projects.length === 0 ? (
        <div style={{ textAlign: "center", padding: "5rem 2rem", animation: "fadeUp 0.4s ease", background: "#fff", borderRadius: 20, border: "1px dashed rgba(62,92,118,0.2)" }}>
          <div style={{ width: 64, height: 64, borderRadius: 20, background: "rgba(62,92,118,0.07)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1.25rem" }}>
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#3e5c76" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          </div>
          <h2 style={{ fontFamily: "DM Serif Display, serif", fontSize: 24, color: "#0d1321", marginBottom: 10 }}>
            {locale === "fr" ? "Aucun projet pour l'instant" : "No projects yet"}
          </h2>
          <p style={{ color: "#748cab", fontSize: 14, marginBottom: "2rem", maxWidth: 380, margin: "0 auto 2rem" }}>
            {locale === "fr" ? "Créez votre premier projet pour commencer à suivre l'avancement." : "Create your first project to start tracking progress."}
          </p>
          <button className="new-btn" onClick={() => router.push("/dashboard/projects/new")} style={{
            background: "linear-gradient(135deg, #1d2d44, #3e5c76)", color: "#f0ebd8",
            border: "none", borderRadius: 11, padding: "13px 32px", fontSize: 14,
            fontWeight: 600, cursor: "pointer", transition: "all 0.2s",
          }}>
            {locale === "fr" ? "Créer un projet" : "Create a project"}
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1.25rem", animation: "fadeUp 0.3s ease" }}>
          {filtered.map(p => <ProjectCard key={p.id} project={p} onClick={() => router.push(`/dashboard/projects/${p.id}`)} />)}
        </div>
      )}
    </div>
  );
}

function healthScore(p: Project): { score: number; label: string; color: string } {
  if (p.status === "off_track" || p.risk_level === "High")
    return { score: Math.max(10, 40 - p.blockers * 5), label: "Critique", color: "#ef4444" };
  if (p.status === "at_risk"   || p.risk_level === "Medium")
    return { score: Math.min(65, 55 + p.progress / 10), label: "Tendu",   color: "#f59e0b" };
  return   { score: Math.min(99, 70 + p.progress / 10), label: "Sain",    color: "#22c55e" };
}

function ProjectCard({ project: p, onClick }: { project: Project; onClick: () => void }) {
  const status = STATUS_META[p.status] ?? STATUS_META.on_track;
  const progressColor = p.progress >= 70 ? "#16a34a" : p.progress >= 40 ? "#d97706" : "#ef4444";
  const owner = p.members.find(m => m.role === "owner") ?? p.members[0];
  const ownerName = owner?.name ?? p.created_by ?? "CEO";
  const health = healthScore(p);

  return (
    <div
      className="pcard"
      onClick={onClick}
      style={{
        background: "#fff", borderRadius: 16, overflow: "hidden",
        border: "1px solid rgba(62,92,118,0.09)",
        boxShadow: "0 2px 12px rgba(13,19,33,0.06)",
      }}
    >
      {/* Color bar */}
      <div style={{ height: 4, background: p.color }} />

      <div style={{ padding: "1.25rem 1.4rem" }}>

        {/* ── Row 1: Title + Status badge ── */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, marginBottom: "0.6rem" }}>
          <h3 style={{ fontFamily: "DM Serif Display, serif", fontSize: 16, color: "#0d1321", margin: 0, lineHeight: 1.3, flex: 1 }}>
            {p.name}
          </h3>
          <span style={{
            fontSize: 10, fontWeight: 800, letterSpacing: "0.08em",
            padding: "3px 9px", borderRadius: 20, whiteSpace: "nowrap", flexShrink: 0,
            background: status.bg, color: status.color, border: `1px solid ${status.border}`,
          }}>
            {status.label}
          </span>
        </div>

        {/* ── Row 2: Owner + Last updated ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "0.75rem" }}>
          <div style={{ width: 22, height: 22, borderRadius: "50%", background: "#1d2d44", color: "#f0ebd8", fontSize: 10, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            {ownerName[0]?.toUpperCase()}
          </div>
          <span style={{ fontSize: 12, color: "#748cab", fontWeight: 500 }}>{ownerName}</span>
          <span style={{ fontSize: 11, color: "#c0cdd8", marginLeft: "auto" }}>
            Updated {timeAgo(p.updated_at ?? p.created_at)}
          </span>
        </div>

        {/* ── Row 3: Description ── */}
        <p style={{
          fontSize: 12, color: "#748cab", lineHeight: 1.6, margin: "0 0 1rem",
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          minHeight: 38,
        }}>
          {p.description ?? <span style={{ fontStyle: "italic", color: "#c0cdd8" }}>Aucune description</span>}
        </p>

        {/* ── Row 4: Health Score ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: "1rem", padding: "10px 12px", borderRadius: 12, background: `${health.color}09`, border: `1px solid ${health.color}25` }}>
          <div style={{ position: "relative", width: 44, height: 44, flexShrink: 0 }}>
            <svg width="44" height="44" viewBox="0 0 44 44">
              <circle cx="22" cy="22" r="18" fill="none" stroke="rgba(62,92,118,0.1)" strokeWidth="4" />
              <circle cx="22" cy="22" r="18" fill="none" stroke={health.color} strokeWidth="4"
                strokeDasharray={`${(health.score / 100) * 113} 113`}
                strokeLinecap="round"
                transform="rotate(-90 22 22)" />
            </svg>
            <span style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 800, color: health.color }}>
              {health.score}
            </span>
          </div>
          <div>
            <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600, marginBottom: 2 }}>Score Santé</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: health.color, display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: health.color, display: "inline-block", flexShrink: 0 }} />
              {health.label}
            </div>
          </div>
          <div style={{ marginLeft: "auto", textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 2 }}>Progress</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: progressColor }}>{p.progress}%</div>
          </div>
        </div>

        {/* ── Row 5: Progress bar ── */}
        <div style={{ marginBottom: "1rem" }}>
          <div style={{ height: 5, background: "rgba(62,92,118,0.08)", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${p.progress}%`, background: progressColor, borderRadius: 6, transition: "width 0.6s ease" }} />
          </div>
        </div>

        {/* ── Row 5: Metrics footer ── */}
        <div style={{ display: "flex", alignItems: "center", paddingTop: "0.75rem", borderTop: "1px solid rgba(62,92,118,0.07)", flexWrap: "wrap", gap: 4 }}>
          <MetricItem label={`${p.blockers} blocker${p.blockers !== 1 ? "s" : ""}`} color={p.blockers > 0 ? "#ef4444" : "#748cab"} />
          <Dot />
          <MetricItem label={`Risk: ${p.risk_level}`} color={RISK_COLOR[p.risk_level] ?? "#748cab"} />
          <Dot />
          <MetricItem label={p.sentiment} color={SENTIMENT_COLOR[p.sentiment] ?? "#748cab"} />
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
            {p.sources.slice(0, 3).map(s => (
              <span key={s.id} title={s.source_type} style={{ fontSize: 10, fontWeight: 700, padding: "1px 5px", borderRadius: 3, background: `${SOURCE_COLOR[s.source_type] ?? "#748cab"}15`, color: SOURCE_COLOR[s.source_type] ?? "#748cab", letterSpacing: "0.03em" }}>
                {SOURCE_ABBREV[s.source_type] ?? s.source_type.slice(0, 2).toUpperCase()}
              </span>
            ))}
            <span style={{ color: "#c0cdd8", fontSize: 10 }}>·</span>
            <span style={{ fontSize: 11, color: "#94a3b8" }}>
              {p.notes_count} notes · {p.files_count} fichiers · {p.members.length} membres
            </span>
          </div>
        </div>

      </div>
    </div>
  );
}

function MetricItem({ label, color }: { label: string; color: string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 600, color }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, display: "inline-block", flexShrink: 0 }} />
      {label}
    </span>
  );
}

function Dot() {
  return <span style={{ color: "#c0cdd8", margin: "0 6px", fontSize: 10 }}>·</span>;
}
