"use client";
import { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import API from "@/lib/api";

interface SourceDoc {
  id: string; title: string; author: string;
  timestamp: string; source: string;
  sentiment: string; business: string;
  excerpt: string; url: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: SourceDoc[];
}

const SOURCE_ICONS: Record<string, string> = {
  gmail: "✉️", slack: "💬", jira: "📋", teams: "💼",
  outlook: "📨", clickup: "✅", default: "📄",
};

const SOURCE_COLORS: Record<string, string> = {
  gmail: "#EA4335", slack: "#4A154B", jira: "#0052CC",
  teams: "#6264A7", outlook: "#0078D4", clickup: "#7B68EE",
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

// ── Rendu markdown → JSX propre ──────────────────────────────────────────────
function renderContent(text: string) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let listBuffer: string[] = [];
  let key = 0;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    elements.push(
      <ul key={key++} style={{ margin: "6px 0 6px 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
        {listBuffer.map((item, i) => (
          <li key={i} style={{ fontSize: 13, color: "#1e293b", lineHeight: 1.6 }}>
            {renderInline(item)}
          </li>
        ))}
      </ul>
    );
    listBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) { flushList(); elements.push(<div key={key++} style={{ height: 6 }} />); continue; }

    // Titres **Texte** seuls sur une ligne
    const headingMatch = line.match(/^\*\*(.+)\*\*$/);
    if (headingMatch) {
      flushList();
      elements.push(
        <div key={key++} style={{ fontSize: 12, fontWeight: 700, color: "#3e5c76", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 10, marginBottom: 4, borderBottom: "1px solid rgba(62,92,118,0.12)", paddingBottom: 3 }}>
          {headingMatch[1]}
        </div>
      );
      continue;
    }

    // Items de liste * ou -
    const listMatch = line.match(/^[*\-•]\s+(.+)/);
    if (listMatch) { listBuffer.push(listMatch[1]); continue; }

    // Paragraphe normal
    flushList();
    elements.push(
      <p key={key++} style={{ fontSize: 13, color: "#1e293b", lineHeight: 1.7, margin: "3px 0" }}>
        {renderInline(line)}
      </p>
    );
  }
  flushList();
  return elements;
}

function renderInline(text: string): React.ReactNode {
  // **gras**
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const bold = part.match(/^\*\*(.+)\*\*$/);
    if (bold) return <strong key={i} style={{ fontWeight: 700, color: "#0d1321" }}>{bold[1]}</strong>;
    // Sources [1], [2]... → badge subtil
    return <span key={i}>{part.replace(/\(Sources?\s*\[[\d,\s]+\]\)/gi, "").replace(/\(Source\s*\[[\d,\s]+\]\)/gi, "")}</span>;
  });
}

// ─────────────────────────────────────────────────────────────────────────────

export default function AskAnything() {
  const pathname = usePathname();
  const projectMatch = pathname?.match(/\/dashboard\/projects\/([^/]+)/);
  const projectId    = projectMatch ? projectMatch[1] : null;

  const [open, setOpen]               = useState(false);
  const [query, setQuery]             = useState("");
  const [messages, setMessages]       = useState<Message[]>([]);
  const [loading, setLoading]         = useState(false);
  const [indexed, setIndexed]         = useState<number | null>(null);
  const [reindexing, setReindexing]   = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [provider, setProvider]       = useState<"ollama" | "gpt">("ollama");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  const EXAMPLES = projectId ? EXAMPLES_PROJECT : EXAMPLES_GLOBAL;

  useEffect(() => {
    API.get("/api/ask/status").then(r => setIndexed(r.data.indexed_count)).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  // Réinitialise les suggestions si on vide la conversation
  useEffect(() => {
    if (messages.length === 0) setShowSuggestions(true);
  }, [messages]);

  const handleAsk = async (q?: string) => {
    const question = (q ?? query).trim();
    if (!question || loading) return;
    setQuery("");
    setShowSuggestions(false); // masque les suggestions dès qu'une question est posée
    setMessages(prev => [...prev, { role: "user", content: question }]);
    setLoading(true);
    try {
      let r;
      if (projectId) {
        r = await API.post(`/api/projects/${projectId}/ask`, { question, top_k: 8 });
      } else {
        r = await API.post("/api/ask", { query: question, top_k: 5, provider });
      }
      setMessages(prev => [...prev, { role: "assistant", content: r.data.answer, sources: r.data.sources }]);
      if (r.data.indexed_count !== undefined) setIndexed(r.data.indexed_count);
    } catch (e: any) {
      setMessages(prev => [...prev, { role: "assistant", content: `Erreur : impossible de contacter le serveur. (${e.message})` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      const r = await API.post("/api/ask/reindex", {});
      setIndexed(r.data.indexed);
      setMessages(prev => [...prev, { role: "assistant", content: `${r.data.indexed} messages indexés dans la base de connaissances.` }]);
    } catch (e: any) {
      setMessages(prev => [...prev, { role: "assistant", content: `Erreur lors de l'indexation : ${e.message}` }]);
    } finally {
      setReindexing(false);
    }
  };

  const handleClear = () => {
    setMessages([]);
    setShowSuggestions(true);
    setQuery("");
  };

  const formatDate = (iso: string) => {
    if (!iso) return "";
    try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }); }
    catch { return iso.slice(0, 10); }
  };

  return (
    <>
      <style>{`
        @keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-5px)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        .aria-msg { animation: fadeUp 0.25s ease; }
      `}</style>

      {/* ── Panneau ────────────────────────────────────────────────────────── */}
      <div style={{
        position: "fixed", bottom: 90, right: 24,
        width: 440, maxHeight: "75vh",
        background: "#fff", borderRadius: 22,
        boxShadow: "0 12px 48px rgba(13,19,33,0.2)",
        border: "1px solid rgba(62,92,118,0.12)",
        display: "flex", flexDirection: "column",
        zIndex: 1000, overflow: "hidden",
        transform: open ? "translateY(0) scale(1)" : "translateY(16px) scale(0.97)",
        opacity: open ? 1 : 0,
        pointerEvents: open ? "all" : "none",
        transition: "transform 0.22s cubic-bezier(.4,0,.2,1), opacity 0.18s ease",
      }}>

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div style={{ background: "linear-gradient(135deg, #1d2d44 0%, #2e4a6b 100%)", padding: "0.875rem 1.125rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {/* Avatar ARIA */}
            <div style={{ width: 36, height: 36, borderRadius: "50%", background: "linear-gradient(135deg, #748cab, #f0ebd8)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0 }}>
              🧠
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 800, color: "#f0ebd8", letterSpacing: "0.04em" }}>ARIA</div>
              <div style={{ fontSize: 10, color: "rgba(240,235,216,0.55)", letterSpacing: "0.05em" }}>
                {projectId ? "Contexte projet actif" : indexed !== null ? `${indexed} msgs · ${provider === "gpt" ? "GPT" : "Ollama"}` : "Executive Intelligence"}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {/* Provider toggle */}
            <div style={{ display: "flex", background: "rgba(0,0,0,0.25)", borderRadius: 8, padding: 2, gap: 2 }}>
              {(["ollama", "gpt"] as const).map(p => (
                <button
                  key={p}
                  onClick={() => setProvider(p)}
                  title={p === "ollama" ? "Ollama (local)" : "GPT (OpenAI)"}
                  style={{
                    padding: "3px 9px", borderRadius: 6, border: "none",
                    cursor: "pointer", fontSize: 11, fontWeight: 700,
                    background: provider === p ? "#f0ebd8" : "transparent",
                    color: provider === p ? "#1d2d44" : "rgba(240,235,216,0.5)",
                    transition: "all 0.15s",
                  }}
                >
                  {p === "ollama" ? "🦙 Ollama" : "✨ GPT"}
                </button>
              ))}
            </div>
            {messages.length > 0 && (
              <button onClick={handleClear} title="Nouvelle conversation" style={{ background: "rgba(255,255,255,0.1)", border: "1px solid rgba(240,235,216,0.2)", color: "rgba(240,235,216,0.7)", borderRadius: 8, padding: "4px 10px", fontSize: 11, cursor: "pointer", fontWeight: 600 }}>
                Effacer
              </button>
            )}
            <button onClick={handleReindex} disabled={reindexing} title="Réindexer" style={{ background: "rgba(255,255,255,0.1)", border: "1px solid rgba(240,235,216,0.2)", color: "#f0ebd8", borderRadius: 8, padding: "4px 10px", fontSize: 11, cursor: "pointer", fontWeight: 600 }}>
              {reindexing ? "⏳" : "↻"}
            </button>
            <button onClick={() => setOpen(false)} style={{ background: "rgba(255,255,255,0.1)", border: "none", color: "#f0ebd8", borderRadius: 8, width: 28, height: 28, cursor: "pointer", fontSize: 15, display: "flex", alignItems: "center", justifyContent: "center" }}>
              ✕
            </button>
          </div>
        </div>

        {/* ── Messages ───────────────────────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1rem", display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Écran de bienvenue */}
          {messages.length === 0 && (
            <div style={{ textAlign: "center", padding: "1.5rem 1rem 0.5rem" }}>
              <div style={{ width: 52, height: 52, borderRadius: "50%", background: "linear-gradient(135deg, #1d2d44, #3e5c76)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, margin: "0 auto 12px" }}>🧠</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#0d1321", marginBottom: 6 }}>Bonjour, je suis ARIA</div>
              <div style={{ fontSize: 12, color: "#748cab", lineHeight: 1.6 }}>
                {projectId
                  ? "Je connais ce projet — tâches, équipe, messages."
                  : "Votre assistante exécutive IA. Posez-moi une question sur vos emails, projets ou équipes."}
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((msg, i) => (
            <div key={i} className="aria-msg" style={{ display: "flex", flexDirection: msg.role === "user" ? "row-reverse" : "row", gap: 8, alignItems: "flex-start" }}>

              {/* Avatar */}
              <div style={{ width: 30, height: 30, borderRadius: "50%", flexShrink: 0, background: msg.role === "user" ? "linear-gradient(135deg,#3e5c76,#1d2d44)" : "linear-gradient(135deg,#e8f0fe,#c7d9f5)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>
                {msg.role === "user" ? "👤" : "🧠"}
              </div>

              <div style={{ maxWidth: "82%", display: "flex", flexDirection: "column", gap: 8 }}>

                {/* Bulle */}
                {msg.role === "user" ? (
                  <div style={{ padding: "0.625rem 0.9rem", borderRadius: "16px 4px 16px 16px", background: "linear-gradient(135deg,#1d2d44,#3e5c76)", color: "#f0ebd8", fontSize: 13, lineHeight: 1.6 }}>
                    {msg.content}
                  </div>
                ) : (
                  <div style={{ padding: "0.75rem 1rem", borderRadius: "4px 16px 16px 16px", background: "#f8fafc", border: "1px solid rgba(62,92,118,0.1)" }}>
                    {renderContent(msg.content)}
                  </div>
                )}

                {/* Sources */}
                {msg.sources && msg.sources.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    <div style={{ fontSize: 10, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", paddingLeft: 2 }}>Sources utilisées</div>
                    {msg.sources.map((src, j) => {
                      const srcColor = SOURCE_COLORS[src.source] ?? "#748cab";
                      return (
                        <div key={src.id} style={{ padding: "8px 10px", background: "#fff", border: `1px solid ${srcColor}25`, borderLeft: `3px solid ${srcColor}`, borderRadius: "0 10px 10px 0", fontSize: 11 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6, marginBottom: 3 }}>
                            <span style={{ fontWeight: 700, color: "#0d1321", lineHeight: 1.4, flex: 1 }}>
                              <span style={{ color: srcColor, marginRight: 4 }}>[{j+1}]</span>
                              {src.title || "(sans titre)"}
                            </span>
                            {src.business && (
                              <span style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 700, background: (BUSINESS_COLORS[src.business] ?? BUSINESS_COLORS.default) + "18", color: BUSINESS_COLORS[src.business] ?? BUSINESS_COLORS.default, flexShrink: 0 }}>
                                {src.business}
                              </span>
                            )}
                          </div>
                          <div style={{ color: "#748cab", display: "flex", gap: 6, alignItems: "center" }}>
                            <span>{SOURCE_ICONS[src.source] ?? SOURCE_ICONS.default}</span>
                            <span>{src.author}</span>
                            <span>·</span>
                            <span>{formatDate(src.timestamp)}</span>
                          </div>
                          {src.excerpt && (
                            <div style={{ color: "#475569", marginTop: 4, lineHeight: 1.5, fontStyle: "italic" }}>
                              "{src.excerpt.slice(0, 100)}{src.excerpt.length > 100 ? "…" : ""}"
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Typing indicator */}
          {loading && (
            <div className="aria-msg" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div style={{ width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg,#e8f0fe,#c7d9f5)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>🧠</div>
              <div style={{ padding: "0.625rem 0.875rem", background: "#f8fafc", border: "1px solid rgba(62,92,118,0.1)", borderRadius: "4px 16px 16px 16px", display: "flex", gap: 5, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "#748cab", marginRight: 4 }}>ARIA analyse</span>
                {[0,1,2].map(k => (
                  <div key={k} style={{ width: 6, height: 6, borderRadius: "50%", background: "#748cab", animation: "bounce 1.2s infinite", animationDelay: `${k * 0.2}s` }} />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* ── Suggestions — visibles uniquement avant la 1ère question ───── */}
        {showSuggestions && (
          <div style={{ padding: "0.625rem 1rem 0", borderTop: "1px solid rgba(62,92,118,0.08)", background: "#fff", flexShrink: 0 }}>
            <div style={{ fontSize: 10, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Suggestions</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {EXAMPLES.map(ex => (
                <button key={ex} onClick={() => handleAsk(ex)} disabled={loading} style={{ padding: "5px 11px", background: "rgba(62,92,118,0.06)", border: "1px solid rgba(62,92,118,0.15)", borderRadius: 20, fontSize: 11, color: "#3e5c76", cursor: "pointer", fontWeight: 500, whiteSpace: "nowrap", transition: "all 0.15s" }}
                  onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(62,92,118,0.12)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(62,92,118,0.06)"; }}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Input ──────────────────────────────────────────────────────── */}
        <div style={{ padding: "0.625rem 1rem 0.875rem", display: "flex", gap: 8, flexShrink: 0, background: "#fff", borderTop: showSuggestions ? "none" : "1px solid rgba(62,92,118,0.08)" }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleAsk()}
            placeholder="Posez une question à ARIA..."
            disabled={loading}
            style={{ flex: 1, padding: "0.625rem 0.875rem", border: "1.5px solid rgba(62,92,118,0.18)", borderRadius: 12, fontSize: 13, outline: "none", fontFamily: "inherit", background: "#f8fafc", transition: "border-color 0.15s" }}
            onFocus={e => { (e.target as HTMLInputElement).style.borderColor = "#3e5c76"; }}
            onBlur={e  => { (e.target as HTMLInputElement).style.borderColor = "rgba(62,92,118,0.18)"; }}
          />
          <button onClick={() => handleAsk()} disabled={loading || !query.trim()} style={{ width: 38, height: 38, borderRadius: 12, border: "none", flexShrink: 0, background: loading || !query.trim() ? "#e2e8f0" : "linear-gradient(135deg,#1d2d44,#3e5c76)", color: loading || !query.trim() ? "#94a3b8" : "#fff", cursor: loading || !query.trim() ? "not-allowed" : "pointer", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.15s" }}>
            ↑
          </button>
        </div>
      </div>

      {/* ── Bouton flottant ────────────────────────────────────────────────── */}
      <button onClick={() => setOpen(v => !v)} style={{ position: "fixed", bottom: 24, right: 24, width: 56, height: 56, borderRadius: "50%", background: open ? "#1d2d44" : "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)", border: "none", boxShadow: "0 4px 20px rgba(13,19,33,0.3)", cursor: "pointer", zIndex: 1001, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, color: "#f0ebd8", transition: "transform 0.2s, background 0.2s" }} title="ARIA — Executive Intelligence">
        {open ? "✕" : "🧠"}
      </button>
    </>
  );
}
