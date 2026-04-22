"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const LABEL_COLORS: Record<string, string> = {
  Blocked: "#ef4444", Urgent: "#f97316", Risk: "#f59e0b",
  Conflict: "#8b5cf6", Overload: "#ec4899", Concern: "#eab308",
};

interface Action {
  id: number;
  message_id?: string;
  title: string;
  author?: string;
  source?: string;
  business_label?: string;
  note?: string;
  done: boolean;
  created_at: string;
}

export default function ActionItems() {
  const { t } = useI18n();
  const [actions, setActions] = useState<Action[]>([]);
  const [loading, setLoading] = useState(true);
  const [noteEdit, setNoteEdit] = useState<Record<number, string>>({});

  const reload = () => {
    setLoading(true);
    API.get("/api/actions")
      .then(r => setActions(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const toggle = async (id: number, done: boolean) => {
    await API.patch(`/api/actions/${id}`, { done });
    setActions(prev => prev.map(a => a.id === id ? { ...a, done } : a));
  };

  const saveNote = async (id: number) => {
    const note = noteEdit[id] ?? "";
    await API.patch(`/api/actions/${id}`, { note });
    setActions(prev => prev.map(a => a.id === id ? { ...a, note } : a));
    setNoteEdit(prev => { const n = { ...prev }; delete n[id]; return n; });
  };

  const remove = async (id: number) => {
    await fetch(`http://localhost:8000/api/actions/${id}`, { method: "DELETE" });
    setActions(prev => prev.filter(a => a.id !== id));
  };

  const pending = actions.filter(a => !a.done);
  const done    = actions.filter(a => a.done);

  return (
    <div style={{ background: "#fff", borderRadius: 20, padding: "1.5rem 1.75rem", boxShadow: "0 2px 20px rgba(13,19,33,0.07)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>{t.actions_badge}</div>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>
            {t.actions_title}
            {pending.length > 0 && (
              <span style={{ marginLeft: 10, fontSize: 12, background: "#fef2f2", color: "#ef4444", border: "1px solid #fecaca", borderRadius: 20, padding: "2px 10px", fontFamily: "DM Sans, sans-serif" }}>
                {t.actions_pending(pending.length)}
              </span>
            )}
          </h2>
        </div>
      </div>

      {loading ? (
        <p style={{ color: "#748cab", fontSize: 13, textAlign: "center" }}>{t.actions_loading}</p>
      ) : actions.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem", color: "#748cab" }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
          <p style={{ fontSize: 13 }}>{t.actions_empty}</p>
        </div>
      ) : (
        <div>
          {/* Pending */}
          {pending.map(action => {
            const blColor = LABEL_COLORS[action.business_label ?? ""] ?? "#748cab";
            return (
              <div key={action.id} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "10px 0", borderBottom: "1px solid rgba(62,92,118,0.07)" }}>
                <input type="checkbox" checked={false} onChange={() => toggle(action.id, true)}
                  style={{ marginTop: 3, width: 16, height: 16, cursor: "pointer", accentColor: "#3e5c76" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{action.title}</div>
                  <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>
                    {action.author && <span>{action.author} · </span>}
                    {action.business_label && (
                      <span style={{ color: blColor, fontWeight: 600 }}>{action.business_label} · </span>
                    )}
                    {new Date(action.created_at).toLocaleDateString("fr-FR")}
                  </div>
                  {/* Note */}
                  {noteEdit[action.id] !== undefined ? (
                    <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
                      <input value={noteEdit[action.id]} onChange={e => setNoteEdit(p => ({ ...p, [action.id]: e.target.value }))}
                        placeholder={t.actions_note_ph}
                        style={{ flex: 1, fontSize: 12, padding: "4px 8px", border: "1px solid rgba(62,92,118,0.2)", borderRadius: 6, outline: "none" }} />
                      <button onClick={() => saveNote(action.id)} style={{ fontSize: 11, padding: "4px 10px", borderRadius: 6, border: "none", background: "#3e5c76", color: "#fff", cursor: "pointer" }}>OK</button>
                    </div>
                  ) : (
                    action.note
                      ? <div style={{ fontSize: 12, color: "#3e5c76", marginTop: 4, fontStyle: "italic" }}>📝 {action.note}</div>
                      : <button onClick={() => setNoteEdit(p => ({ ...p, [action.id]: action.note ?? "" }))}
                          style={{ marginTop: 4, fontSize: 11, color: "#748cab", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                          {t.actions_add_note}
                        </button>
                  )}
                </div>
                <button onClick={() => remove(action.id)} style={{ color: "#ef4444", background: "none", border: "none", cursor: "pointer", fontSize: 14, padding: "0 4px" }}>✕</button>
              </div>
            );
          })}

          {/* Done */}
          {done.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>{t.actions_done(done.length)}</div>
              {done.map(action => (
                <div key={action.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", opacity: 0.5 }}>
                  <input type="checkbox" checked onChange={() => toggle(action.id, false)} style={{ width: 16, height: 16, cursor: "pointer", accentColor: "#22c55e" }} />
                  <span style={{ fontSize: 13, color: "#748cab", textDecoration: "line-through" }}>{action.title}</span>
                  <button onClick={() => remove(action.id)} style={{ marginLeft: "auto", color: "#748cab", background: "none", border: "none", cursor: "pointer", fontSize: 12 }}>✕</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
