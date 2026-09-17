"use client";
import { useEffect, useState } from "react";
import API from "@/lib/api";

interface OrgSettings {
  id: string;
  name: string;
  plan: string;
  contributes_to_shared_training: boolean;
}

const PLAN_LABEL: Record<string, string> = { free: "Free", pro: "Pro", enterprise: "Enterprise" };

export default function SettingsPage() {
  const [org, setOrg] = useState<OrgSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try { setOrg((await API.get("/organisations/me")).data); }
    catch {}
    setLoading(false);
  }

  async function toggleConsent(next: boolean) {
    if (!org) return;
    setSaving(true); setMsg(null);
    const prev = org.contributes_to_shared_training;
    setOrg({ ...org, contributes_to_shared_training: next }); // optimistic
    try {
      const r = await API.patch("/organisations/me/training-consent", { contributes_to_shared_training: next });
      setOrg(r.data);
      setMsg(next
        ? "✅ Vos corrections aideront désormais à améliorer le modèle IA partagé."
        : "✅ Vos corrections ne seront plus utilisées pour le modèle partagé.");
    } catch (e: any) {
      setOrg({ ...org, contributes_to_shared_training: prev }); // revert
      setMsg(`❌ ${e.response?.data?.detail ?? e.message}`);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", flexDirection: "column", gap: 12 }}>
      <div style={{ width: 32, height: 32, border: "2px solid rgba(147,51,234,0.2)", borderTop: "2px solid #9333ea", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <span style={{ fontSize: 13, color: "#748cab" }}>Chargement…</span>
    </div>
  );

  if (!org) return (
    <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>Impossible de charger les paramètres de l'organisation.</div>
  );

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');`}</style>

      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase", color: "#9333ea", fontWeight: 600, marginBottom: 6 }}>
          {org.name} · {PLAN_LABEL[org.plan] ?? org.plan}
        </div>
        <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 30, color: "var(--text-primary, #0d1321)", margin: 0 }}>Paramètres</h1>
        <p style={{ color: "#748cab", fontSize: 13, marginTop: 6 }}>Gérez la confidentialité de vos données et votre contribution à l'IA d'InsightFlow.</p>
      </div>

      {/* Confidentialité & IA */}
      <div style={{
        background: "var(--bg-card, #fff)", borderRadius: 16,
        border: "1px solid rgba(62,92,118,0.1)", boxShadow: "0 2px 8px rgba(13,19,33,0.05)",
        padding: "1.75rem",
      }}>
        <div style={{ fontSize: 12, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700, marginBottom: "1rem" }}>
          🔒 Confidentialité & IA
        </div>

        <div style={{ display: "flex", alignItems: "flex-start", gap: 16, padding: "1rem", borderRadius: 12, background: "rgba(147,51,234,0.04)", border: "1px solid rgba(147,51,234,0.12)" }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary, #0d1321)", marginBottom: 6 }}>
              Aider à améliorer le modèle IA partagé
            </div>
            <div style={{ fontSize: 12.5, color: "#748cab", lineHeight: 1.6 }}>
              Quand activé, les corrections que votre équipe apporte aux prédictions IA (sentiment, émotion) sont
              utilisées pour ré-entraîner le modèle de langage partagé avec les autres organisations clientes.
              <br /><br />
              <strong style={{ color: "var(--text-primary, #0d1321)" }}>Vos messages bruts ne sont jamais partagés</strong> — seules
              les étiquettes corrigées (ex : "ceci est en fait de la frustration, pas de la neutralité") contribuent au
              ré-entraînement. Désactivé, vos corrections restent strictement internes à votre organisation et
              n'influencent jamais le modèle utilisé par d'autres clients.
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, flexShrink: 0 }}>
            <div
              onClick={() => !saving && toggleConsent(!org.contributes_to_shared_training)}
              style={{
                width: 46, height: 26, borderRadius: 13,
                background: org.contributes_to_shared_training ? "#22c55e" : "rgba(62,92,118,0.25)",
                position: "relative", cursor: saving ? "not-allowed" : "pointer",
                opacity: saving ? 0.6 : 1, transition: "background 0.2s",
              }}
            >
              <div style={{
                position: "absolute", top: 3, left: org.contributes_to_shared_training ? 23 : 3,
                width: 20, height: 20, borderRadius: "50%", background: "#fff",
                boxShadow: "0 1px 4px rgba(0,0,0,0.25)", transition: "left 0.2s",
              }} />
            </div>
            <span style={{ fontSize: 10, fontWeight: 700, color: org.contributes_to_shared_training ? "#16a34a" : "#748cab" }}>
              {org.contributes_to_shared_training ? "ACTIVÉ" : "DÉSACTIVÉ"}
            </span>
          </div>
        </div>

        {msg && (
          <div style={{
            marginTop: 14, fontSize: 13, padding: "10px 14px", borderRadius: 10,
            background: msg.startsWith("✅") ? "#f0fdf4" : "#fef2f2",
            color: msg.startsWith("✅") ? "#16a34a" : "#ef4444",
          }}>
            {msg}
          </div>
        )}

        <div style={{ marginTop: 14, fontSize: 11, color: "#94a3b8" }}>
          {org.plan === "enterprise"
            ? "Plan Enterprise : ce paramètre est désactivé par défaut à la création de votre compte."
            : "Sur votre plan, ce paramètre est activé par défaut à la création de votre compte — vous pouvez le désactiver à tout moment."}
        </div>
      </div>
    </div>
  );
}
