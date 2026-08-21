"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface MLStatus {
  corrections: {
    pending_sentiment: number;
    pending_emotion: number;
    pending_business: number;
    total_pending: number;
    total_all_time: number;
    last_correction_at: string | null;
  };
  last_training: {
    task: string;
    run_id: string;
    eval_accuracy: number;
    eval_f1: number;
    train_samples: number;
    trained_at: string;
    model_path: string;
    label_distribution: Record<string, number>;
  } | null;
  training_in_progress: boolean;
  training_task: string | null;
  models: Record<string, { base_model_exists: boolean; latest_finetuned: string | null; versions_count: number }>;
  script_available: boolean;
}

interface DriftCheck {
  check:    string;
  status:   "ok" | "alert" | "warning" | "skipped" | "error";
  message?: string;
  reason?:  string;
  details?: Record<string, any>;
}

interface DriftReport {
  task:            string;
  overall_status:  "healthy" | "warning" | "alert" | "error" | "insufficient_data" | "no_report";
  recommendation?: string;
  generated_at?:   string;
  checks?:         DriftCheck[];
  // pour /drift (all)
  global_status?:  string;
  tasks?:          Record<string, DriftReport>;
}

const TASK_COLORS: Record<string, string> = {
  sentiment: "#3b82f6",
  emotion:   "#8b5cf6",
  business:  "#f59e0b",
  all:       "#22c55e",
};

const DRIFT_STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  healthy:           { color: "#16a34a", bg: "#f0fdf4", label: "Sain" },
  warning:           { color: "#d97706", bg: "#fffbeb", label: "Attention" },
  alert:             { color: "#ef4444", bg: "#fef2f2", label: "Alerte" },
  error:             { color: "#ef4444", bg: "#fef2f2", label: "Erreur" },
  insufficient_data: { color: "#748cab", bg: "#f8fafc", label: "Données insuffisantes" },
  no_report:         { color: "#748cab", bg: "#f8fafc", label: "Pas de rapport" },
};

interface AgentDecision {
  strategy:             string;
  root_cause:           string;
  reasoning:            string;
  label_filter:         string | null;
  confidence:           string;
  urgency:              string;
  estimated_improvement:string;
  llm_used:             boolean;
}

interface AgentLog {
  agent_run_id:     string;
  timestamp:        string;
  dry_run:          boolean;
  perception: {
    total_pending:        number;
    emotion_count:        number;
    sentiment_count:      number;
    emotion_systematic:   boolean;
    sentiment_systematic: boolean;
    dominant_emotion?:    { original_emotion: string; corrected_emotion: string; count: number } | null;
    dominant_sentiment?:  { original_sentiment: string; corrected_sentiment: string; count: number } | null;
    drift_emotion?:       string | null;
    drift_sentiment?:     string | null;
  };
  decision:    AgentDecision;
  execution: {
    executed:     boolean;
    status?:      string;
    task?:        string;
    label_filter?:string | null;
    reason?:      string;
  };
  duration_seconds: number;
}

const STRATEGY_LABELS: Record<string, string> = {
  targeted_emotion:   "Targeted emotion",
  targeted_sentiment: "Targeted sentiment",
  full_emotion:       "Full emotion retrain",
  full_sentiment:     "Full sentiment retrain",
  full_both:          "Full retrain (both)",
  wait:               "Wait — collect more data",
};

const URGENCY_COLORS: Record<string, string> = {
  immediate: "#ef4444",
  tonight:   "#f59e0b",
  can_wait:  "#22c55e",
};

export default function MLStatusCard() {
  const [status, setStatus]       = useState<MLStatus | null>(null);
  const [loading, setLoading]     = useState(true);
  const [retraining, setRetraining] = useState(false);
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null);
  const [expanded, setExpanded]   = useState(false);
  const [task, setTask]           = useState<"sentiment" | "emotion" | "all">("sentiment");
  const [drift, setDrift]               = useState<DriftReport | null>(null);
  const [driftLoading, setDriftLoading] = useState(false);
  const [scheduler, setScheduler]       = useState<any | null>(null);
  const [triggeringAuto, setTriggeringAuto] = useState(false);
  const [agentStatus, setAgentStatus]   = useState<any | null>(null);
  const [agentLogs, setAgentLogs]       = useState<AgentLog[]>([]);
  const [agentLogsExpanded, setAgentLogsExpanded] = useState(false);
  const [triggeringAgent, setTriggeringAgent] = useState(false);

  const fetchStatus = () => {
    API.get("/api/ml/status")
      .then(r => setStatus(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const fetchScheduler = () => {
    API.get("/api/ml/scheduler")
      .then(r => setScheduler(r.data))
      .catch(() => {});
  };

  const fetchAgentStatus = () => {
    API.get("/api/ml/agent/status")
      .then(r => setAgentStatus(r.data))
      .catch(() => {});
  };

  const fetchAgentLogs = () => {
    API.get("/api/ml/agent/log?n=10")
      .then(r => setAgentLogs(r.data.logs ?? []))
      .catch(() => {});
  };

  const handleTriggerAgent = async (dryRun = false) => {
    setTriggeringAgent(true);
    try {
      await API.post(`/api/ml/agent/trigger?dry_run=${dryRun}`, {});
      setRetrainMsg(`Agent autonome lancé${dryRun ? " (dry-run)" : ""}. Résultat dans quelques secondes...`);
      setTimeout(() => { fetchAgentStatus(); fetchAgentLogs(); fetchScheduler(); }, 5000);
    } catch (e: any) {
      setRetrainMsg(`Erreur agent : ${e.message}`);
    } finally {
      setTriggeringAgent(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchScheduler();
    fetchAgentStatus();
    const interval = setInterval(() => {
      if (status?.training_in_progress) fetchStatus();
      fetchScheduler();
      fetchAgentStatus();
    }, 15000);
    return () => clearInterval(interval);
  }, [status?.training_in_progress]);

  const handleRetrain = async () => {
    setRetraining(true);
    setRetrainMsg(null);
    try {
      const r = await API.post("/api/ml/retrain", { task, min_samples: 1, epochs: 3 });
      setRetrainMsg(r.data.message);
      setTimeout(fetchStatus, 2000);
    } catch (e: any) {
      setRetrainMsg(e.message ?? "Erreur lors du lancement");
    } finally {
      setRetraining(false);
    }
  };

  const handleDriftCheck = async () => {
    setDriftLoading(true);
    try {
      // Charger d'abord le dernier rapport (rapide)
      const r = await API.get(`/api/ml/drift/last?task=${task === "all" ? "sentiment" : task}`);
      setDrift(r.data);
    } catch {
      // Si pas de rapport → lancer le calcul complet
      try {
        const r = await API.get(`/api/ml/drift?task=${task}&window_days=30`);
        setDrift(r.data);
      } catch (e: any) {
        setRetrainMsg(`Erreur monitoring : ${e.message}`);
      }
    } finally {
      setDriftLoading(false);
    }
  };

  const handleTriggerAuto = async () => {
    setTriggeringAuto(true);
    try {
      await API.post("/api/ml/auto-retrain/trigger", {});
      setRetrainMsg("Vérification auto-retraining lancée. Résultat dans quelques instants...");
      setTimeout(() => { fetchScheduler(); fetchStatus(); }, 4000);
    } catch (e: any) {
      setRetrainMsg(`Erreur : ${e.message}`);
    } finally {
      setTriggeringAuto(false);
    }
  };

  const handleDriftRun = async () => {
    setDriftLoading(true);
    setDrift(null);
    try {
      const r = await API.get(`/api/ml/drift?task=${task}&window_days=30`);
      setDrift(r.data);
    } catch (e: any) {
      setRetrainMsg(`Erreur monitoring : ${e.message}`);
    } finally {
      setDriftLoading(false);
    }
  };

  const handleReload = async () => {
    try {
      await API.post("/api/ml/reload-models", {});
      setRetrainMsg("Modèles rechargés depuis le disque.");
    } catch (e: any) {
      setRetrainMsg(e.message);
    }
  };

  if (loading) return null;
  if (!status) return null;

  const total = status.corrections.total_pending;
  const hasEnough = total >= 1;
  const inProgress = status.training_in_progress;

  return (
    <div style={{
      background: "#fff",
      borderRadius: 20,
      border: "1px solid rgba(62,92,118,0.12)",
      boxShadow: "0 2px 20px rgba(13,19,33,0.06)",
      overflow: "hidden",
      marginBottom: "1.5rem",
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          padding: "1.25rem 1.75rem",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          cursor: "pointer",
          background: inProgress ? "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)" : "#fff",
          transition: "background 0.3s",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Pulse indicator */}
          <div style={{
            width: 10, height: 10, borderRadius: "50%",
            background: inProgress ? "#22c55e" : total > 0 ? "#f59e0b" : "#94a3b8",
            boxShadow: inProgress
              ? "0 0 0 3px rgba(34,197,94,0.3)"
              : total > 0 ? "0 0 0 3px rgba(245,158,11,0.2)" : "none",
            animation: inProgress ? "pulse 2s infinite" : "none",
            flexShrink: 0,
          }} />
          <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}`}</style>
          <div>
            <div style={{
              fontSize: 11, fontWeight: 700, letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: inProgress ? "rgba(240,235,216,0.7)" : "#748cab",
            }}>
              Continuous Learning
            </div>
            <div style={{
              fontSize: 14, fontWeight: 700,
              color: inProgress ? "#f0ebd8" : "#0d1321",
              marginTop: 2,
            }}>
              {inProgress
                ? `Fine-tuning en cours (${status.training_task})...`
                : `${total} correction${total !== 1 ? "s" : ""} disponible${total !== 1 ? "s" : ""}`}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Badges par tâche */}
          {[
            { label: "sentiment", count: status.corrections.pending_sentiment },
            { label: "emotion",   count: status.corrections.pending_emotion },
            { label: "business",  count: status.corrections.pending_business },
          ].filter(b => b.count > 0).map(b => (
            <span key={b.label} style={{
              fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
              background: `${TASK_COLORS[b.label]}20`, color: TASK_COLORS[b.label],
              border: `1px solid ${TASK_COLORS[b.label]}40`,
            }}>
              {b.label}: {b.count}
            </span>
          ))}
          <span style={{
            fontSize: 12, color: inProgress ? "rgba(240,235,216,0.5)" : "#748cab",
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s", display: "inline-block",
          }}>▾</span>
        </div>
      </div>

      {/* Corps expandable */}
      {expanded && (
        <div style={{ padding: "1.5rem 1.75rem", borderTop: "1px solid rgba(62,92,118,0.08)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>

            {/* Colonne gauche — Corrections */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab", marginBottom: 12 }}>
                Corrections humaines
              </div>
              {[
                { label: "Sentiment", count: status.corrections.pending_sentiment, color: TASK_COLORS.sentiment },
                { label: "Émotion",   count: status.corrections.pending_emotion,   color: TASK_COLORS.emotion },
                { label: "Business",  count: status.corrections.pending_business,  color: TASK_COLORS.business },
              ].map(row => (
                <div key={row.label} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: row.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: "#748cab", flex: 1 }}>{row.label}</span>
                  <span style={{
                    fontSize: 13, fontWeight: 700,
                    color: row.count > 0 ? "#0d1321" : "#94a3b8",
                  }}>
                    {row.count} en attente
                  </span>
                </div>
              ))}
              <div style={{ fontSize: 11, color: "#748cab", marginTop: 8 }}>
                Total historique : {status.corrections.total_all_time} correction{status.corrections.total_all_time !== 1 ? "s" : ""}
              </div>
              {status.corrections.last_correction_at && (
                <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                  Dernière correction : {new Date(status.corrections.last_correction_at).toLocaleString("fr-FR")}
                </div>
              )}
            </div>

            {/* Colonne droite — Dernier fine-tuning */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab", marginBottom: 12 }}>
                Dernier fine-tuning
              </div>
              {status.last_training ? (
                <div>
                  <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                    {[
                      { label: "F1-macro",  value: `${(status.last_training.eval_f1 * 100).toFixed(1)}%`,   color: status.last_training.eval_f1 > 0.9 ? "#22c55e" : "#f59e0b" },
                      { label: "Accuracy",  value: `${(status.last_training.eval_accuracy * 100).toFixed(1)}%`, color: status.last_training.eval_accuracy > 0.9 ? "#22c55e" : "#f59e0b" },
                      { label: "Samples",   value: status.last_training.train_samples, color: "#3e5c76" },
                    ].map(m => (
                      <div key={m.label} style={{
                        flex: 1, background: `${m.color}10`,
                        border: `1px solid ${m.color}30`,
                        borderRadius: 10, padding: "6px 10px", textAlign: "center",
                      }}>
                        <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em" }}>{m.label}</div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: m.color, marginTop: 2 }}>{m.value}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>
                    Tâche : <strong style={{ color: TASK_COLORS[status.last_training.task] ?? "#3e5c76" }}>{status.last_training.task}</strong>
                    &nbsp;·&nbsp;{new Date(status.last_training.trained_at).toLocaleString("fr-FR")}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab", marginTop: 4, wordBreak: "break-all" }}>
                    Run : {status.last_training.run_id}
                  </div>
                  {/* Distribution des labels */}
                  {status.last_training.label_distribution && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 11, color: "#748cab", marginBottom: 6 }}>Distribution d'entraînement :</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {Object.entries(status.last_training.label_distribution).map(([lbl, cnt]) => (
                          <span key={lbl} style={{
                            fontSize: 10, padding: "2px 8px", borderRadius: 20,
                            background: "rgba(62,92,118,0.08)", color: "#3e5c76",
                          }}>
                            {lbl}: {cnt}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 13, color: "#748cab", padding: "1rem", textAlign: "center", background: "rgba(62,92,118,0.04)", borderRadius: 10 }}>
                  Aucun fine-tuning effectué.<br />
                  <span style={{ fontSize: 11 }}>Faites au moins {1} correction puis lancez le fine-tuning.</span>
                </div>
              )}
            </div>
          </div>

          {/* Modèles disponibles */}
          <div style={{ marginTop: "1.25rem", padding: "12px 16px", background: "rgba(62,92,118,0.04)", borderRadius: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab", marginBottom: 8 }}>
              Modèles en mémoire
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              {Object.entries(status.models).map(([task_name, info]) => (
                <div key={task_name} style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: TASK_COLORS[task_name] ?? "#3e5c76", marginBottom: 4 }}>
                    {task_name}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>
                    Base : {info.base_model_exists ? <span style={{ color: "#22c55e" }}>✓ présent</span> : <span style={{ color: "#ef4444" }}>✗ absent</span>}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab" }}>
                    Fine-tunés : {info.versions_count} version{info.versions_count !== 1 ? "s" : ""}
                  </div>
                  {info.latest_finetuned && (
                    <div style={{ fontSize: 10, color: "#748cab", marginTop: 2, wordBreak: "break-all" }}>
                      Latest : {info.latest_finetuned}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div style={{ marginTop: "1.25rem", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            {/* Sélecteur de tâche */}
            <select
              value={task}
              onChange={e => setTask(e.target.value as any)}
              disabled={inProgress || retraining}
              style={{
                padding: "8px 12px", borderRadius: 10, border: "1px solid rgba(62,92,118,0.2)",
                fontSize: 13, color: "#3e5c76", background: "#f8f9fa", cursor: "pointer",
              }}
            >
              <option value="sentiment">Fine-tuner sentiment</option>
              <option value="emotion">Fine-tuner émotion</option>
              <option value="all">Tout fine-tuner</option>
            </select>

            {/* Bouton retrain */}
            <button
              onClick={handleRetrain}
              disabled={inProgress || retraining || !hasEnough || !status.script_available}
              title={!hasEnough ? "Minimum 1 correction requise" : !status.script_available ? "Script introuvable" : ""}
              style={{
                padding: "8px 20px", borderRadius: 10, border: "none",
                background: (inProgress || retraining || !hasEnough)
                  ? "rgba(62,92,118,0.2)"
                  : "linear-gradient(135deg, #1d2d44, #3e5c76)",
                color: (inProgress || retraining || !hasEnough) ? "#748cab" : "#f0ebd8",
                fontSize: 13, fontWeight: 600,
                cursor: (inProgress || retraining || !hasEnough) ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", gap: 6,
              }}
            >
              <span style={{ animation: (inProgress || retraining) ? "spin 1s linear infinite" : "none", display: "inline-block" }}>⚙</span>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
              {inProgress ? "Fine-tuning en cours..." : retraining ? "Lancement..." : "Lancer le fine-tuning"}
            </button>

            {/* Bouton reload */}
            {status.last_training && (
              <button
                onClick={handleReload}
                style={{
                  padding: "8px 16px", borderRadius: 10,
                  border: "1px solid rgba(62,92,118,0.2)",
                  background: "transparent", color: "#748cab",
                  fontSize: 12, cursor: "pointer",
                }}
              >
                ↺ Recharger modèles
              </button>
            )}
          </div>

          {/* Message feedback */}
          {retrainMsg && (
            <div style={{
              marginTop: 10, padding: "8px 14px", borderRadius: 8, fontSize: 12,
              background: retrainMsg.toLowerCase().includes("erreur") ? "#fef2f2" : "#f0fdf4",
              color: retrainMsg.toLowerCase().includes("erreur") ? "#ef4444" : "#16a34a",
              border: `1px solid ${retrainMsg.toLowerCase().includes("erreur") ? "#fecaca" : "#86efac"}`,
            }}>
              {retrainMsg}
            </div>
          )}

          {!status.script_available && (
            <div style={{ marginTop: 10, fontSize: 12, color: "#f59e0b" }}>
              ⚠ Script ml/continuous_learning.py introuvable — vérifiez le chemin.
            </div>
          )}

          {/* ── Auto-Retraining Scheduler ── */}
          {scheduler && (
            <div style={{
              marginTop: "1.5rem", borderTop: "1px solid rgba(62,92,118,0.1)", paddingTop: "1.25rem",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab" }}>
                  Auto-Retraining
                </div>
                <button
                  onClick={handleTriggerAuto}
                  disabled={triggeringAuto || status?.training_in_progress}
                  title="Lancer la vérification maintenant"
                  style={{
                    padding: "5px 12px", borderRadius: 8, border: "none",
                    background: triggeringAuto ? "rgba(62,92,118,0.2)" : "rgba(62,92,118,0.12)",
                    color: "#3e5c76", fontSize: 11, cursor: triggeringAuto ? "not-allowed" : "pointer", fontWeight: 600,
                  }}
                >
                  {triggeringAuto ? "⏳ Vérification..." : "▷ Vérifier maintenant"}
                </button>
              </div>

              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {/* Statut */}
                <div style={{
                  flex: 1, minWidth: 160,
                  padding: "10px 14px", borderRadius: 10,
                  background: scheduler.enabled ? "#f0fdf4" : "#f8fafc",
                  border: `1px solid ${scheduler.enabled ? "#86efac" : "rgba(62,92,118,0.1)"}`,
                }}>
                  <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Statut</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                      background: scheduler.enabled && scheduler.running ? "#22c55e" : "#94a3b8",
                    }} />
                    <span style={{ fontSize: 13, fontWeight: 700, color: scheduler.enabled ? "#16a34a" : "#748cab" }}>
                      {scheduler.enabled && scheduler.running ? "Actif" : scheduler.enabled ? "En attente" : "Désactivé"}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                    {scheduler.schedule}
                  </div>
                </div>

                {/* Prochain run */}
                <div style={{
                  flex: 1, minWidth: 160,
                  padding: "10px 14px", borderRadius: 10,
                  background: "rgba(62,92,118,0.04)",
                  border: "1px solid rgba(62,92,118,0.1)",
                }}>
                  <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Prochain run</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>
                    {scheduler.next_run
                      ? new Date(scheduler.next_run).toLocaleString("fr-FR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" })
                      : "—"}
                  </div>
                  <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                    Seuil : {scheduler.min_samples} corrections
                  </div>
                </div>

                {/* Dernier run */}
                {scheduler.last_run?.triggered_at && (
                  <div style={{
                    flex: 1, minWidth: 160,
                    padding: "10px 14px", borderRadius: 10,
                    background: scheduler.last_run.status === "completed" ? "#f0fdf4" : "rgba(62,92,118,0.04)",
                    border: `1px solid ${scheduler.last_run.status === "completed" ? "#86efac" : "rgba(62,92,118,0.1)"}`,
                  }}>
                    <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Dernier run</div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#0d1321" }}>
                      {new Date(scheduler.last_run.triggered_at).toLocaleString("fr-FR")}
                    </div>
                    <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>
                      {scheduler.last_run.status === "no_action_needed" && "✓ Rien à faire"}
                      {scheduler.last_run.status === "completed" && `✓ ${scheduler.last_run.tasks_launched?.join(", ")} entraîné(s)`}
                      {scheduler.last_run.status === "never_run" && "Jamais lancé"}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Autonomous Agent ── */}
          <div style={{ marginTop: "1.5rem", borderTop: "1px solid rgba(62,92,118,0.1)", paddingTop: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab" }}>
                  Autonomous Agent
                </div>
                {agentStatus?.last_decision && (
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
                    background: agentStatus.last_decision.llm_used ? "#3b82f620" : "rgba(62,92,118,0.1)",
                    color: agentStatus.last_decision.llm_used ? "#3b82f6" : "#748cab",
                    border: `1px solid ${agentStatus.last_decision.llm_used ? "#3b82f640" : "rgba(62,92,118,0.15)"}`,
                  }}>
                    {agentStatus.last_decision.llm_used ? "LLM reasoning" : "Rule-based"}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => handleTriggerAgent(true)}
                  disabled={triggeringAgent}
                  title="Analyze without executing (dry-run)"
                  style={{
                    padding: "5px 12px", borderRadius: 8,
                    border: "1px solid rgba(62,92,118,0.2)",
                    background: "#f8f9fa", color: "#3e5c76",
                    fontSize: 11, cursor: triggeringAgent ? "not-allowed" : "pointer", fontWeight: 500,
                  }}
                >
                  {triggeringAgent ? "⏳" : "Dry-run"}
                </button>
                <button
                  onClick={() => handleTriggerAgent(false)}
                  disabled={triggeringAgent || status?.training_in_progress}
                  title="Run agent — analyze and act"
                  style={{
                    padding: "5px 12px", borderRadius: 8, border: "none",
                    background: (triggeringAgent || status?.training_in_progress)
                      ? "rgba(62,92,118,0.2)"
                      : "linear-gradient(135deg,#1d2d44,#3e5c76)",
                    color: (triggeringAgent || status?.training_in_progress) ? "#748cab" : "#f0ebd8",
                    fontSize: 11, cursor: (triggeringAgent || status?.training_in_progress) ? "not-allowed" : "pointer",
                    fontWeight: 600,
                  }}
                >
                  ▷ Run Agent
                </button>
              </div>
            </div>

            {/* Last agent decision */}
            {agentStatus?.last_decision ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* Strategy + urgency */}
                <div style={{
                  display: "flex", gap: 10, flexWrap: "wrap",
                }}>
                  <div style={{
                    flex: 2, minWidth: 200,
                    padding: "10px 14px", borderRadius: 10,
                    background: "rgba(62,92,118,0.04)",
                    border: "1px solid rgba(62,92,118,0.1)",
                  }}>
                    <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
                      Strategy
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>
                      {STRATEGY_LABELS[agentStatus.last_decision.strategy] ?? agentStatus.last_decision.strategy}
                    </div>
                    {agentStatus.last_decision.label_filter && (
                      <div style={{ fontSize: 11, color: "#748cab", marginTop: 3 }}>
                        Labels: <strong style={{ color: "#8b5cf6" }}>{agentStatus.last_decision.label_filter}</strong>
                      </div>
                    )}
                  </div>

                  <div style={{
                    flex: 1, minWidth: 120,
                    padding: "10px 14px", borderRadius: 10,
                    background: `${URGENCY_COLORS[agentStatus.last_decision.urgency] ?? "#748cab"}10`,
                    border: `1px solid ${URGENCY_COLORS[agentStatus.last_decision.urgency] ?? "#748cab"}30`,
                  }}>
                    <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Urgency</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: URGENCY_COLORS[agentStatus.last_decision.urgency] ?? "#748cab" }}>
                      {agentStatus.last_decision.urgency?.replace("_", " ")}
                    </div>
                    <div style={{ fontSize: 10, color: "#748cab", marginTop: 2 }}>
                      conf: {agentStatus.last_decision.confidence}
                    </div>
                  </div>

                  <div style={{
                    flex: 1, minWidth: 120,
                    padding: "10px 14px", borderRadius: 10,
                    background: agentStatus.executed ? "#f0fdf4" : "rgba(62,92,118,0.04)",
                    border: `1px solid ${agentStatus.executed ? "#86efac" : "rgba(62,92,118,0.1)"}`,
                  }}>
                    <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Execution</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: agentStatus.executed ? "#16a34a" : "#748cab" }}>
                      {agentStatus.executed ? "✓ Executed" : "— Not run"}
                    </div>
                    {agentStatus.timestamp && (
                      <div style={{ fontSize: 10, color: "#748cab", marginTop: 2 }}>
                        {new Date(agentStatus.timestamp).toLocaleString("fr-FR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" })}
                      </div>
                    )}
                  </div>
                </div>

                {/* Root cause */}
                <div style={{
                  padding: "10px 14px", borderRadius: 10,
                  background: "rgba(62,92,118,0.03)",
                  border: "1px solid rgba(62,92,118,0.08)",
                }}>
                  <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Root cause</div>
                  <div style={{ fontSize: 12, color: "#0d1321", lineHeight: 1.5 }}>
                    {agentStatus.last_decision.root_cause}
                  </div>
                </div>

                {/* Reasoning */}
                <div style={{
                  padding: "10px 14px", borderRadius: 10,
                  background: "rgba(62,92,118,0.03)",
                  border: "1px solid rgba(62,92,118,0.08)",
                }}>
                  <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Reasoning</div>
                  <div style={{ fontSize: 12, color: "#3e5c76", lineHeight: 1.5, fontStyle: "italic" }}>
                    {agentStatus.last_decision.reasoning}
                  </div>
                  {agentStatus.last_decision.estimated_improvement && agentStatus.last_decision.estimated_improvement !== "N/A" && (
                    <div style={{ fontSize: 11, color: "#22c55e", marginTop: 4 }}>
                      Expected: {agentStatus.last_decision.estimated_improvement}
                    </div>
                  )}
                </div>

                {/* History toggle */}
                <div>
                  <button
                    onClick={() => { setAgentLogsExpanded(v => !v); if (!agentLogsExpanded) fetchAgentLogs(); }}
                    style={{
                      background: "none", border: "none", cursor: "pointer",
                      fontSize: 11, color: "#748cab", padding: 0,
                      display: "flex", alignItems: "center", gap: 4,
                    }}
                  >
                    <span style={{ transform: agentLogsExpanded ? "rotate(180deg)" : "rotate(0deg)", display: "inline-block", transition: "transform 0.2s" }}>▾</span>
                    {agentLogsExpanded ? "Hide" : "Show"} decision history ({agentLogs.length > 0 ? agentLogs.length : "..."} runs)
                  </button>

                  {agentLogsExpanded && agentLogs.length > 0 && (
                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                      {agentLogs.map((log, i) => (
                        <div key={log.agent_run_id ?? i} style={{
                          display: "flex", alignItems: "center", gap: 10,
                          padding: "6px 12px", borderRadius: 8,
                          background: i === 0 ? "rgba(62,92,118,0.06)" : "transparent",
                          border: "1px solid rgba(62,92,118,0.07)",
                          fontSize: 11,
                        }}>
                          <span style={{ color: "#748cab", minWidth: 110, flexShrink: 0 }}>
                            {new Date(log.timestamp).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                          </span>
                          <span style={{
                            fontWeight: 600,
                            color: log.decision.strategy === "wait" ? "#94a3b8" : "#3e5c76",
                            minWidth: 160,
                          }}>
                            {STRATEGY_LABELS[log.decision.strategy] ?? log.decision.strategy}
                          </span>
                          {log.decision.label_filter && (
                            <span style={{ color: "#8b5cf6" }}>→ {log.decision.label_filter}</span>
                          )}
                          <span style={{ color: log.execution.executed ? "#22c55e" : "#94a3b8", marginLeft: "auto" }}>
                            {log.execution.executed ? `✓ ${log.execution.status}` : log.dry_run ? "dry-run" : "—"}
                          </span>
                          <span style={{ color: "#748cab", minWidth: 50, textAlign: "right" }}>
                            {log.duration_seconds?.toFixed(1)}s
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div style={{
                fontSize: 13, color: "#748cab", padding: "1rem", textAlign: "center",
                background: "rgba(62,92,118,0.03)", borderRadius: 10,
              }}>
                Agent not yet run.<br />
                <span style={{ fontSize: 11 }}>Click "Run Agent" or "Dry-run" to start analysis.</span>
              </div>
            )}
          </div>

          {/* ── Monitoring / Drift Detection ── */}
          <div style={{ marginTop: "1.5rem", borderTop: "1px solid rgba(62,92,118,0.1)", paddingTop: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab" }}>
                Monitoring — Drift Detection
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={handleDriftCheck}
                  disabled={driftLoading}
                  title="Charger le dernier rapport"
                  style={{
                    padding: "5px 12px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.2)",
                    background: "#f8f9fa", color: "#3e5c76",
                    fontSize: 11, cursor: driftLoading ? "not-allowed" : "pointer", fontWeight: 500,
                  }}
                >
                  {driftLoading ? "⏳" : "Dernier rapport"}
                </button>
                <button
                  onClick={handleDriftRun}
                  disabled={driftLoading}
                  title="Lancer un nouveau check de drift"
                  style={{
                    padding: "5px 12px", borderRadius: 8, border: "none",
                    background: driftLoading ? "rgba(62,92,118,0.2)" : "linear-gradient(135deg,#1d2d44,#3e5c76)",
                    color: driftLoading ? "#748cab" : "#f0ebd8",
                    fontSize: 11, cursor: driftLoading ? "not-allowed" : "pointer", fontWeight: 600,
                  }}
                >
                  {driftLoading ? "Analyse..." : "Analyser maintenant"}
                </button>
              </div>
            </div>

            {drift && (() => {
              // Normaliser : le rapport peut être "all" (tasks) ou mono-task
              const tasks: Record<string, any> = drift.tasks
                ? drift.tasks
                : { [drift.task]: drift };
              const globalStatus = drift.global_status ?? drift.overall_status ?? "no_report";
              const cfg = DRIFT_STATUS_CONFIG[globalStatus] ?? DRIFT_STATUS_CONFIG.no_report;

              return (
                <div>
                  {/* Badge statut global */}
                  <div style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "10px 14px", borderRadius: 10,
                    background: cfg.bg, border: `1px solid ${cfg.color}30`,
                    marginBottom: 12,
                  }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: cfg.color, flexShrink: 0,
                      boxShadow: globalStatus === "alert" ? `0 0 0 3px ${cfg.color}30` : "none",
                    }} />
                    <span style={{ fontSize: 13, fontWeight: 700, color: cfg.color }}>
                      {cfg.label}
                    </span>
                    {(drift.recommendation ?? Object.values(tasks)[0]?.recommendation) && (
                      <span style={{ fontSize: 11, color: "#748cab", marginLeft: 4 }}>
                        — {drift.recommendation ?? Object.values(tasks)[0]?.recommendation}
                      </span>
                    )}
                  </div>

                  {/* Détail par tâche */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {Object.entries(tasks).map(([taskName, report]: [string, any]) => {
                      const checks: any[] = report.checks ?? [];
                      const tCfg = DRIFT_STATUS_CONFIG[report.overall_status] ?? DRIFT_STATUS_CONFIG.no_report;
                      return (
                        <div key={taskName} style={{
                          padding: "10px 14px", borderRadius: 10,
                          background: "rgba(62,92,118,0.03)",
                          border: "1px solid rgba(62,92,118,0.1)",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: checks.length > 0 ? 8 : 0 }}>
                            <span style={{
                              fontSize: 11, fontWeight: 700, padding: "2px 8px",
                              borderRadius: 20, background: `${(TASK_COLORS[taskName] ?? "#3e5c76")}15`,
                              color: TASK_COLORS[taskName] ?? "#3e5c76",
                            }}>{taskName}</span>
                            <span style={{ fontSize: 11, color: tCfg.color, fontWeight: 600 }}>
                              {tCfg.label}
                            </span>
                            {report.generated_at && (
                              <span style={{ fontSize: 10, color: "#94a3b8", marginLeft: "auto" }}>
                                {new Date(report.generated_at).toLocaleString("fr-FR")}
                              </span>
                            )}
                          </div>

                          {/* Checks individuels */}
                          {checks.filter(c => c.status !== "skipped").map((chk: any) => {
                            const chkColors: Record<string, string> = {
                              ok: "#22c55e", alert: "#ef4444", warning: "#f59e0b", error: "#ef4444",
                            };
                            const chkColor = chkColors[chk.status] ?? "#94a3b8";
                            const checkLabels: Record<string, string> = {
                              performance_drift:  "Performance",
                              distribution_drift: "Distribution",
                              confidence_drift:   "Confiance",
                            };
                            return (
                              <div key={chk.check} style={{
                                display: "flex", alignItems: "flex-start", gap: 8,
                                padding: "5px 0", borderTop: "1px solid rgba(62,92,118,0.06)",
                              }}>
                                <span style={{ fontSize: 10, color: chkColor, marginTop: 2 }}>
                                  {chk.status === "ok" ? "✓" : "⚠"}
                                </span>
                                <div style={{ flex: 1 }}>
                                  <span style={{ fontSize: 11, fontWeight: 600, color: "#3e5c76" }}>
                                    {checkLabels[chk.check] ?? chk.check}
                                  </span>
                                  {chk.message && (
                                    <span style={{ fontSize: 11, color: "#748cab", marginLeft: 6 }}>
                                      {chk.message}
                                    </span>
                                  )}
                                  {/* Détails F1 / KL */}
                                  {chk.details && (
                                    <div style={{ display: "flex", gap: 10, marginTop: 3, flexWrap: "wrap" }}>
                                      {chk.details.current_f1 != null && (
                                        <span style={{ fontSize: 10, color: "#748cab" }}>
                                          F1={chk.details.current_f1}
                                          {chk.details.baseline_f1 != null && ` (baseline=${chk.details.baseline_f1})`}
                                        </span>
                                      )}
                                      {chk.details.kl_divergence != null && (
                                        <span style={{ fontSize: 10, color: "#748cab" }}>
                                          KL={chk.details.kl_divergence}
                                        </span>
                                      )}
                                      {chk.details.current_avg_confidence != null && (
                                        <span style={{ fontSize: 10, color: "#748cab" }}>
                                          Conf={(chk.details.current_avg_confidence * 100).toFixed(1)}%
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
