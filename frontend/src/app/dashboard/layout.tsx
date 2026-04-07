"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import API from "@/lib/api";

const NAV = [
  { href: "/dashboard",        label: "Vue d'ensemble", icon: "◈" },
  { href: "/dashboard/gmail",  label: "Gmail",          icon: "✉" },
  { href: "/dashboard/slack",  label: "Slack",          icon: "#" },
  { href: "/dashboard/jira",   label: "Jira",           icon: "J" },
];

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

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [showSources, setShowSources] = useState(false);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    API.get("/api/sources/status").then(r => setSources(r.data)).catch(() => {});
  }, []);

  // Close panel on outside click
  useEffect(() => {
    if (!showSources) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setShowSources(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSources]);

  const connected = sources.filter(s => s.connected);
  const available = sources.filter(s => !s.connected && s.available && !s.coming_soon);
  const comingSoon = sources.filter(s => !s.connected && s.coming_soon);

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "DM Sans, sans-serif", background: "#f5f3ee" }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');*{box-sizing:border-box;margin:0;padding:0;}`}</style>

      {/* Sidebar */}
      <aside style={{
        width: 220, background: "#1d2d44", color: "#f0ebd8",
        display: "flex", flexDirection: "column",
        position: "fixed", top: 0, left: 0, bottom: 0, zIndex: 10,
      }}>
        <div style={{ padding: "1.5rem 1.25rem 1rem", borderBottom: "1px solid rgba(240,235,216,0.1)" }}>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 4 }}>
            InsightFlow
          </div>
          <div style={{ fontFamily: "DM Serif Display, serif", fontSize: 17, color: "#f0ebd8" }}>
            Executive
          </div>
        </div>

        <nav style={{ flex: 1, padding: "1rem 0.75rem", display: "flex", flexDirection: "column", gap: 4 }}>
          {NAV.map(({ href, label, icon }) => {
            const active = path === href;
            return (
              <Link key={href} href={href} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: 10, textDecoration: "none",
                background: active ? "rgba(240,235,216,0.12)" : "transparent",
                color: active ? "#f0ebd8" : "#748cab",
                fontSize: 13, fontWeight: active ? 600 : 400,
                transition: "all 0.15s",
              }}>
                <span style={{ fontSize: 15 }}>{icon}</span>
                {label}
              </Link>
            );
          })}

          {/* Sources button */}
          <div ref={panelRef} style={{ position: "relative" }}>
            <button
              onClick={() => setShowSources(v => !v)}
              style={{
                display: "flex", alignItems: "center", gap: 10, width: "100%",
                padding: "10px 12px", borderRadius: 10, border: "none", cursor: "pointer",
                background: showSources ? "rgba(240,235,216,0.12)" : "transparent",
                color: showSources ? "#f0ebd8" : "#748cab",
                fontSize: 13, fontWeight: showSources ? 600 : 400,
                transition: "all 0.15s",
              }}
            >
              <span style={{ fontSize: 15 }}>⊕</span>
              Sources
              {connected.length > 0 && (
                <span style={{
                  marginLeft: "auto", fontSize: 10, background: "#22c55e",
                  color: "#fff", borderRadius: 10, padding: "1px 6px", fontWeight: 700,
                }}>
                  {connected.length}
                </span>
              )}
            </button>

            {showSources && (
              <div style={{
                position: "absolute", left: "calc(100% + 8px)", top: 0,
                width: 280, background: "#fff", borderRadius: 14,
                boxShadow: "0 8px 32px rgba(13,19,33,0.18)",
                border: "1px solid rgba(62,92,118,0.12)",
                zIndex: 100, overflow: "hidden",
              }}>
                {/* Connected */}
                <div style={{ padding: "14px 16px 8px" }}>
                  <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", fontWeight: 600, marginBottom: 8 }}>
                    Connectées ({connected.length})
                  </div>
                  {connected.length === 0 ? (
                    <p style={{ fontSize: 12, color: "#748cab", padding: "4px 0" }}>Aucune source connectée</p>
                  ) : (
                    connected.map(s => (
                      <div
                        key={s.key}
                        onClick={() => { setShowSources(false); router.push(`/dashboard/${s.key}`); }}
                        style={{
                          display: "flex", alignItems: "center", gap: 10,
                          padding: "8px 10px", borderRadius: 8, marginBottom: 4,
                          background: path === `/dashboard/${s.key}` ? "#f0fdf4" : "#f8fffe",
                          cursor: "pointer", transition: "background 0.15s",
                          border: `1px solid ${path === `/dashboard/${s.key}` ? "#86efac" : "transparent"}`,
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#e8f5e9")}
                        onMouseLeave={e => (e.currentTarget.style.background = path === `/dashboard/${s.key}` ? "#f0fdf4" : "#f8fffe")}
                      >
                        <span style={{ fontSize: 16 }}>{s.icon}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{s.name}</div>
                          <div style={{ fontSize: 11, color: "#748cab" }}>
                            {s.items_count} items
                            {s.last_sync && ` · ${new Date(s.last_sync).toLocaleDateString("fr-FR")}`}
                          </div>
                        </div>
                        <span style={{ fontSize: 10, background: "#dcfce7", color: "#16a34a", borderRadius: 8, padding: "2px 8px", fontWeight: 600 }}>
                          ✓ actif
                        </span>
                      </div>
                    ))
                  )}
                </div>

                {/* Available but not connected */}
                {available.length > 0 && (
                  <div style={{ padding: "8px 16px", borderTop: "1px solid rgba(62,92,118,0.08)" }}>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", fontWeight: 600, marginBottom: 8 }}>
                      Disponibles
                    </div>
                    {available.map(s => (
                      <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: 8, marginBottom: 4, background: "#f8f9fa" }}>
                        <span style={{ fontSize: 16 }}>{s.icon}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, color: "#0d1321" }}>{s.name}</div>
                        </div>
                        <span style={{ fontSize: 10, background: "#fef9c3", color: "#a16207", borderRadius: 8, padding: "2px 8px", fontWeight: 600 }}>
                          non connecté
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Coming soon */}
                <div style={{ padding: "8px 16px 14px", borderTop: "1px solid rgba(62,92,118,0.08)" }}>
                  <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", fontWeight: 600, marginBottom: 8 }}>
                    À venir ({comingSoon.length})
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {comingSoon.map(s => (
                      <span key={s.key} style={{
                        fontSize: 11, padding: "3px 10px", borderRadius: 20,
                        background: "rgba(62,92,118,0.08)", color: "#748cab",
                      }}>
                        {s.icon} {s.name}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </nav>

        <div style={{ padding: "1rem 1.25rem", borderTop: "1px solid rgba(240,235,216,0.1)" }}>
          <div style={{ fontSize: 11, color: "#748cab" }}>v0.1.0 — PFE 2026</div>
        </div>
      </aside>

      {/* Main */}
      <main style={{ marginLeft: 220, flex: 1, padding: "2rem 2.5rem", minWidth: 0 }}>
        {children}
      </main>
    </div>
  );
}
