"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AskAnything from "@/components/AskAnything";
import RealtimeNotifications from "@/components/RealtimeNotifications";
import { WebSocketProvider, useWS } from "@/lib/WebSocketContext";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getUser, isCEO, logout, ROLE_LABELS, ROLE_COLORS, type AuthUser } from "@/lib/auth";
import { useTheme } from "@/lib/ThemeContext";
import {
  IconHome, IconFolder, IconCalendar, IconSettings,
  IconBuilding, IconUser, IconUsers, IconLogOut,
  IconSun, IconMoon, IconChevronDown,
  IconPlus, IconDatabase, IconMessageSquare, IconClipboard,
  IconCloud, IconCode, IconMail, IconFile,
  IconCheckSquare,
} from "@/components/icons";

interface SourceStatus {
  key: string; name: string; icon: string; color: string;
  category: string; available: boolean; coming_soon: boolean;
  connected: boolean; sync_pending?: boolean;
  items_count: number; last_sync: string | null;
}

/* ── Design tokens ─────────────────────────────────────────────── */
const SB = {
  bg:           "#1a2844",
  bgHover:      "rgba(255,255,255,0.06)",
  bgActive:     "rgba(59,130,246,0.12)",
  border:       "rgba(255,255,255,0.09)",
  accent:       "#3b82f6",
  textPrimary:  "#f1f5f9",
  textSecond:   "#a8bfd4",
  textMuted:    "#607a94",
} as const;

/* ── Category metadata ─────────────────────────────────────────── */
const CATEGORY_META: Record<string, { icon: React.ReactNode; order: number; color: string }> = {
  Communication: { icon: <IconMessageSquare size={13} />, order: 1, color: "#3b82f6" },
  Projets:       { icon: <IconClipboard size={13} />,    order: 2, color: "#8b5cf6" },
  Agenda:        { icon: <IconCalendar size={13} />,     order: 3, color: "#10b981" },
  CRM:           { icon: <IconCloud size={13} />,        order: 4, color: "#f59e0b" },
  Dev:           { icon: <IconCode size={13} />,         order: 5, color: "#ec4899" },
};

/* ── Source icons ───────────────────────────────────────────────── */
const SOURCE_ICON_MAP: Record<string, React.ReactNode> = {
  gmail:    <IconMail size={13} />,
  outlook:  <IconMail size={13} />,
  slack:    <IconMessageSquare size={13} />,
  teams:    <IconUsers size={13} />,
  jira:     <IconClipboard size={13} />,
  clickup:  <IconCheckSquare size={13} />,
  onedrive: <IconCloud size={13} />,
  notion:   <IconFile size={13} />,
};

/* ── Logo mark SVG ─────────────────────────────────────────────── */
function LogoMark() {
  return (
    <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
      <rect width={28} height={28} rx={7} fill="url(#lg)" />
      <path d="M8 14l4 4 8-8" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="28" y2="28">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/* ── Nav item ──────────────────────────────────────────────────── */
function NavItem({
  href, icon, label, active, badge, disabled,
}: {
  href: string; icon: React.ReactNode; label: React.ReactNode;
  active?: boolean; badge?: React.ReactNode; disabled?: boolean;
}) {
  return (
    <Link
      href={disabled ? "#" : href}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "8px 12px 8px 10px",
        borderRadius: 8,
        borderLeft: `2px solid ${active ? SB.accent : "transparent"}`,
        background: active ? SB.bgActive : "transparent",
        color: active ? SB.textPrimary : SB.textSecond,
        fontSize: 13, fontWeight: active ? 600 : 400,
        textDecoration: "none",
        transition: "all 0.15s",
        pointerEvents: disabled ? "none" : "auto",
        marginBottom: 1,
      }}
      className="sb-navitem"
    >
      <span style={{ display: "flex", color: active ? SB.accent : SB.textMuted }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {badge}
    </Link>
  );
}

/* ── User menu ─────────────────────────────────────────────────── */
function UserMenu({ user }: { user: AuthUser }) {
  const [open, setOpen] = useState(false);
  const initials = user.full_name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "5px 10px 5px 5px", borderRadius: 999,
          border: "1px solid rgba(29,45,68,0.12)",
          background: "#fff", cursor: "pointer",
          boxShadow: open ? "0 2px 12px rgba(29,45,68,0.12)" : "none",
          transition: "box-shadow 0.15s",
        }}
      >
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "linear-gradient(135deg,#3b82f6,#8b5cf6)",
          color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 700, flexShrink: 0,
        }}>
          {initials}
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#1d2d44", lineHeight: 1.2 }}>{user.full_name}</div>
          <div style={{ fontSize: 9, padding: "1px 5px", borderRadius: 5, fontWeight: 700,
            background: `${ROLE_COLORS[user.role]}18`, color: ROLE_COLORS[user.role],
            textTransform: "uppercase", letterSpacing: "0.05em", display: "inline-block", marginTop: 1 }}>
            {ROLE_LABELS[user.role]}
          </div>
        </div>
        <span style={{ display: "flex", color: "#94a3b8", transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
          <IconChevronDown size={11} />
        </span>
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 49 }} />
          <div style={{
            position: "absolute", top: "calc(100% + 8px)", right: 0, zIndex: 50,
            background: "#fff", borderRadius: 14, minWidth: 200,
            boxShadow: "0 8px 30px rgba(29,45,68,0.15)",
            border: "1px solid rgba(29,45,68,0.08)", overflow: "hidden",
          }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(29,45,68,0.07)" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#1d2d44", marginBottom: 2 }}>{user.full_name}</div>
              <div style={{ fontSize: 11, color: "#748cab" }}>{user.email}</div>
            </div>
            <div style={{ padding: "8px" }}>
              <button onClick={logout} style={{
                width: "100%", padding: "8px 12px", borderRadius: 9, border: "none",
                background: "rgba(239,68,68,0.07)", color: "#ef4444",
                fontSize: 12, fontWeight: 600, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 8, transition: "background 0.15s",
              }}>
                <IconLogOut size={13} />
                Déconnexion
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Dashboard inner ───────────────────────────────────────────── */
function DashboardInner({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { t, locale, setLocale } = useI18n();
  const { connected } = useWS();
  const { theme, toggle: toggleTheme } = useTheme();
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [projectCount, setProjectCount] = useState(0);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setCurrentUser(getUser());
    API.get("/api/sources/status").then(r => {
      const data = r.data;
      setSources(data);
      const cats = new Set<string>(data.map((s: SourceStatus) => s.category));
      setCollapsedCategories(cats);
    }).catch(() => {});
    API.get("/api/projects").then(r => setProjectCount(r.data.length ?? 0)).catch(() => {});
  }, []);

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

  async function handleSourceClick(s: SourceStatus) {
    if (s.coming_soon) return;
    if (s.connected) {
      router.push(`/dashboard/${s.key}`);
    } else if (s.available && currentUser && isCEO(currentUser)) {
      const OAUTH_SOURCES: Record<string, string> = {
        gmail: "/auth/google", outlook: "/auth/outlook/auth-url", teams: "/auth/teams/auth-url",
      };
      const ep = OAUTH_SOURCES[s.key];
      if (ep) {
        try {
          const res = await API.get(ep);
          if (res.data?.url) { window.location.href = res.data.url; return; }
        } catch { /* fall through */ }
      }
      router.push("/onboarding");
    }
  }

  const connectedCount = sources.filter(s => s.connected).length;

  /* ── Superadmin layout ──────────────────────────────────────── */
  if (currentUser?.role === "superadmin") {
    return (
      <div style={{ display: "flex", minHeight: "100vh", fontFamily: "DM Sans, sans-serif", background: "#f5f3ee" }}>
        <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap'); *{box-sizing:border-box;margin:0;padding:0;}`}</style>
        <aside style={{
          width: 230, background: SB.bg, color: SB.textPrimary,
          display: "flex", flexDirection: "column",
          position: "fixed", top: 0, left: 0, bottom: 0, zIndex: 10,
        }}>
          {/* Brand */}
          <div style={{ padding: "1.25rem", borderBottom: `1px solid ${SB.border}`, flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <LogoMark />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: SB.textPrimary, lineHeight: 1.2 }}>InsightFlow</div>
                <div style={{ fontSize: 10, color: SB.textMuted, letterSpacing: "0.04em" }}>Executive</div>
              </div>
            </div>
            <div style={{ marginTop: 10, display: "inline-flex", alignItems: "center", gap: 5,
              background: "rgba(147,51,234,0.15)", border: "1px solid rgba(147,51,234,0.3)",
              borderRadius: 6, padding: "3px 8px" }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#9333ea" }} />
              <span style={{ fontSize: 9, fontWeight: 700, color: "#c4b5fd", letterSpacing: "0.1em" }}>SUPER ADMIN</span>
            </div>
          </div>

          <nav style={{ flex: 1, padding: "0.875rem 0.75rem", display: "flex", flexDirection: "column", gap: 2 }}>
            <NavItem href="/dashboard/admin" icon={<IconSettings size={14} />} label="Platform Console"
              active={path === "/dashboard/admin"} />
            <div style={{ height: 1, background: SB.border, margin: "8px 4px" }} />
            <div style={{ fontSize: 10, color: SB.textMuted, textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, padding: "0 10px", marginBottom: 4 }}>
              Monitoring
            </div>
            <NavItem href="/dashboard/admin?tab=orgs"  icon={<IconBuilding size={14} />} label="Organisations" />
            <NavItem href="/dashboard/admin?tab=users" icon={<IconUser size={14} />}     label="Utilisateurs" />
          </nav>

          <SidebarFooter locale={locale} setLocale={setLocale} connected={connected} version={t.app_version} />
        </aside>

        <main style={{ marginLeft: 230, flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "flex-end",
            padding: "0.75rem 2.5rem", background: "#f5f3ee",
            borderBottom: "1px solid rgba(29,45,68,0.08)",
            position: "sticky", top: 0, zIndex: 9,
          }}>
            {currentUser && <UserMenu user={currentUser} />}
          </div>
          <div style={{ padding: "2rem 2.5rem", flex: 1 }}>{children}</div>
        </main>
      </div>
    );
  }

  /* ── Main layout ────────────────────────────────────────────── */
  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "DM Sans, sans-serif", background: "var(--bg-page)" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        .sb-navitem:hover { background: ${SB.bgHover} !important; color: ${SB.textPrimary} !important; }
        .sb-navitem:hover span:first-child { color: ${SB.textSecond} !important; }
        .sb-item { transition: all 0.15s; cursor: pointer; }
        .sb-item:hover { background: ${SB.bgHover} !important; }
        .sb-item-disabled { cursor: default !important; }
        .sb-cat:hover { background: ${SB.bgHover} !important; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }
        @keyframes glowPulse { 0%,100%{box-shadow:0 0 6px #10b98166} 50%{box-shadow:0 0 12px #10b98199} }
      `}</style>

      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside style={{
        width: 240,
        background: SB.bg,
        display: "flex", flexDirection: "column",
        position: "fixed", top: 0, left: 0, bottom: 0, zIndex: 10,
        overflowY: "auto",
        borderRight: `1px solid ${SB.border}`,
      }}>

        {/* Brand */}
        <div style={{ padding: "1.25rem 1.125rem", borderBottom: `1px solid ${SB.border}`, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <LogoMark />
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: SB.textPrimary, letterSpacing: "-0.01em", lineHeight: 1.2 }}>
                InsightFlow
              </div>
              <div style={{ fontSize: 10, color: SB.textMuted, letterSpacing: "0.04em", marginTop: 1 }}>
                Executive
              </div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "0.875rem 0.75rem 0.5rem", display: "flex", flexDirection: "column" }}>

          {/* Overview */}
          <NavItem
            href="/dashboard"
            icon={<IconHome size={15} />}
            label={t.nav_overview}
            active={path === "/dashboard"}
          />

          <div style={{ height: 1, background: SB.border, margin: "8px 4px" }} />

          {/* Section label */}
          <div style={{ fontSize: 10, color: SB.textMuted, textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600, padding: "0 10px", marginBottom: 4 }}>
            {locale === "fr" ? "Navigation" : "Navigation"}
          </div>

          {/* Projects */}
          <NavItem
            href="/dashboard/projects"
            icon={<IconFolder size={15} />}
            label={locale === "fr" ? "Projets" : "Projects"}
            active={path.startsWith("/dashboard/projects")}
            badge={projectCount > 0 ? (
              <span style={{ fontSize: 10, background: "rgba(139,92,246,0.18)", color: "#a78bfa", borderRadius: 8, padding: "1px 7px", fontWeight: 700 }}>
                {projectCount}
              </span>
            ) : undefined}
          />

          {/* Calendar */}
          <NavItem
            href="/dashboard/calendar"
            icon={<IconCalendar size={15} />}
            label={locale === "fr" ? "Calendrier" : "Calendar"}
            active={path.startsWith("/dashboard/calendar")}
          />

          <div style={{ height: 1, background: SB.border, margin: "8px 4px" }} />

          {/* Sources header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 10px", marginBottom: 6 }}>
            <span style={{ fontSize: 10, color: SB.textMuted, textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600 }}>
              Sources
            </span>
            {connectedCount > 0 && (
              <span style={{
                fontSize: 10, background: "rgba(16,185,129,0.15)", color: "#10b981",
                borderRadius: 10, padding: "1px 7px", fontWeight: 700,
              }}>
                {connectedCount}
              </span>
            )}
          </div>

          {/* Source categories */}
          {sortedCategories.map(category => {
            const catSources = sourcesByCategory[category];
            const meta = CATEGORY_META[category];
            const isCollapsed = collapsedCategories.has(category);
            const hasConnected = catSources.some(s => s.connected);

            return (
              <div key={category} style={{ marginBottom: 2 }}>
                {/* Category toggle */}
                <div
                  className="sb-cat"
                  onClick={() => toggleCategory(category)}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 10px", borderRadius: 8, marginTop: 4,
                    cursor: "pointer", userSelect: "none",
                    transition: "background 0.15s",
                  }}
                >
                  {/* Colored icon pill */}
                  <div style={{
                    width: 24, height: 24, borderRadius: 6, flexShrink: 0,
                    background: meta ? `${meta.color}18` : "rgba(255,255,255,0.06)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: meta?.color ?? SB.textMuted,
                  }}>
                    {meta?.icon ?? <IconDatabase size={13} />}
                  </div>
                  <span style={{ fontSize: 12.5, color: SB.textSecond, fontWeight: 600, flex: 1 }}>
                    {category}
                  </span>
                  {hasConnected && (
                    <span style={{
                      width: 5, height: 5, borderRadius: "50%",
                      background: "#10b981",
                      boxShadow: "0 0 5px #10b98188",
                      flexShrink: 0,
                    }} />
                  )}
                  <span style={{
                    display: "flex", color: SB.textMuted,
                    transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)",
                    transition: "transform 0.2s",
                  }}>
                    <IconChevronDown size={12} />
                  </span>
                </div>

                {/* Sources in category */}
                {!isCollapsed && (
                  <div style={{ paddingLeft: 6, marginTop: 2 }}>
                    {catSources.map(s => {
                      const isActive  = path === `/dashboard/${s.key}`;
                      const isDisabled = s.coming_soon || (!s.connected && currentUser && !isCEO(currentUser));
                      const canManage = currentUser ? isCEO(currentUser) : false;
                      const sourceColor = meta?.color ?? SB.accent;

                      return (
                        <div
                          key={s.key}
                          className={isDisabled ? "sb-item sb-item-disabled" : "sb-item"}
                          onClick={() => handleSourceClick(s)}
                          style={{
                            display: "flex", alignItems: "center", gap: 9,
                            padding: "6px 10px 6px 8px",
                            borderRadius: 7, marginBottom: 1,
                            borderLeft: `2px solid ${isActive ? sourceColor : "transparent"}`,
                            background: isActive ? `${sourceColor}0d` : "transparent",
                            opacity: isDisabled && !s.connected ? 0.45 : 1,
                          }}
                        >
                          <span style={{ display: "flex", color: isActive ? sourceColor : SB.textMuted }}>
                            {SOURCE_ICON_MAP[s.key] ?? <IconDatabase size={13} />}
                          </span>
                          <span style={{
                            fontSize: 12.5, flex: 1,
                            color: isActive ? SB.textPrimary : s.connected ? SB.textSecond : SB.textMuted,
                            fontWeight: isActive ? 600 : 400,
                          }}>
                            {s.name}
                          </span>
                          {/* Status indicator */}
                          {s.connected && s.sync_pending ? (
                            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#f59e0b", flexShrink: 0, animation: "pulse 1.5s ease infinite" }} />
                          ) : s.connected ? (
                            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#10b981", flexShrink: 0, boxShadow: "0 0 4px #10b98177" }} />
                          ) : s.coming_soon ? (
                            <span style={{ fontSize: 9, color: SB.textMuted, background: "rgba(255,255,255,0.06)", borderRadius: 4, padding: "1px 5px", fontWeight: 600 }}>
                              {locale === "fr" ? "bientôt" : "soon"}
                            </span>
                          ) : canManage ? (
                            <span style={{ fontSize: 9, color: "#f59e0b", background: "rgba(245,158,11,0.12)", borderRadius: 4, padding: "1px 5px", fontWeight: 600 }}>
                              +
                            </span>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {/* Manage sources — CEO only */}
          {currentUser && isCEO(currentUser) && (
            <div style={{ marginTop: 10 }}>
              <Link href="/onboarding" style={{
                display: "flex", alignItems: "center", gap: 9,
                padding: "7px 12px", borderRadius: 8, textDecoration: "none",
                color: SB.textMuted, fontSize: 12,
                border: `1px dashed ${SB.border}`,
                transition: "all 0.15s",
              }}>
                <IconPlus size={13} />
                {locale === "fr" ? "Gérer les sources" : "Manage sources"}
              </Link>
            </div>
          )}
        </nav>

        <SidebarFooter locale={locale} setLocale={setLocale} connected={connected} version={t.app_version} />
      </aside>

      {/* ── Main content ────────────────────────────────────────── */}
      <main style={{ marginLeft: 240, flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        {/* Topbar */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "flex-end",
          padding: "0.75rem 2.5rem",
          background: "var(--bg-topbar)",
          borderBottom: "1px solid var(--border-top)",
          position: "sticky", top: 0, zIndex: 9,
          gap: 12, transition: "background 0.25s ease",
        }}>
          <button
            onClick={toggleTheme}
            title={theme === "dark" ? "Mode clair" : "Mode sombre"}
            style={{
              width: 34, height: 34, borderRadius: 9,
              border: "1px solid var(--border)",
              background: "var(--bg-card)",
              color: "var(--text-secondary)",
              cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all 0.2s",
            }}
          >
            {theme === "dark" ? <IconSun size={15} /> : <IconMoon size={15} />}
          </button>
          {currentUser && <UserMenu user={currentUser} />}
        </div>

        <div style={{ padding: "2rem 2.5rem", flex: 1, background: "var(--bg-page)", transition: "background 0.25s ease" }}>
          {children}
        </div>
      </main>

      <AskAnything />
      <RealtimeNotifications />
    </div>
  );
}

/* ── Sidebar footer ─────────────────────────────────────────────── */
function SidebarFooter({ locale, setLocale, connected, version }: {
  locale: string; setLocale: (l: "fr" | "en") => void;
  connected: boolean; version: string;
}) {
  return (
    <div style={{ padding: "0.875rem 1.125rem", borderTop: `1px solid ${SB.border}`, flexShrink: 0 }}>
      {/* Lang toggle */}
      <div style={{
        display: "flex", gap: 2, marginBottom: 10,
        background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: 3,
      }}>
        {(["fr", "en"] as const).map(l => (
          <button key={l} onClick={() => setLocale(l)} style={{
            flex: 1, padding: "4px 0", borderRadius: 6, border: "none",
            background: locale === l ? "rgba(59,130,246,0.2)" : "transparent",
            color: locale === l ? "#93c5fd" : SB.textMuted,
            fontSize: 11, fontWeight: locale === l ? 700 : 400,
            cursor: "pointer", letterSpacing: "0.05em",
            transition: "all 0.15s",
          }}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Connection status */}
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <span style={{
          width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
          background: connected ? "#10b981" : "#f87171",
          animation: connected ? "glowPulse 2.5s ease infinite" : "none",
        }} />
        <span style={{ fontSize: 11, color: connected ? "#34d399" : "#f87171" }}>
          {connected ? (locale === "fr" ? "Temps réel actif" : "Live connected") : (locale === "fr" ? "Reconnexion..." : "Reconnecting...")}
        </span>
      </div>

      <div style={{ fontSize: 10, color: SB.textMuted, marginTop: 6, letterSpacing: "0.02em" }}>
        {version}
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <WebSocketProvider>
      <DashboardInner>{children}</DashboardInner>
    </WebSocketProvider>
  );
}
