"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

const SEVERITY_COLOR: Record<string, string> = {
  high:   "#ef4444",
  medium: "#f59e0b",
  low:    "#22c55e",
};

const SEVERITY_LABEL: Record<string, string> = {
  high:   "Critique",
  medium: "Modéré",
  low:    "Faible",
};

const SOURCE_ICON: Record<string, string> = {
  gmail: "✉️", jira: "📋", slack: "💬",
};

interface AnomalyEvent {
  id: number;
  source: string;
  metric: string;
  current_value: number;
  baseline_value: number;
  anomaly_score: number;
  severity: string;
  description: string;
  detected_at: string;
  is_read: boolean;
}

interface WarmupStatus {
  ready: boolean;
  days_available: number;
  days_needed: number;
}

export default function AnomalyCard() {
  const [events, setEvents]   = useState<AnomalyEvent[]>([]);
  const [status, setStatus]   = useState<Record<string, WarmupStatus>>({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [msg, setMsg]         = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      API.get("/api/anomaly/events?since_days=7&limit=10"),
      API.get("/api/anomaly/status"),
    ])
      .then(([evRes, stRes]) => {
        setEvents(evRes.data.events ?? []);
        setStatus(stRes.data.sources ?? {});
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const runNow = async () => {
    setRunning(true);
    setMsg(null);
    try {
      const r = await API.post("/api/anomaly/run");
      setMsg(`${r.data.anomalies_detected} anomalie(s) détectée(s)`);
      load();
    } catch {
      setMsg("Erreur lors de la détection");
    } finally {
      setRunning(false);
    }
  };

  const markRead = async (id: number) => {
    await API.patch(`/api/anomaly/events/${id}/read`);
    setEvents(prev => prev.map(e => e.id === id ? { ...e, is_read: true } : e));
  };

  const unread = events.filter(e => !e.is_read);
  const sourcesReady = Object.values(status).filter(s => s.ready).length;
  const sourcesTotal = Object.keys(status).length;

  return (
    <div style={{ background: "#fff", borderRadius: 20, padding: "1.5rem 1.75rem", boxShadow: "0 2px 20px rgba(13,19,33,0.07)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.5rem" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>
            Isolation Forest · Comportemental
          </div>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif", margin: 0 }}>
            Détection d'Anomalies
          </h2>
          {unread.length > 0 && (
            <span style={{ fontSize: 11, background: "#ef444420", color: "#ef4444", borderRadius: 20, padding: "2px 8px", fontWeight: 700, marginTop: 4, display: "inline-block" }}>
              {unread.length} non lue(s)
            </span>
          )}
        </div>
        <button
          onClick={runNow}
          disabled={running}
          style={{ padding: "6px 14px", borderRadius: 20, border: "1px solid rgba(62,92,118,0.3)", background: "rgba(62,92,118,0.06)", color: "#3e5c76", fontSize: 12, fontWeight: 500, cursor: running ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 5 }}
        >
          <span style={{ display: "inline-block", animation: running ? "spin 0.8s linear infinite" : "none" }}>↻</span>
          {running ? "Analyse..." : "Analyser"}
        </button>
      </div>

      {msg && (
        <div style={{ fontSize: 12, color: msg.startsWith("Erreur") ? "#ef4444" : "#22c55e", marginBottom: 12 }}>
          {msg}
        </div>
      )}

      {/* Warmup status */}
      {sourcesTotal > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: "1.25rem", flexWrap: "wrap" }}>
          {Object.entries(status).map(([src, s]) => (
            <div key={src} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, padding: "4px 10px", borderRadius: 20, background: s.ready ? "#22c55e15" : "#f59e0b15", border: `1px solid ${s.ready ? "#22c55e40" : "#f59e0b40"}`, color: s.ready ? "#16a34a" : "#d97706" }}>
              <span>{SOURCE_ICON[src] ?? "◈"}</span>
              <span style={{ fontWeight: 600 }}>{src}</span>
              <span>{s.ready ? "Actif" : `J+${s.days_needed - s.days_available}`}</span>
            </div>
          ))}
          {sourcesReady === 0 && (
            <p style={{ fontSize: 12, color: "#748cab", margin: 0 }}>
              Période d'apprentissage en cours — détection active dans quelques jours.
            </p>
          )}
        </div>
      )}

      {/* Events list */}
      {loading ? (
        <p style={{ color: "#748cab", fontSize: 13, textAlign: "center", padding: "1rem" }}>Chargement...</p>
      ) : events.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem", color: "#748cab" }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>✓</div>
          <div style={{ fontWeight: 600, fontSize: 14, color: "#0d1321" }}>Aucune anomalie détectée</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>Tous les patterns sont dans les normes habituelles</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {events.map(e => {
            const color = SEVERITY_COLOR[e.severity] ?? "#748cab";
            return (
              <div
                key={e.id}
                style={{
                  padding: "12px 14px",
                  borderRadius: 12,
                  border: `1px solid ${color}30`,
                  background: e.is_read ? "#f8f9fa" : `${color}08`,
                  opacity: e.is_read ? 0.7 : 1,
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span>{SOURCE_ICON[e.source] ?? "◈"}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: `${color}20`, color }}>{SEVERITY_LABEL[e.severity] ?? e.severity}</span>
                      <span style={{ fontSize: 11, color: "#748cab" }}>
                        {new Date(e.detected_at).toLocaleDateString("fr-FR")}
                      </span>
                    </div>
                    <p style={{ fontSize: 13, color: "#0d1321", margin: 0, lineHeight: 1.5 }}>
                      {e.description}
                    </p>
                    <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                      Score IF : {e.anomaly_score} · {e.metric} : {e.current_value} vs normale {e.baseline_value}
                    </div>
                  </div>
                  {!e.is_read && (
                    <button
                      onClick={() => markRead(e.id)}
                      style={{ flexShrink: 0, fontSize: 11, padding: "3px 10px", borderRadius: 20, border: "1px solid rgba(62,92,118,0.2)", background: "transparent", color: "#748cab", cursor: "pointer" }}
                    >
                      Lu
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
