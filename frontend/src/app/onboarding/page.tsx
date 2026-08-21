"use client";
import { useEffect, useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import API from "@/lib/api";
import { getUser } from "@/lib/auth";

/* ── Types ─────────────────────────────────────────────────────────────────── */
interface SourceStatus {
  key: string; name: string; icon: string; color: string;
  category: string; available: boolean; coming_soon: boolean; connected: boolean;
  sync_pending?: boolean; items_count?: number;
}

type WizardStep = "welcome" | "choose" | "form" | "connected" | "generating";

/* ── Connector metadata for forms & OAuth ───────────────────────────────────── */
const OAUTH_URL_ENDPOINT: Record<string, string> = {
  gmail:   "/auth/google",
  teams:   "/auth/teams/auth-url",
  outlook: "/auth/outlook/auth-url",
};

interface FormField { key: string; label: string; placeholder: string; type?: string; hint?: string; required?: boolean; }

const CONNECTOR_FORMS: Record<string, FormField[]> = {
  jira: [
    { key: "base_url",     label: "URL Atlassian *",    placeholder: "https://entreprise.atlassian.net", required: true },
    { key: "email",        label: "Email Atlassian *",  placeholder: "ceo@entreprise.com", type: "email", required: true },
    { key: "api_token",    label: "API Token *",        placeholder: "ATATT3xFf...", type: "password", required: true,
      hint: "https://id.atlassian.com/manage-profile/security/api-tokens" },
    { key: "project_keys", label: "Clés projet",        placeholder: "SCRUM, DEV" },
  ],
  clickup: [
    { key: "api_token", label: "Personal API Token *", placeholder: "pk_xxxxxxx...", type: "password", required: true,
      hint: "Settings → Apps → API Token" },
    { key: "team_id",   label: "Team ID (optionnel)",  placeholder: "1234567" },
  ],
};

const FORM_ENDPOINT: Record<string, string> = {
  jira:    "/api/sources/jira/connect",
  clickup: "/api/sources/clickup/connect",
};

/* ── Global styles ─────────────────────────────────────────────────────────── */
const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&display=swap');
  *{box-sizing:border-box;margin:0;padding:0;}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
  @keyframes grow{from{width:0}to{width:100%}}
  .ob-fade{animation:fadeUp 0.4s ease forwards;}
  .src-card{transition:all 0.18s;cursor:pointer;}
  .src-card:hover:not([data-disabled]){transform:translateY(-3px);box-shadow:0 10px 32px rgba(13,19,33,0.1);}
  input:focus{outline:none;}
  .btn-primary:hover{opacity:0.92;}
  .btn-secondary:hover{background:rgba(62,92,118,0.07)!important;}
`;

/* ── Component ─────────────────────────────────────────────────────────────── */
function OnboardingInner() {
  const router        = useRouter();
  const params        = useSearchParams();

  const [step, setStep]               = useState<WizardStep>("welcome");
  const [sources, setSources]         = useState<SourceStatus[]>([]);
  const [connected, setConnected]     = useState<Set<string>>(new Set());
  const [selected, setSelected]       = useState<SourceStatus | null>(null);
  const [formValues, setFormValues]   = useState<Record<string, string>>({});
  const [formError, setFormError]     = useState("");
  const [formLoading, setFormLoading] = useState(false);
  const [loadingSources, setLoadingSources] = useState(true);
  const [sourcesError, setSourcesError]     = useState(false);
  const [syncMsg, setSyncMsg]               = useState("");
  const [orgName, setOrgName] = useState("CEO");

  useEffect(() => {
    const u = getUser();
    if (u?.full_name) setOrgName(u.full_name);
  }, []);

  /* Load sources + handle OAuth callback param */
  useEffect(() => {
    const connectedParam = params.get("connected");

    // If returning from OAuth, skip the welcome screen immediately
    if (connectedParam) setStep("choose");

    API.get("/api/sources/status")
      .then(r => {
        const list: SourceStatus[] = r.data;
        setSources(list);
        const alreadyConnected = new Set(list.filter(s => s.connected).map(s => s.key));
        if (connectedParam) alreadyConnected.add(connectedParam);
        setConnected(alreadyConnected);
        // If returning from OAuth, show the "connected" confirmation step
        if (connectedParam) {
          // Find in list, or build a minimal source object from REGISTRY fallback
          const src = list.find(s => s.key === connectedParam) ?? {
            key: connectedParam, name: connectedParam, icon: "✅",
            color: "#16a34a", category: "", available: true, coming_soon: false, connected: true,
          };
          setSelected(src);
          setStep("connected");
        }
      })
      .catch(() => setSourcesError(true))
      .finally(() => setLoadingSources(false));
  }, [params]);

  /* OAuth connectors — fetch URL via API (carries JWT), then redirect */
  const startOAuth = useCallback(async (src: SourceStatus) => {
    const endpoint = OAUTH_URL_ENDPOINT[src.key];
    if (!endpoint) return;
    try {
      const r = await API.get(endpoint);
      window.location.href = r.data.url;
    } catch {
      setFormError("Impossible de lancer l'authentification OAuth.");
    }
  }, []);

  /* API-key connectors — submit inline form */
  async function submitForm() {
    if (!selected) return;
    setFormError(""); setFormLoading(true);
    const fields = CONNECTOR_FORMS[selected.key] ?? [];
    for (const f of fields) {
      if (f.required && !formValues[f.key]?.trim()) {
        setFormError(`Le champ "${f.label}" est obligatoire.`);
        setFormLoading(false); return;
      }
    }
    try {
      await API.post(FORM_ENDPOINT[selected.key], formValues);
      setConnected(prev => new Set([...prev, selected.key]));
      setStep("connected");
    } catch (e: any) {
      setFormError(e.response?.data?.detail ?? e.message ?? "Erreur de connexion. Vérifiez vos credentials.");
    } finally {
      setFormLoading(false);
    }
  }

  function handleSourceClick(src: SourceStatus) {
    if (!src.available || src.coming_soon) return;
    if (connected.has(src.key)) return; // already done
    setSelected(src);
    setFormError(""); setFormValues({});
    if (OAUTH_URL_ENDPOINT[src.key]) {
      startOAuth(src);
    } else {
      setStep("form");
    }
  }

  function goToGenerating() {
    setStep("generating");
    setTimeout(() => router.replace("/dashboard"), 3000);
  }

  /* ── Render helpers ─────────────────────────────────────────────────────── */

  const sortedSources = [...sources].sort((a, b) => {
    // Available + not coming_soon first, then coming_soon, then disabled
    const rank = (s: SourceStatus) => s.available && !s.coming_soon ? 0 : s.coming_soon ? 1 : 2;
    return rank(a) - rank(b);
  });

  const shell = (children: React.ReactNode) => (
    <div style={{ minHeight: "100vh", background: "#f5f3ee", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "DM Sans, sans-serif", padding: "2rem" }}>
      <style>{GLOBAL_CSS}</style>
      {/* Progress bar accent */}
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 3, background: "linear-gradient(90deg, #1d2d44, #3e5c76, #748cab)" }} />
      {children}
    </div>
  );

  /* ── STEP: welcome ─────────────────────────────────────────────────────── */
  if (step === "welcome") return shell(
    <div className="ob-fade" style={{ textAlign: "center", maxWidth: 540 }}>
      <div style={{ width: 72, height: 72, borderRadius: "50%", background: "#1d2d44", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 2rem", fontSize: 30 }}>
        🧭
      </div>
      <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 8 }}>InsightFlow Executive</div>
      <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 32, color: "#0d1321", marginBottom: 14, lineHeight: 1.2 }}>
        Bienvenue, {orgName} !
      </h1>
      <p style={{ color: "#748cab", fontSize: 15, lineHeight: 1.7, marginBottom: "2.5rem" }}>
        Pour analyser vos communications, connectez vos sources de données.<br />
        Gmail, Jira, Teams, Outlook — chaque source enrichit votre tableau de bord IA.
      </p>
      <button
        className="btn-primary"
        onClick={() => setStep("choose")}
        style={{ background: "#1d2d44", color: "#f0ebd8", border: "none", borderRadius: 14, padding: "14px 40px", fontSize: 15, fontWeight: 700, cursor: "pointer", transition: "opacity 0.15s" }}
      >
        Commencer →
      </button>
      <div style={{ marginTop: "1rem" }}>
        <button onClick={goToGenerating} style={{ background: "none", border: "none", color: "#94a3b8", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>
          Passer et accéder au dashboard
        </button>
      </div>
    </div>
  );

  /* ── STEP: choose ──────────────────────────────────────────────────────── */
  if (step === "choose") {
    const connectedCount = sources.filter(s => connected.has(s.key)).length;
    return shell(
      <div className="ob-fade" style={{ width: "100%", maxWidth: 860 }}>
        {/* Header */}
        <div style={{ marginBottom: "2rem", textAlign: "center" }}>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 6 }}>Étape 1 / 2</div>
          <h2 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", marginBottom: 8 }}>Connectez vos sources</h2>
          <p style={{ color: "#748cab", fontSize: 13 }}>Cliquez sur une source pour l'authentifier avec vos propres credentials.</p>
          {connectedCount > 0 && (
            <div style={{ marginTop: 10, display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: 100, padding: "4px 14px" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#16a34a" }} />
              <span style={{ fontSize: 12, color: "#16a34a", fontWeight: 600 }}>{connectedCount} source{connectedCount > 1 ? "s" : ""} connectée{connectedCount > 1 ? "s" : ""}</span>
            </div>
          )}
        </div>

        {loadingSources ? (
          <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
            <div style={{ width: 28, height: 28, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 8px" }} />
            Chargement…
          </div>
        ) : sourcesError ? (
          <div style={{ textAlign: "center", padding: "3rem" }}>
            <div style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 12, padding: "1.25rem", color: "#dc2626", fontSize: 13, marginBottom: "1rem" }}>
              Impossible de charger les sources. Vérifiez que vous êtes connecté et que le serveur est démarré.
            </div>
            <button onClick={() => { setSourcesError(false); setLoadingSources(true); API.get("/api/sources/status").then(r => { setSources(r.data); }).catch(() => setSourcesError(true)).finally(() => setLoadingSources(false)); }}
              style={{ background: "#1d2d44", color: "#f0ebd8", border: "none", borderRadius: 10, padding: "10px 24px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              Réessayer
            </button>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
            {sortedSources.map(src => {
              const isConnected  = connected.has(src.key);
              const isDisabled   = !src.available || src.coming_soon;
              return (
                <div
                  key={src.key}
                  className="src-card"
                  data-disabled={isDisabled || isConnected ? "true" : undefined}
                  onClick={() => handleSourceClick(src)}
                  style={{
                    background: isConnected ? "rgba(34,197,94,0.04)" : "#fff",
                    border: `1.5px solid ${isConnected ? "rgba(34,197,94,0.35)" : "rgba(62,92,118,0.12)"}`,
                    borderRadius: 16, padding: "1.25rem 1rem",
                    opacity: isDisabled ? 0.4 : 1,
                    cursor: isConnected || isDisabled ? "default" : "pointer",
                    boxShadow: isConnected ? "0 4px 16px rgba(34,197,94,0.06)" : "0 2px 8px rgba(13,19,33,0.04)",
                  }}
                >
                  <div style={{ fontSize: 26, marginBottom: 8 }}>{src.icon}</div>
                  <div style={{ fontWeight: 700, fontSize: 13, color: "#0d1321", marginBottom: 4 }}>{src.name}</div>
                  <div style={{ fontSize: 11, color: "#748cab", lineHeight: 1.4, marginBottom: 10 }}>
                    {src.coming_soon ? "Bientôt disponible" : src.available ? "Disponible" : "Non disponible"}
                  </div>
                  {isConnected && src.sync_pending ? (
                    <span style={{ fontSize: 10, fontWeight: 600, color: "#d97706", background: "rgba(217,119,6,0.1)", borderRadius: 6, padding: "3px 8px" }}>⏳ Sync en cours</span>
                  ) : isConnected ? (
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", background: "rgba(34,197,94,0.1)", borderRadius: 6, padding: "3px 8px" }}>✓ Connecté</span>
                  ) : src.coming_soon ? (
                    <span style={{ fontSize: 10, color: "#94a3b8", background: "rgba(116,140,171,0.1)", borderRadius: 6, padding: "3px 8px", fontWeight: 600, letterSpacing: "0.05em" }}>BIENTÔT</span>
                  ) : src.available ? (
                    <span style={{ fontSize: 11, color: "#3e5c76", fontWeight: 600 }}>
                      {OAUTH_URL_ENDPOINT[src.key] ? "OAuth →" : "Configurer →"}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}

        <div style={{ textAlign: "center" }}>
          <button
            className="btn-primary"
            onClick={goToGenerating}
            disabled={connectedCount === 0}
            style={{
              background: connectedCount > 0 ? "#1d2d44" : "#94a3b8",
              color: "#f0ebd8", border: "none", borderRadius: 14,
              padding: "13px 36px", fontSize: 14, fontWeight: 700,
              cursor: connectedCount > 0 ? "pointer" : "not-allowed",
              transition: "opacity 0.15s",
            }}
          >
            Générer mon dashboard →
          </button>
          <div style={{ marginTop: 10 }}>
            <button onClick={goToGenerating} style={{ background: "none", border: "none", color: "#94a3b8", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>
              Continuer sans connecter
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ── STEP: form (API key connectors) ───────────────────────────────────── */
  if (step === "form" && selected) {
    const fields = CONNECTOR_FORMS[selected.key] ?? [];
    return shell(
      <div className="ob-fade" style={{ width: "100%", maxWidth: 560 }}>
        {/* Back + title */}
        <button onClick={() => setStep("choose")} style={{ background: "none", border: "none", color: "#748cab", fontSize: 13, cursor: "pointer", marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: 6 }}>
          ← Retour
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: "2rem" }}>
          <div style={{ width: 52, height: 52, borderRadius: 14, background: `${selected.color}14`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26 }}>{selected.icon}</div>
          <div>
            <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600 }}>Connexion</div>
            <h2 style={{ fontFamily: "DM Serif Display, serif", fontSize: 22, color: "#0d1321" }}>{selected.name}</h2>
          </div>
        </div>

        <div style={{ background: "#fff", borderRadius: 18, padding: "2rem", boxShadow: "0 4px 20px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", marginBottom: "1.5rem" }}>
            {fields.map(f => (
              <div key={f.key}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>
                  {f.label}
                  {f.hint && (
                    <a href={f.hint} target="_blank" rel="noreferrer" style={{ marginLeft: 8, fontSize: 11, color: "#3e5c76", fontWeight: 400 }}>Générer →</a>
                  )}
                </label>
                <input
                  type={f.type ?? "text"}
                  placeholder={f.placeholder}
                  value={formValues[f.key] ?? ""}
                  onChange={e => setFormValues(v => ({ ...v, [f.key]: e.target.value }))}
                  style={{ width: "100%", padding: "10px 14px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 10, fontSize: 13, fontFamily: "inherit", background: "#f8fafc", color: "#0d1321", transition: "border-color 0.2s" }}
                />
              </div>
            ))}
          </div>

          {formError && (
            <div style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 10, padding: "10px 14px", color: "#dc2626", fontSize: 13, marginBottom: "1rem" }}>
              {formError}
            </div>
          )}

          <button
            onClick={submitForm}
            disabled={formLoading}
            className="btn-primary"
            style={{ width: "100%", background: formLoading ? "#94a3b8" : "#1d2d44", color: "#f0ebd8", border: "none", borderRadius: 12, padding: "13px 0", fontSize: 14, fontWeight: 700, cursor: formLoading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "opacity 0.15s" }}
          >
            {formLoading
              ? <><div style={{ width: 14, height: 14, border: "2px solid rgba(255,255,255,0.3)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />Connexion en cours…</>
              : "Valider et connecter →"}
          </button>
        </div>

        <div style={{ marginTop: "0.75rem", textAlign: "center", fontSize: 11, color: "#94a3b8" }}>
          Vos credentials sont chiffrés et stockés sur votre organisation uniquement.
        </div>
      </div>
    );
  }

  /* ── STEP: connected ────────────────────────────────────────────────────── */
  if (step === "connected" && selected) {
    return shell(
      <div className="ob-fade" style={{ textAlign: "center", maxWidth: 480 }}>
        {/* Success icon */}
        <div style={{ width: 80, height: 80, borderRadius: "50%", background: "rgba(34,197,94,0.1)", border: "2px solid rgba(34,197,94,0.3)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1.5rem", fontSize: 36 }}>
          ✅
        </div>
        <h2 style={{ fontFamily: "DM Serif Display, serif", fontSize: 28, color: "#0d1321", marginBottom: 10 }}>
          {selected.name} connecté !
        </h2>
        <p style={{ color: "#748cab", fontSize: 14, lineHeight: 1.7, marginBottom: "2rem" }}>
          Vos données sont en cours d'importation et d'analyse par l'IA.<br />
          Voulez-vous connecter une autre source ?
        </p>

        {/* Connected sources summary */}
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginBottom: "2rem", flexWrap: "wrap" }}>
          {sources.filter(s => connected.has(s.key)).map(s => (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(34,197,94,0.07)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: 20, padding: "4px 12px" }}>
              <span style={{ fontSize: 14 }}>{s.icon}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#16a34a" }}>{s.name}</span>
            </div>
          ))}
        </div>

        {syncMsg && (
          <div style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: 10, padding: "10px 16px", color: "#16a34a", fontSize: 13, marginBottom: "0.5rem" }}>
            {syncMsg}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {selected?.key === "gmail" && (
            <button
              onClick={async () => {
                setSyncMsg("Sync en cours…");
                try {
                  await API.post("/auth/gmail/sync", {});
                  setSyncMsg("Sync Gmail lancé ! Les emails arrivent en arrière-plan. Redirection dans 3 secondes…");
                  setTimeout(() => router.replace("/dashboard"), 3000);
                } catch {
                  setSyncMsg("Erreur lors du sync. Vérifiez les logs backend.");
                }
              }}
              style={{ background: "rgba(34,197,94,0.08)", color: "#16a34a", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 12, padding: "11px 28px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              ↻ Synchroniser Gmail maintenant
            </button>
          )}
          <button
            className="btn-primary"
            onClick={() => { setSelected(null); setStep("choose"); }}
            style={{ background: "#fff", color: "#1d2d44", border: "1.5px solid rgba(29,45,68,0.2)", borderRadius: 12, padding: "13px 28px", fontSize: 14, fontWeight: 600, cursor: "pointer", transition: "all 0.15s" }}
          >
            + Connecter une autre source
          </button>
          <button
            className="btn-primary"
            onClick={goToGenerating}
            style={{ background: "#1d2d44", color: "#f0ebd8", border: "none", borderRadius: 12, padding: "13px 28px", fontSize: 14, fontWeight: 700, cursor: "pointer", transition: "opacity 0.15s" }}
          >
            🚀 Générer mon dashboard
          </button>
        </div>
      </div>
    );
  }

  /* ── STEP: generating ───────────────────────────────────────────────────── */
  if (step === "generating") return shell(
    <div className="ob-fade" style={{ textAlign: "center", maxWidth: 420 }}>
      <div style={{ fontSize: 60, marginBottom: "1.5rem", animation: "pulse 2s ease infinite" }}>🧠</div>
      <h2 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", marginBottom: 12 }}>
        Analyse en cours…
      </h2>
      <p style={{ color: "#748cab", fontSize: 14, marginBottom: "2rem" }}>
        L'IA analyse vos communications et prépare votre tableau de bord personnalisé.
      </p>
      {/* Animated progress bar */}
      <div style={{ height: 6, borderRadius: 6, background: "rgba(62,92,118,0.1)", overflow: "hidden", marginBottom: "1rem" }}>
        <div style={{ height: "100%", background: "linear-gradient(90deg, #1d2d44, #3e5c76)", borderRadius: 6, animation: "grow 3s linear forwards" }} />
      </div>
      <div style={{ fontSize: 12, color: "#94a3b8" }}>Redirection vers votre dashboard…</div>
    </div>
  );

  /* fallback while loading */
  return shell(
    <div style={{ textAlign: "center", color: "#748cab" }}>
      <div style={{ width: 32, height: 32, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
      Chargement…
    </div>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={
      <div style={{ minHeight: "100vh", background: "#f5f3ee", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "DM Sans, sans-serif" }}>
        <div style={{ width: 32, height: 32, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
      </div>
    }>
      <OnboardingInner />
    </Suspense>
  );
}
