"use client";
import { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import API from "@/lib/api";

interface SourceDoc {
  id:        string;
  title:     string;
  author:    string;
  timestamp: string;
  source:    string;
  sentiment: string;
  business:  string;
  excerpt:   string;
  url:       string;
}

interface Message {
  role:    "user" | "assistant";
  content: string;
  sources?: SourceDoc[];
}

const SOURCE_ICONS: Record<string, string> = {
  gmail: "✉️", slack: "💬", jira: "📋", notion: "📝", default: "📄",
};

const BUSINESS_COLORS: Record<string, string> = {
  BLOCKED: "#ef4444", URGENT: "#f97316", RISK: "#eab308",
  CONFLICT: "#a855f7", OVERLOAD: "#ec4899", PROGRESS: "#22c55e",
  CONCERN: "#3b82f6", default: "#94a3b8",
};

const EXAMPLES_GLOBAL = [
  "Quels projets sont bloqués ?",
  "Y a-t-il des urgences cette semaine ?",
  "Résume les emails négatifs récents",
  "Qui m'a contacté le plus souvent ?",
];

const EXAMPLES_PROJECT = [
  "Quels sont les risques de ce projet ?",
  "Y a-t-il des tâches bloquées ?",
  "Quel est l'état de l'équipe ?",
  "Résume les derniers messages importants.",
];

export default function AskAnything() {
  const pathname = usePathname();

  // Detect if we're on a project page
  const projectMatch = pathname?.match(/\/dashboard\/projects\/([^/]+)/);
  const projectId    = projectMatch ? projectMatch[1] : null;

  const [open, setOpen]           = useState(false);
  const [query, setQuery]         = useState("");
  const [messages, setMessages]   = useState<Message[]>([]);
  const [loading, setLoading]     = useState(false);
  const [indexed, setIndexed]     = useState<number | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  const EXAMPLES = projectId ? EXAMPLES_PROJECT : EXAMPLES_GLOBAL;

  // Charger le statut de l'index
  useEffect(() => {
    API.get("/api/ask/status")
      .then(r => setIndexed(r.data.indexed_count))
      .catch(() => {});
  }, []);

  // Scroll auto vers le bas à chaque nouveau message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input quand on ouvre
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  const handleAsk = async (q?: string) => {
    const question = (q ?? query).trim();
    if (!question || loading) return;
    setQuery("");
    setMessages(prev => [...prev, { role: "user", content: question }]);
    setLoading(true);
    try {
      let r;
      if (projectId) {
        // Project-aware RAG: context includes tasks, members, notes
        r = await API.post(`/api/projects/${projectId}/ask`, { question, top_k: 8 });
      } else {
        // Global RAG: all messages across all sources
        r = await API.post("/api/ask", { query: question, top_k: 5 });
      }
      setMessages(prev => [...prev, {
        role: "assistant",
        content: r.data.answer,
        sources: r.data.sources,
      }]);
      if (r.data.indexed_count !== undefined) setIndexed(r.data.indexed_count);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `⚠️ Erreur : ${e.message ?? "Impossible de contacter le serveur."}`,
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      const r = await API.post("/api/ask/reindex", {});
      setIndexed(r.data.indexed);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `✅ ${r.data.indexed} messages indexés dans la base de connaissances.`,
      }]);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `⚠️ Erreur lors de l'indexation : ${e.message}`,
      }]);
    } finally {
      setReindexing(false);
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "";
    try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }); }
    catch { return iso.slice(0, 10); }
  };

  return (
    <>
      {/* ── Panneau chat ── */}
      <div style={{
        position:   "fixed",
        bottom:     90,
        right:      24,
        width:      420,
        maxHeight:  "70vh",
        background: "#fff",
        borderRadius: 20,
        boxShadow:  "0 8px 40px rgba(13,19,33,0.18)",
        border:     "1px solid rgba(62,92,118,0.15)",
        display:    "flex",
        flexDirection: "column",
        zIndex:     1000,
        overflow:   "hidden",
        transform:  open ? "translateY(0) scale(1)" : "translateY(16px) scale(0.97)",
        opacity:    open ? 1 : 0,
        pointerEvents: open ? "all" : "none",
        transition: "transform 0.22s cubic-bezier(.4,0,.2,1), opacity 0.18s ease",
      }}>

        {/* Header */}
        <div style={{
          background: "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)",
          padding: "1rem 1.25rem",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20 }}>🧠</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#f0ebd8" }}>
                Ask InsightFlow
              </div>
              <div style={{ fontSize: 11, color: "rgba(240,235,216,0.6)" }}>
                {projectId
                  ? "🗂️ Contexte projet actif"
                  : indexed !== null ? `${indexed} messages indexés` : "Chargement..."}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              onClick={handleReindex}
              disabled={reindexing}
              title="Réindexer les messages"
              style={{
                background: "rgba(255,255,255,0.12)",
                border: "1px solid rgba(240,235,216,0.2)",
                color: "#f0ebd8", borderRadius: 8,
                padding: "4px 10px", fontSize: 11,
                cursor: "pointer", fontWeight: 600,
              }}
            >
              {reindexing ? "⏳" : "🔄"}
            </button>
            <button
              onClick={() => setOpen(false)}
              style={{
                background: "rgba(255,255,255,0.12)",
                border: "none", color: "#f0ebd8",
                borderRadius: 8, width: 28, height: 28,
                cursor: "pointer", fontSize: 16,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Messages */}
        <div style={{
          flex: 1, overflowY: "auto", padding: "1rem",
          display: "flex", flexDirection: "column", gap: 12,
        }}>

          {/* Message de bienvenue */}
          {messages.length === 0 && (
            <div style={{ textAlign: "center", padding: "1rem 0 0.5rem" }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>👋</div>
              <div style={{ fontSize: 13, color: "#475569" }}>
                {projectId
                  ? "Posez une question sur ce projet — tâches, équipe, messages liés."
                  : "Posez une question sur vos emails, projets ou équipes."}
              </div>
            </div>
          )}

          {/* Bulles de message */}
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: "flex",
              flexDirection: msg.role === "user" ? "row-reverse" : "row",
              gap: 8, alignItems: "flex-start",
            }}>
              {/* Avatar */}
              <div style={{
                width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                background: msg.role === "user"
                  ? "linear-gradient(135deg,#3e5c76,#1d2d44)"
                  : "linear-gradient(135deg,#f0ebd8,#e0d5c0)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13,
              }}>
                {msg.role === "user" ? "👤" : "🧠"}
              </div>

              <div style={{ maxWidth: "80%", display: "flex", flexDirection: "column", gap: 6 }}>
                {/* Bulle */}
                <div style={{
                  padding: "0.625rem 0.875rem",
                  borderRadius: msg.role === "user" ? "16px 4px 16px 16px" : "4px 16px 16px 16px",
                  background: msg.role === "user"
                    ? "linear-gradient(135deg,#1d2d44,#3e5c76)"
                    : "#f1f5f9",
                  color: msg.role === "user" ? "#f0ebd8" : "#0d1321",
                  fontSize: 13, lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                }}>
                  {msg.content}
                </div>

                {/* Sources */}
                {msg.sources && msg.sources.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {msg.sources.map((src, j) => (
                      <div key={src.id} style={{
                        padding: "6px 10px",
                        background: "#fff",
                        border: "1px solid rgba(62,92,118,0.12)",
                        borderRadius: 10, fontSize: 11,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                          <span style={{ fontWeight: 600, color: "#0d1321" }}>
                            [{j+1}] {src.title || "(sans titre)"}
                          </span>
                          {src.business && (
                            <span style={{
                              padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 700,
                              background: (BUSINESS_COLORS[src.business] ?? BUSINESS_COLORS.default) + "20",
                              color: BUSINESS_COLORS[src.business] ?? BUSINESS_COLORS.default,
                            }}>
                              {src.business}
                            </span>
                          )}
                        </div>
                        <div style={{ color: "#748cab" }}>
                          {SOURCE_ICONS[src.source] ?? SOURCE_ICONS.default}
                          {" "}{src.author} · {formatDate(src.timestamp)}
                        </div>
                        <div style={{ color: "#475569", marginTop: 2, lineHeight: 1.4 }}>
                          {src.excerpt}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Indicateur "en train de taper" */}
          {loading && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%",
                background: "linear-gradient(135deg,#f0ebd8,#e0d5c0)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13,
              }}>🧠</div>
              <div style={{
                padding: "0.625rem 0.875rem", background: "#f1f5f9",
                borderRadius: "4px 16px 16px 16px",
                display: "flex", gap: 4, alignItems: "center",
              }}>
                {[0,1,2].map(k => (
                  <div key={k} style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: "#748cab",
                    animation: "bounce 1.2s infinite",
                    animationDelay: `${k * 0.2}s`,
                  }} />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Suggestions rapides — toujours visibles */}
        <div style={{
          padding: "0.5rem 1rem 0",
          borderTop: "1px solid rgba(62,92,118,0.08)",
          display: "flex", flexWrap: "wrap", gap: 5, flexShrink: 0,
          background: "#fff",
        }}>
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => handleAsk(ex)}
              disabled={loading}
              style={{
                padding: "4px 10px",
                background: "#f1f5f9",
                border: "1px solid rgba(62,92,118,0.15)",
                borderRadius: 20, fontSize: 11,
                color: "#3e5c76", cursor: "pointer",
                fontWeight: 500, whiteSpace: "nowrap",
              }}
            >
              {ex}
            </button>
          ))}
        </div>

        {/* Input */}
        <div style={{
          padding: "0.625rem 1rem 0.75rem",
          display: "flex", gap: 8, flexShrink: 0,
          background: "#fff",
        }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleAsk()}
            placeholder="Posez votre question..."
            disabled={loading}
            style={{
              flex: 1, padding: "0.625rem 0.875rem",
              border: "1.5px solid rgba(62,92,118,0.2)",
              borderRadius: 12, fontSize: 13, outline: "none",
              fontFamily: "inherit", background: "#f8fafc",
            }}
          />
          <button
            onClick={() => handleAsk()}
            disabled={loading || !query.trim()}
            style={{
              width: 38, height: 38, borderRadius: 12, border: "none", flexShrink: 0,
              background: loading || !query.trim()
                ? "#e2e8f0"
                : "linear-gradient(135deg,#1d2d44,#3e5c76)",
              color: loading || !query.trim() ? "#94a3b8" : "#fff",
              cursor: loading || !query.trim() ? "not-allowed" : "pointer",
              fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            ↑
          </button>
        </div>

        <style>{`
          @keyframes bounce {
            0%, 60%, 100% { transform: translateY(0); }
            30%            { transform: translateY(-5px); }
          }
        `}</style>
      </div>

      {/* ── Bouton flottant ── */}
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          position:   "fixed",
          bottom:     24,
          right:      24,
          width:      56,
          height:     56,
          borderRadius: "50%",
          background: open
            ? "#1d2d44"
            : "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)",
          border:     "none",
          boxShadow:  "0 4px 20px rgba(13,19,33,0.3)",
          cursor:     "pointer",
          zIndex:     1001,
          display:    "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize:   22,
          color:      "#f0ebd8",
          transition: "transform 0.2s, background 0.2s",
          transform:  open ? "rotate(0deg)" : "rotate(0deg)",
        }}
        title="Ask InsightFlow"
      >
        {open ? "✕" : "🧠"}
      </button>
    </>
  );
}
