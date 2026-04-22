"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface Decision {
  id: number;
  title: string;
  context?: string;
  status: "pending" | "decided" | "cancelled";
  created_at: string;
  decided_at?: string;
}

const STATUS_META = {
  pending:   { label: "En attente",  color: "#f59e0b", bg: "#fefce8" },
  decided:   { label: "Décidé",      color: "#22c55e", bg: "#f0fdf4" },
  cancelled: { label: "Annulé",      color: "#94a3b8", bg: "#f8fafc" },
};

export default function DecisionLog() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading]     = useState(true);
  const [form, setForm]           = useState({ title: "", context: "" });
  const [adding, setAdding]       = useState(false);
  const [saving, setSaving]       = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const reload = () => {
    setLoading(true);
    API.get("/api/decisions")
      .then(r => setDecisions(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const submit = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    await API.post("/api/decisions", { title: form.title, context: form.context || undefined });
    setForm({ title: "", context: "" });
    setAdding(false);
    setSaving(false);
    reload();
  };

  const setStatus = async (id: number, status: Decision["status"]) => {
    await API.patch(`/api/decisions/${id}`, { status });
    setDecisions(prev => prev.map(d => d.id === id ? { ...d, status } : d));
  };

  const remove = async (id: number) => {
    await API.delete(`/api/decisions/${id}`);
    setDecisions(prev => prev.filter(d => d.id !== id));
  };

  const pending   = decisions.filter(d => d.status === "pending");
  const decided   = decisions.filter(d => d.status === "decided");
  const cancelled = decisions.filter(d => d.status === "cancelled");

  return (
    <div style={{ background: "#fff", borderRadius: 20, padding: "1.5rem 1.75rem", boxShadow: "0 2px 20px rgba(13,19,33,0.07)", border: "1px solid rgba(62,92,118,0.1)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>
            Décisions
          </div>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>
            Journal des décisions
            {pending.length > 0 && (
              <span style={{ marginLeft: 10, fontSize: 12, background: "#fefce8", color: "#a16207", border: "1px solid #fde68a", borderRadius: 20, padding: "2px 10px", fontFamily: "DM Sans, sans-serif" }}>
                {pending.length} en attente
              </span>
            )}
          </h2>
        </div>
        <button
          onClick={() => setAdding(v => !v)}
          style={{
            padding: "7px 16px", borderRadius: 10, border: "none", cursor: "pointer",
            background: adding ? "rgba(62,92,118,0.1)" : "linear-gradient(135deg, #1d2d44, #3e5c76)",
            color: adding ? "#3e5c76" : "#fff", fontSize: 12, fontWeight: 600,
          }}
        >
          {adding ? "✕ Annuler" : "＋ Ajouter"}
        </button>
      </div>

      {/* Form */}
      {adding && (
        <div style={{ background: "rgba(62,92,118,0.04)", borderRadius: 12, padding: "1rem", marginBottom: "1.25rem", border: "1px solid rgba(62,92,118,0.12)" }}>
          <input
            value={form.title}
            onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
            placeholder="Décision à prendre ou prise..."
            style={{ width: "100%", fontSize: 13, padding: "8px 12px", border: "1px solid rgba(62,92,118,0.2)", borderRadius: 8, outline: "none", marginBottom: 8, fontFamily: "DM Sans, sans-serif" }}
          />
          <textarea
            value={form.context}
            onChange={e => setForm(p => ({ ...p, context: e.target.value }))}
            placeholder="Contexte, raisons, personnes impliquées... (optionnel)"
            rows={3}
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", border: "1px solid rgba(62,92,118,0.2)", borderRadius: 8, outline: "none", resize: "vertical", fontFamily: "DM Sans, sans-serif", color: "#3e5c76" }}
          />
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
            <button
              onClick={submit}
              disabled={saving || !form.title.trim()}
              style={{ padding: "7px 20px", borderRadius: 8, border: "none", cursor: "pointer", background: "#3e5c76", color: "#fff", fontSize: 13, fontWeight: 600, opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Enregistrement..." : "Enregistrer"}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p style={{ color: "#748cab", fontSize: 13, textAlign: "center", padding: "1.5rem" }}>Chargement...</p>
      ) : decisions.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem", color: "#748cab" }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
          <p style={{ fontSize: 13 }}>Aucune décision enregistrée</p>
        </div>
      ) : (
        <div>
          {/* Pending */}
          {pending.length > 0 && (
            <div style={{ marginBottom: "1rem" }}>
              {pending.map(d => <DecisionRow key={d.id} d={d} expanded={expandedId === d.id} onExpand={id => setExpandedId(v => v === id ? null : id)} onStatus={setStatus} onDelete={remove} />)}
            </div>
          )}

          {/* Decided */}
          {decided.length > 0 && (
            <div style={{ marginBottom: "0.75rem" }}>
              <div style={{ fontSize: 11, color: "#22c55e", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                Décidées ({decided.length})
              </div>
              {decided.map(d => <DecisionRow key={d.id} d={d} expanded={expandedId === d.id} onExpand={id => setExpandedId(v => v === id ? null : id)} onStatus={setStatus} onDelete={remove} />)}
            </div>
          )}

          {/* Cancelled */}
          {cancelled.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                Annulées ({cancelled.length})
              </div>
              {cancelled.map(d => <DecisionRow key={d.id} d={d} expanded={expandedId === d.id} onExpand={id => setExpandedId(v => v === id ? null : id)} onStatus={setStatus} onDelete={remove} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DecisionRow({ d, expanded, onExpand, onStatus, onDelete }: {
  d: Decision;
  expanded: boolean;
  onExpand: (id: number) => void;
  onStatus: (id: number, s: Decision["status"]) => void;
  onDelete: (id: number) => void;
}) {
  const meta = STATUS_META[d.status];
  return (
    <div style={{ borderBottom: "1px solid rgba(62,92,118,0.07)", paddingBottom: 10, marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        {/* Status badge */}
        <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 20, background: meta.bg, color: meta.color, border: `1px solid ${meta.color}40`, whiteSpace: "nowrap", marginTop: 2, flexShrink: 0 }}>
          {meta.label}
        </span>

        {/* Title */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            onClick={() => onExpand(d.id)}
            style={{ fontSize: 13, fontWeight: 600, color: d.status === "cancelled" ? "#94a3b8" : "#0d1321", cursor: "pointer", textDecoration: d.status === "cancelled" ? "line-through" : "none" }}
          >
            {d.title}
          </div>
          <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>
            {new Date(d.created_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })}
            {d.decided_at && ` · Décidé le ${new Date(d.decided_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}`}
          </div>
          {expanded && d.context && (
            <div style={{ marginTop: 6, fontSize: 12, color: "#3e5c76", background: "rgba(62,92,118,0.05)", borderRadius: 8, padding: "8px 10px", lineHeight: 1.6 }}>
              {d.context}
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {d.status !== "decided" && (
            <button onClick={() => onStatus(d.id, "decided")} title="Marquer comme décidé"
              style={{ padding: "4px 8px", borderRadius: 7, border: "1px solid #86efac", background: "#f0fdf4", color: "#16a34a", fontSize: 11, cursor: "pointer", fontWeight: 600 }}>
              ✓
            </button>
          )}
          {d.status !== "cancelled" && (
            <button onClick={() => onStatus(d.id, "cancelled")} title="Annuler"
              style={{ padding: "4px 8px", borderRadius: 7, border: "1px solid rgba(148,163,184,0.3)", background: "#f8fafc", color: "#94a3b8", fontSize: 11, cursor: "pointer" }}>
              ✕
            </button>
          )}
          {d.status !== "pending" && (
            <button onClick={() => onStatus(d.id, "pending")} title="Remettre en attente"
              style={{ padding: "4px 8px", borderRadius: 7, border: "1px solid #fde68a", background: "#fefce8", color: "#a16207", fontSize: 11, cursor: "pointer" }}>
              ↩
            </button>
          )}
          <button onClick={() => onDelete(d.id)} title="Supprimer"
            style={{ padding: "4px 8px", borderRadius: 7, border: "none", background: "none", color: "#ef444460", fontSize: 13, cursor: "pointer" }}>
            🗑
          </button>
        </div>
      </div>
    </div>
  );
}
