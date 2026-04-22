"use client";

interface BusinessLabel {
  label: string;
  count: number;
  pct:   number;
  color: string;
  icon:  string;
  desc:  string;
}

interface Emotion {
  label: string;
  count: number;
  pct:   number;
  color: string;
  icon:  string;
}

interface Intelligence {
  business_labels: BusinessLabel[];
  emotions:        Emotion[];
  topics:          { label: string; count: number }[];
  risk_count:      number;
  risk_rate:       number;
  climate:         string;
  climate_label:   string;
  climate_color:   string;
  nlp_coverage:    number;
}

// Traduction CEO des labels business
const BUSINESS_FR: Record<string, { label: string; action: string; color: string; icon: string }> = {
  Urgent:         { label: "Urgences",        action: "nécessitent votre attention immédiate", color: "#ef4444", icon: "🚨" },
  Blocked:        { label: "Blocages",         action: "bloquent les équipes",                  color: "#f97316", icon: "🛑" },
  Risk:           { label: "Risques",          action: "à surveiller de près",                  color: "#f59e0b", icon: "⚠️" },
  Conflict:       { label: "Conflits",         action: "détectés dans les échanges",            color: "#8b5cf6", icon: "⚡" },
  Overload:       { label: "Surcharges",       action: "signaux de surcharge identifiés",       color: "#ec4899", icon: "📈" },
  Concern:        { label: "Préoccupations",   action: "méritent un suivi",                     color: "#eab308", icon: "🔶" },
  Progress:       { label: "Avancées",         action: "progressent bien",                      color: "#22c55e", icon: "✅" },
  "Neutral Update": { label: "Mises à jour",  action: "informatives, sans action requise",     color: "#94a3b8", icon: "ℹ️" },
};

// Traduction CEO des émotions (éviter le doublon avec "concern")
const EMOTION_FR: Record<string, { label: string; color: string; icon: string }> = {
  frustration:  { label: "Frustration",  color: "#ef4444", icon: "😤" },
  urgency:      { label: "Urgence",      color: "#f97316", icon: "⚡" },
  concern:      { label: "Inquiétude",   color: "#eab308", icon: "😟" },
  satisfaction: { label: "Satisfaction", color: "#22c55e", icon: "😊" },
  neutral:      { label: "Neutralité",   color: "#94a3b8", icon: "😐" },
};

const CLIMATE_CONFIG: Record<string, { label: string; color: string; icon: string; bg: string }> = {
  critical: { label: "Critique",  color: "#ef4444", icon: "🔴", bg: "#fef2f2" },
  tense:    { label: "Tendu",     color: "#f97316", icon: "🟠", bg: "#fff7ed" },
  moderate: { label: "Modéré",    color: "#f59e0b", icon: "🟡", bg: "#fefce8" },
  healthy:  { label: "Sain",      color: "#22c55e", icon: "🟢", bg: "#f0fdf4" },
};

function generateInsight(data: Intelligence): string {
  const urgent  = data.business_labels?.find(b => b.label === "Urgent");
  const blocked = data.business_labels?.find(b => b.label === "Blocked");
  const frustration = data.emotions?.find(e => e.label === "frustration");
  const satisfaction = data.emotions?.find(e => e.label === "satisfaction");

  const parts: string[] = [];
  if (urgent && urgent.count > 0)
    parts.push(`${urgent.count} sujet${urgent.count > 1 ? "s" : ""} urgent${urgent.count > 1 ? "s" : ""}`);
  if (blocked && blocked.count > 0)
    parts.push(`${blocked.count} blocage${blocked.count > 1 ? "s" : ""}`);
  if (frustration && frustration.pct > 15)
    parts.push(`frustration détectée (${frustration.pct}%)`);
  if (satisfaction && satisfaction.pct > 20)
    parts.push(`${satisfaction.pct}% de satisfaction`);

  if (parts.length === 0) return "Aucun signal critique détecté — situation globalement sous contrôle.";
  return `Détecté : ${parts.join(", ")}.`;
}

export default function SignalPanel({ data }: { data: Intelligence }) {
  const climate = CLIMATE_CONFIG[data.climate] ?? CLIMATE_CONFIG.moderate;

  // Séparer les signaux qui nécessitent action vs informatifs
  const actionable = (data.business_labels ?? []).filter(b =>
    ["Urgent", "Blocked", "Risk", "Conflict", "Overload", "Concern"].includes(b.label) && b.count > 0
  );
  const positive = (data.business_labels ?? []).filter(b =>
    ["Progress", "Neutral Update"].includes(b.label) && b.count > 0
  );

  const insight = generateInsight(data);

  return (
    <div style={{
      background: "#fff",
      borderRadius: 20,
      padding: "1.75rem 2rem",
      boxShadow: "0 2px 20px rgba(13,19,33,0.07)",
      border: "1px solid rgba(62,92,118,0.1)",
      marginBottom: "1.5rem",
    }}>

      {/* ── Header ─────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.25rem", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", fontWeight: 600, marginBottom: 4 }}>
            Analyse de communication
          </div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif", margin: 0 }}>
            Tableau de bord des signaux
          </h2>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "8px 16px", borderRadius: 20,
          background: climate.bg,
          border: `1px solid ${climate.color}40`,
        }}>
          <span style={{ fontSize: 16 }}>{climate.icon}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: climate.color }}>
            Climat {climate.label}
          </span>
        </div>
      </div>

      {/* ── Insight phrase ──────────────────────────────────────── */}
      <div style={{
        background: "rgba(62,92,118,0.05)",
        borderRadius: 12,
        padding: "10px 16px",
        fontSize: 13,
        color: "#3e5c76",
        fontWeight: 500,
        marginBottom: "1.75rem",
        borderLeft: "3px solid #3e5c76",
      }}>
        💡 {insight}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>

        {/* ── LEFT : Points d'attention ───────────────────────── */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", marginBottom: "1rem" }}>
            Points d'attention
          </div>

          {actionable.length === 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px", background: "#f0fdf4", borderRadius: 10 }}>
              <span style={{ fontSize: 16 }}>✅</span>
              <span style={{ fontSize: 13, color: "#16a34a", fontWeight: 500 }}>Aucun signal critique</span>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {actionable.map(b => {
                const meta = BUSINESS_FR[b.label] ?? { label: b.label, action: "", color: b.color, icon: b.icon };
                return (
                  <div key={b.label} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "10px 14px",
                    background: `${meta.color}0d`,
                    borderRadius: 10,
                    borderLeft: `3px solid ${meta.color}`,
                  }}>
                    <span style={{ fontSize: 16, flexShrink: 0 }}>{meta.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>
                        {b.count} {meta.label}
                      </div>
                      <div style={{ fontSize: 11, color: "#748cab" }}>{meta.action}</div>
                    </div>
                    <span style={{
                      fontSize: 11, fontWeight: 700, color: meta.color,
                      background: `${meta.color}18`, borderRadius: 6,
                      padding: "2px 8px", flexShrink: 0,
                    }}>
                      {b.pct}%
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Positifs en dessous */}
          {positive.length > 0 && (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              {positive.map(b => {
                const meta = BUSINESS_FR[b.label] ?? { label: b.label, action: "", color: b.color, icon: b.icon };
                return (
                  <div key={b.label} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "8px 12px",
                    background: "#f8fafc",
                    borderRadius: 8,
                  }}>
                    <span style={{ fontSize: 14 }}>{meta.icon}</span>
                    <span style={{ fontSize: 12, color: "#748cab", flex: 1 }}>
                      {b.count} {meta.label}
                    </span>
                    <span style={{ fontSize: 11, color: "#94a3b8" }}>{b.pct}%</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── RIGHT : Ton des communications ─────────────────── */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#748cab", marginBottom: "1rem" }}>
            Ton des communications
          </div>

          {(data.emotions ?? []).length === 0 ? (
            <p style={{ color: "#748cab", fontSize: 13 }}>Aucune donnée émotionnelle</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {data.emotions
                .filter(e => e.count > 0)
                .sort((a, b) => b.pct - a.pct)
                .map(e => {
                  const meta = EMOTION_FR[e.label] ?? { label: e.label, color: e.color, icon: e.icon };
                  const maxPct = Math.max(...data.emotions.map(x => x.pct), 1);
                  return (
                    <div key={e.label}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 15, width: 22, textAlign: "center" }}>{meta.icon}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", width: 90, flexShrink: 0 }}>
                          {meta.label}
                        </span>
                        <div style={{ flex: 1, height: 6, background: "rgba(0,0,0,0.06)", borderRadius: 4, overflow: "hidden" }}>
                          <div style={{
                            width: `${(e.pct / maxPct) * 100}%`,
                            height: "100%",
                            background: meta.color,
                            borderRadius: 4,
                            transition: "width 0.6s ease",
                          }} />
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 700, color: meta.color, width: 34, textAlign: "right", flexShrink: 0 }}>
                          {e.pct}%
                        </span>
                      </div>
                    </div>
                  );
                })}
            </div>
          )}

          {/* Topics */}
          {(data.topics ?? []).length > 0 && (
            <div style={{ marginTop: "1.5rem" }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#748cab", marginBottom: 10 }}>
                Sujets dominants
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {data.topics.map((t, i) => (
                  <span key={i} style={{
                    padding: "4px 12px", borderRadius: 20,
                    background: `rgba(62,92,118,${0.07 + (1 - i / data.topics.length) * 0.1})`,
                    color: "#3e5c76", fontSize: 12, fontWeight: 500,
                  }}>
                    {t.label}
                    <span style={{ color: "#748cab", fontSize: 11, marginLeft: 4 }}>{t.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
