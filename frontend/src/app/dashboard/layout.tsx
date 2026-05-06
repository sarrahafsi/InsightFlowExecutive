"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AskAnything from "@/components/AskAnything";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface SourceStatus {
  key: string;
  name: string;
  icon: string;
  color: string;
  category: string;
  available: boolean;
  coming_soon: boolean;
  connected: boolean;
  items_count: number;
  last_sync: string | null;
}

// Category display order + icons
const CATEGORY_META: Record<string, { icon: string; order: number }> = {
  Communication: { icon: "💬", order: 1 },
  Projets:       { icon: "📋", order: 2 },
  Agenda:        { icon: "📅", order: 3 },
  CRM:           { icon: "☁️", order: 4 },
  Dev:           { icon: "🐙", order: 5 },
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { t, locale, setLocale } = useI18n();
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [projectCount, setProjectCount] = useState(0);

  useEffect(() => {
    API.get("/api/sources/status").then(r => {
      const data = r.data;
      setSources(data);
      const cats = new Set<string>(data.map((s: SourceStatus) => s.category));
      setCollapsedCategories(cats);
    }).catch(() => {});

    API.get("/api/projects").then(r => setProjectCount(r.data.length ?? 0)).catch(() => {});
  }, []);

  // Group sources by category, sorted by CATEGORY_META order
  const sourcesByCategory = sources.reduce((acc, s) => {
    if (!acc[s.category]) acc[s.category] = [];
    acc[s.category].push(s);
    return acc;
  }, {} as Record<string, SourceStatus[]>);

  const sortedCategories = Object.keys(sourcesByCategory).sort(
    (a, b) => (CATEGORY_META[a]?.order ?? 99) - (CATEGORY_META[b]?.order ?? 99)
  );

  function toggleCategory(cat: string) {
    setCollapsedCategories(prev => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  }

  function handleSourceClick(s: SourceStatus) {
    if (s.coming_soon) return;
    if (s.connected) {
      router.push(`/dashboard/${s.key}`);
    } else if (s.available) {
      router.push("/onboarding");
    }
  }

  const connectedCount = sources.filter(s => s.connected).length;

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "DM Sans, sans-serif", background: "#f5f3ee" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        .sb-item{transition:all 0.15s;cursor:pointer;}
        .sb-item:hover{background:rgba(240,235,216,0.08) !important;}
        .sb-item-disabled{cursor:default !important;}
        .sb-cat-toggle{transition:all 0.15s;cursor:pointer;}
        .sb-cat-toggle:hover{background:rgba(240,235,216,0.05) !important;}
      `}</style>

      {/* Sidebar */}
      <aside style={{
        width: 230, background: "#1d2d44", color: "#f0ebd8",
        display: "flex", flexDirection: "column",
        position: "fixed", top: 0, left: 0, bottom: 0, zIndex: 10,
        overflowY: "auto",
      }}>
        {/* Logo */}
        <div style={{ padding: "1.5rem 1.25rem 1rem", borderBottom: "1px solid rgba(240,235,216,0.1)", flexShrink: 0 }}>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 4 }}>
            InsightFlow
          </div>
          <div style={{ fontFamily: "DM Serif Display, serif", fontSize: 17, color: "#f0ebd8" }}>
            Executive
          </div>
        </div>

        <nav style={{ flex: 1, padding: "0.75rem 0.75rem 0.5rem", display: "flex", flexDirection: "column" }}>

          {/* Overview */}
          <Link href="/dashboard" style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "9px 12px", borderRadius: 10, textDecoration: "none",
            background: path === "/dashboard" ? "rgba(240,235,216,0.12)" : "transparent",
            color: path === "/dashboard" ? "#f0ebd8" : "#748cab",
            fontSize: 13, fontWeight: path === "/dashboard" ? 600 : 400,
            transition: "all 0.15s", marginBottom: 6,
          }}>
            <span style={{ fontSize: 15 }}>◈</span>
            {t.nav_overview}
          </Link>

          {/* Divider */}
          <div style={{ height: 1, background: "rgba(240,235,216,0.07)", margin: "4px 4px 8px" }} />

          {/* ── PROJECTS link ── */}
          <Link href="/dashboard/projects" style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "9px 12px", borderRadius: 10, textDecoration: "none",
            background: path.startsWith("/dashboard/projects") ? "rgba(240,235,216,0.12)" : "rgba(116,140,171,0.08)",
            color: path.startsWith("/dashboard/projects") ? "#f0ebd8" : "#c8d8e8",
            fontSize: 13, fontWeight: path.startsWith("/dashboard/projects") ? 600 : 500,
            transition: "all 0.15s", marginBottom: 4,
          }}>
            <span style={{ fontSize: 15 }}>🗂️</span>
            <span style={{ flex: 1 }}>{locale === "fr" ? "Projets" : "Projects"}</span>
            {projectCount > 0 && (
              <span style={{ fontSize: 10, background: "rgba(240,235,216,0.15)", color: "#c8d8e8", borderRadius: 10, padding: "1px 6px", fontWeight: 700 }}>
                {projectCount}
              </span>
            )}
          </Link>

          {/* Calendar link */}
          <Link href="/dashboard/calendar" style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "9px 12px", borderRadius: 10, textDecoration: "none",
            background: path.startsWith("/dashboard/calendar") ? "rgba(240,235,216,0.12)" : "rgba(116,140,171,0.08)",
            color: path.startsWith("/dashboard/calendar") ? "#f0ebd8" : "#c8d8e8",
            fontSize: 13, fontWeight: path.startsWith("/dashboard/calendar") ? 600 : 500,
            transition: "all 0.15s", marginBottom: 4,
          }}>
            <span style={{ fontSize: 15 }}>📅</span>
            <span style={{ flex: 1 }}>{locale === "fr" ? "Calendrier" : "Calendar"}</span>
          </Link>

          {/* Divider */}
          <div style={{ height: 1, background: "rgba(240,235,216,0.07)", margin: "4px 4px 8px" }} />

          {/* Sources label + connected count */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", marginBottom: 6 }}>
            <span style={{ fontSize: 10, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", fontWeight: 600 }}>
              {locale === "fr" ? "Sources" : "Sources"}
            </span>
            {connectedCount > 0 && (
              <span style={{ fontSize: 10, background: "#22c55e", color: "#fff", borderRadius: 10, padding: "1px 6px", fontWeight: 700 }}>
                {connectedCount}
              </span>
            )}
          </div>

          {/* Categories */}
          {sortedCategories.map(category => {
            const catSources = sourcesByCategory[category];
            const catMeta = CATEGORY_META[category];
            const isCollapsed = collapsedCategories.has(category);
            const hasConnected = catSources.some(s => s.connected);

            return (
              <div key={category} style={{ marginBottom: 2 }}>
                {/* Category header */}
                <div
                  className="sb-cat-toggle"
                  onClick={() => toggleCategory(category)}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 10px", borderRadius: 8, marginTop: 6,
                    background: "rgba(116,140,171,0.1)",
                    cursor: "pointer", userSelect: "none",
                  }}
                >
                  <span style={{ fontSize: 15 }}>{catMeta?.icon ?? "·"}</span>
                  <span style={{ fontSize: 13, color: "#c8d8e8", fontWeight: 700, flex: 1, letterSpacing: "0.01em" }}>
                    {category}
                  </span>
                  {hasConnected && (
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", flexShrink: 0 }} />
                  )}
                  <span style={{ fontSize: 11, color: "#748cab", transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)", transition: "transform 0.2s", display: "inline-block" }}>
                    ▾
                  </span>
                </div>

                {/* Sources in this category */}
                {!isCollapsed && (
                  <div style={{ paddingLeft: 8 }}>
                    {catSources.map(s => {
                      const isActive = path === `/dashboard/${s.key}`;
                      const isDisabled = s.coming_soon;

                      return (
                        <div
                          key={s.key}
                          className={isDisabled ? "sb-item sb-item-disabled" : "sb-item"}
                          onClick={() => handleSourceClick(s)}
                          style={{
                            display: "flex", alignItems: "center", gap: 9,
                            padding: "7px 10px", borderRadius: 8, marginBottom: 1,
                            background: isActive ? "rgba(240,235,216,0.12)" : "transparent",
                            opacity: isDisabled ? 0.4 : 1,
                          }}
                        >
                          <span style={{ fontSize: 14 }}>{s.icon}</span>
                          <span style={{
                            fontSize: 13, flex: 1,
                            color: isActive ? "#f0ebd8" : s.connected ? "#c8d8e8" : "#748cab",
                            fontWeight: isActive ? 600 : 400,
                          }}>
                            {s.name}
                          </span>
                          {s.connected ? (
                            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#22c55e", flexShrink: 0 }} />
                          ) : s.coming_soon ? (
                            <span style={{ fontSize: 9, color: "#748cab", background: "rgba(116,140,171,0.15)", borderRadius: 4, padding: "1px 5px", fontWeight: 600, letterSpacing: "0.05em" }}>
                              {locale === "fr" ? "bientôt" : "soon"}
                            </span>
                          ) : (
                            <span style={{ fontSize: 9, color: "#a16207", background: "rgba(161,98,7,0.12)", borderRadius: 4, padding: "1px 5px", fontWeight: 600 }}>
                              +
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {/* Add source link */}
          <div style={{ marginTop: 8 }}>
            <Link href="/onboarding" style={{
              display: "flex", alignItems: "center", gap: 9,
              padding: "7px 12px", borderRadius: 8, textDecoration: "none",
              color: "#748cab", fontSize: 12,
              border: "1px dashed rgba(116,140,171,0.25)",
              transition: "all 0.15s",
            }}>
              <span style={{ fontSize: 14 }}>⊕</span>
              {locale === "fr" ? "Gérer les sources" : "Manage sources"}
            </Link>
          </div>
        </nav>

        {/* Footer */}
        <div style={{ padding: "0.75rem 1.25rem", borderTop: "1px solid rgba(240,235,216,0.1)", flexShrink: 0 }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
            {(["fr", "en"] as const).map(l => (
              <button key={l} onClick={() => setLocale(l)} style={{
                flex: 1, padding: "5px 0", borderRadius: 8, border: "none",
                background: locale === l ? "rgba(240,235,216,0.15)" : "transparent",
                color: locale === l ? "#f0ebd8" : "#748cab",
                fontSize: 12, fontWeight: locale === l ? 700 : 400,
                cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.05em",
              }}>
                {l === "fr" ? "🇫🇷 FR" : "🇬🇧 EN"}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "#748cab" }}>{t.app_version}</div>
        </div>
      </aside>

      {/* Main */}
      <main style={{ marginLeft: 230, flex: 1, padding: "2rem 2.5rem", minWidth: 0 }}>
        {children}
      </main>

      {/* Chatbot flottant RAG */}
      <AskAnything />
    </div>
  );
}
