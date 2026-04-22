"use client";
import { useState, useRef, useEffect } from "react";
import API from "@/lib/api";
import MessageDetailModal from "./MessageDetailModal";
import { useI18n } from "@/lib/i18n";

const LABEL_COLORS: Record<string, string> = {
  Blocked: "#ef4444", Urgent: "#f97316", Risk: "#f59e0b",
  Conflict: "#8b5cf6", Overload: "#ec4899", Concern: "#eab308",
  Progress: "#22c55e", "Neutral Update": "#94a3b8",
};

export default function SearchBar() {
  const { t } = useI18n();
  const [query, setQuery]       = useState("");
  const [results, setResults]   = useState<any[]>([]);
  const [open, setOpen]         = useState(false);
  const [loading, setLoading]   = useState(false);
  const [detail, setDetail]     = useState<any | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const search = (q: string) => {
    if (!q.trim()) { setResults([]); setOpen(false); return; }
    setLoading(true);
    API.get(`/api/search?q=${encodeURIComponent(q)}&limit=8&since_days=90`)
      .then(r => { setResults(r.data.items ?? []); setOpen(true); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => search(val), 350);
  };

  return (
    <div ref={ref} style={{ position: "relative", width: "100%", maxWidth: 420 }}>
      <div style={{ position: "relative" }}>
        <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", fontSize: 14, color: "#748cab" }}>🔍</span>
        <input
          value={query}
          onChange={handleChange}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={t.search_ph}
          style={{
            width: "100%", padding: "9px 12px 9px 34px",
            border: "1px solid rgba(62,92,118,0.2)", borderRadius: 12,
            fontSize: 13, color: "#0d1321", background: "#f8f9fa",
            outline: "none", boxSizing: "border-box",
          }}
        />
        {loading && (
          <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", fontSize: 11, color: "#748cab" }}>...</span>
        )}
      </div>

      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0,
          background: "#fff", borderRadius: 14, boxShadow: "0 8px 32px rgba(13,19,33,0.15)",
          border: "1px solid rgba(62,92,118,0.12)", zIndex: 200, overflow: "hidden",
        }}>
          {results.map(item => {
            const bl = item.business_label || "Neutral Update";
            const blColor = LABEL_COLORS[bl] ?? "#94a3b8";
            return (
              <div key={item.id}
                onClick={() => { setDetail(item); setOpen(false); }}
                style={{ padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid rgba(62,92,118,0.06)", transition: "background 0.1s" }}
                onMouseEnter={e => (e.currentTarget.style.background = "#f5f7fa")}
                onMouseLeave={e => (e.currentTarget.style.background = "#fff")}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 10, background: `${blColor}18`, color: blColor, flexShrink: 0 }}>{bl}</span>
                  <span style={{ fontSize: 13, fontWeight: 500, color: "#0d1321", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.title}</span>
                </div>
                <div style={{ fontSize: 11, color: "#748cab", marginTop: 3 }}>
                  {item.author} · {new Date(item.timestamp).toLocaleDateString("fr-FR")}
                </div>
              </div>
            );
          })}
          <div style={{ padding: "8px 14px", fontSize: 11, color: "#748cab", background: "#f8f9fa" }}>
            {t.search_results(results.length)}
          </div>
        </div>
      )}

      {detail && (
        <MessageDetailModal
          item={{ ...detail, snippet: detail.snippet }}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}
