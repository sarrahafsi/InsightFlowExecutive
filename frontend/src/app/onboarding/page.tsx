"use client";
import { useEffect, useState } from "react";
import API, { Source, SourcesResponse } from "@/lib/api";

export default function Onboarding() {
  const [sourcesByCategory, setSourcesByCategory] = useState<SourcesResponse>({});
  const [loading, setLoading] = useState(true);

  // Connection states
  const [gmailConnected, setGmailConnected]     = useState(false);
  const [jiraConnected, setJiraConnected]       = useState(false);
  const [teamsConnected, setTeamsConnected]     = useState(false);
  const [outlookConnected, setOutlookConnected] = useState(false);

  // Jira inline form
  const [jiraFormOpen, setJiraFormOpen]     = useState(false);
  const [jiraConnecting, setJiraConnecting] = useState(false);
  const [jiraError, setJiraError]           = useState("");
  const [jiraUrl, setJiraUrl]               = useState("");
  const [jiraEmail, setJiraEmail]           = useState("");
  const [jiraToken, setJiraToken]           = useState("");
  const [jiraProjects, setJiraProjects]     = useState("SCRUM");

  useEffect(() => {
    API.get("/api/sources/categories")
      .then(r => setSourcesByCategory(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));

    API.get("/api/sources/jira/status")
      .then(r => {
        if (r.data.connected) {
          setJiraConnected(true);
          if (r.data.base_url) setJiraUrl(r.data.base_url);
          if (r.data.email)    setJiraEmail(r.data.email);
        }
      })
      .catch(() => {});

    API.get("/auth/gmail/status")
      .then(r => { if (r.data.connected) setGmailConnected(true); })
      .catch(() => {});

    API.get("/api/sources/teams/status")
      .then(r => { if (r.data.connected) setTeamsConnected(true); })
      .catch(() => {});

    API.get("/api/sources/outlook/status")
      .then(r => { if (r.data.connected) setOutlookConnected(true); })
      .catch(() => {});
  }, []);

  async function connectJira() {
    if (!jiraUrl || !jiraEmail || !jiraToken) {
      setJiraError("Veuillez remplir les 3 champs obligatoires.");
      return;
    }
    setJiraConnecting(true);
    setJiraError("");
    try {
      const res = await fetch("http://localhost:8000/api/sources/jira/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url:     jiraUrl,
          email:        jiraEmail,
          api_token:    jiraToken,
          project_keys: jiraProjects || "SCRUM",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setJiraError(data.detail || "Erreur de connexion. Vérifiez vos credentials.");
      } else {
        setJiraConnected(true);
        setJiraFormOpen(false);
        setJiraError("");
      }
    } catch {
      setJiraError("Impossible de joindre le serveur.");
    } finally {
      setJiraConnecting(false);
    }
  }

  function handleSourceClick(source: Source) {
    if (!source.available || source.coming_soon) return;

    if (source.key === "jira") {
      setJiraFormOpen(v => !v);
      setJiraError("");
      return;
    }
    if (source.key === "gmail" && !gmailConnected) {
      API.get("/auth/google").then(r => { window.location.href = r.data.url; }).catch(() => {});
      return;
    }
    if (source.key === "teams" && !teamsConnected) {
      window.location.href = "http://localhost:8000/auth/teams/connect";
      return;
    }
    if (source.key === "outlook" && !outlookConnected) {
      window.location.href = "http://localhost:8000/auth/outlook/connect";
      return;
    }
  }

  // Whether a source is connected
  function isConnected(key: string): boolean {
    if (key === "slack")  return true;           // always connected via bot token
    if (key === "gmail")  return gmailConnected;
    if (key === "jira")   return jiraConnected;
    if (key === "teams")   return teamsConnected;
    if (key === "outlook") return outlookConnected;
    return false;
  }

  const connectedCount = ["slack", "gmail", "jira", "teams", "outlook"].filter(isConnected).length;

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "#f0ebd8", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 14 }}>
      <div style={{ width: 36, height: 36, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <p style={{ color: "#748cab", fontFamily: "DM Sans, sans-serif", fontSize: 13 }}>Chargement des sources...</p>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", background: "#f0ebd8", color: "#0d1321", fontFamily: "DM Sans, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        .ob-anim{animation:fadeUp 0.5s ease forwards;}
        .ob-anim-1{animation:fadeUp 0.5s ease 0.1s forwards;opacity:0;}
        .ob-anim-2{animation:fadeUp 0.5s ease 0.25s forwards;opacity:0;}
        .source-card{transition:all 0.2s ease;position:relative;cursor:pointer;}
        .source-card:hover:not([data-disabled="true"]){transform:translateY(-2px);box-shadow:0 8px 28px rgba(13,19,33,0.1);}
        .source-card[data-disabled="true"]{cursor:not-allowed;}
        .dash-btn{transition:all 0.25s ease;}
        .dash-btn:hover{transform:translateY(-1px);box-shadow:0 8px 28px rgba(29,45,68,0.3);}
        input:focus{outline:none;border-color:#3e5c76 !important;box-shadow:0 0 0 3px rgba(62,92,118,0.1);}
      `}</style>

      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, background: "radial-gradient(ellipse 80% 60% at 10% 0%, rgba(116,140,171,0.12) 0%, transparent 60%), radial-gradient(ellipse 60% 50% at 90% 100%, rgba(62,92,118,0.1) 0%, transparent 60%)" }} />
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 3, zIndex: 10, background: "linear-gradient(90deg, #1d2d44, #3e5c76, #748cab, #3e5c76, #1d2d44)" }} />

      <div style={{ maxWidth: 960, margin: "0 auto", padding: "4rem 2rem 4rem", position: "relative", zIndex: 1 }}>

        {/* Header */}
        <div className="ob-anim" style={{ textAlign: "center", marginBottom: "3.5rem" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 16px", borderRadius: 100, background: "rgba(29,45,68,0.08)", border: "1px solid rgba(62,92,118,0.2)", marginBottom: "1.5rem" }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#3e5c76" }} />
            <span style={{ fontSize: "0.7rem", letterSpacing: "0.2em", textTransform: "uppercase", color: "#3e5c76", fontWeight: 600 }}>InsightFlow Executive</span>
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: "3rem", color: "#0d1321", letterSpacing: "-0.02em", lineHeight: 1.1, marginBottom: "1rem" }}>
            Connectez vos sources
          </h1>
          <p style={{ color: "#748cab", fontSize: "1rem", maxWidth: 480, margin: "0 auto" }}>
            Sélectionnez les plateformes à analyser pour votre dashboard CEO
          </p>
          {connectedCount > 0 && (
            <div style={{ marginTop: "1rem", display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: 100, padding: "5px 14px" }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#16a34a" }} />
              <span style={{ fontSize: "0.72rem", color: "#16a34a", fontWeight: 600 }}>{connectedCount} source{connectedCount > 1 ? "s" : ""} connectée{connectedCount > 1 ? "s" : ""}</span>
            </div>
          )}
        </div>

        {/* Source grid by category */}
        <div className="ob-anim-1">
          {Object.entries(sourcesByCategory).map(([category, sources]) => (
            <div key={category} style={{ marginBottom: "2.5rem" }}>
              {/* Category label */}
              <div style={{ fontSize: "0.65rem", letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: "1rem", paddingLeft: "0.25rem", display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 20, height: 1, background: "rgba(116,140,171,0.4)" }} />
                {category}
                <div style={{ flex: 1, height: 1, background: "rgba(116,140,171,0.15)" }} />
              </div>

              {/* Cards grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: "1rem" }}>
                {(sources as Source[]).map((source: Source) => {
                  const connected  = isConnected(source.key);
                  const isJira     = source.key === "jira";
                  const isDisabled = !source.available || (source.coming_soon ?? false);
                  const isJiraOpen = isJira && jiraFormOpen;

                  return (
                    <div
                      key={source.key}
                      className="source-card"
                      data-disabled={isDisabled ? "true" : undefined}
                      onClick={() => handleSourceClick(source)}
                      style={{
                        background: connected ? "rgba(34,197,94,0.04)" : isJiraOpen ? "rgba(0,82,204,0.04)" : "#ffffff",
                        border: `1.5px solid ${connected ? "rgba(34,197,94,0.35)" : isJiraOpen ? "rgba(0,82,204,0.35)" : "rgba(62,92,118,0.15)"}`,
                        borderRadius: 16,
                        padding: "1.4rem",
                        opacity: isDisabled ? 0.42 : 1,
                        boxShadow: connected
                          ? "0 4px 16px rgba(34,197,94,0.08)"
                          : isJiraOpen ? "0 4px 16px rgba(0,82,204,0.08)"
                          : "0 2px 8px rgba(13,19,33,0.04)",
                      }}
                    >
                      <div style={{ fontSize: "1.9rem", marginBottom: "0.6rem" }}>{source.icon}</div>
                      <div style={{ fontWeight: 600, fontSize: "0.9rem", color: "#0d1321", marginBottom: "0.3rem" }}>{source.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "#748cab", lineHeight: 1.5 }}>{source.description}</div>

                      {/* State badge */}
                      {connected ? (
                        <div style={{ marginTop: "0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: "0.62rem", fontWeight: 700, color: "#16a34a", background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: 5, padding: "2px 8px", letterSpacing: "0.05em" }}>✓ CONNECTÉ</span>
                          {(isJira || source.key === "gmail") && (
                            <span style={{ fontSize: "0.68rem", color: "#748cab", textDecoration: "underline", cursor: "pointer" }}
                              onClick={e => { e.stopPropagation(); if (isJira) { setJiraFormOpen(v => !v); setJiraError(""); } }}>
                              Modifier
                            </span>
                          )}
                        </div>
                      ) : source.coming_soon ? (
                        <div style={{ position: "absolute", top: 12, right: 12, fontSize: "0.58rem", background: "rgba(116,140,171,0.12)", color: "#748cab", border: "1px solid rgba(116,140,171,0.25)", borderRadius: 4, padding: "2px 6px", letterSpacing: "0.06em", fontWeight: 600 }}>
                          BIENTÔT
                        </div>
                      ) : isJiraOpen ? (
                        <div style={{ marginTop: "0.75rem" }}>
                          <span style={{ fontSize: "0.68rem", color: "#0052CC", fontWeight: 600 }}>▾ Formulaire ouvert</span>
                        </div>
                      ) : source.available ? (
                        <div style={{ marginTop: "0.75rem" }}>
                          <span style={{ fontSize: "0.68rem", color: "#3e5c76", fontWeight: 600 }}>
                            {source.key === "gmail" ? "Connecter via OAuth →" : "Configurer →"}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              {/* Jira inline form — appears below "Projets" category */}
              {category === "Projets" && jiraFormOpen && (
                <div style={{ marginTop: "1.25rem", background: "#fff", border: "1.5px solid rgba(0,82,204,0.2)", borderRadius: 16, padding: "1.75rem 2rem", animation: "fadeIn 0.22s ease", boxShadow: "0 4px 20px rgba(0,82,204,0.06)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "1.25rem" }}>
                    <div style={{ fontSize: 22 }}>🎫</div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 15, color: "#0d1321" }}>Connexion Jira</div>
                      <div style={{ fontSize: 12, color: "#748cab" }}>Entrez vos identifiants Atlassian</div>
                    </div>
                    <button onClick={() => { setJiraFormOpen(false); setJiraError(""); }}
                      style={{ marginLeft: "auto", background: "none", border: "1px solid rgba(62,92,118,0.2)", borderRadius: 8, padding: "5px 12px", fontSize: 12, color: "#748cab", cursor: "pointer", fontFamily: "inherit" }}>
                      ✕ Fermer
                    </button>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6, color: "#0d1321" }}>URL Atlassian *</label>
                      <input value={jiraUrl} onChange={e => setJiraUrl(e.target.value)}
                        placeholder="https://monentreprise.atlassian.net"
                        style={{ width: "100%", padding: "10px 13px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 9, fontSize: 13, fontFamily: "inherit", background: "#fafaf9", transition: "border-color 0.2s, box-shadow 0.2s" }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6, color: "#0d1321" }}>Email Atlassian *</label>
                      <input value={jiraEmail} onChange={e => setJiraEmail(e.target.value)}
                        placeholder="ceo@entreprise.com" type="email"
                        style={{ width: "100%", padding: "10px 13px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 9, fontSize: 13, fontFamily: "inherit", background: "#fafaf9", transition: "border-color 0.2s, box-shadow 0.2s" }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6, color: "#0d1321" }}>
                        API Token *{" "}
                        <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noreferrer"
                          style={{ color: "#0052CC", fontWeight: 400, fontSize: 11 }}>Générer →</a>
                      </label>
                      <input value={jiraToken} onChange={e => setJiraToken(e.target.value)}
                        placeholder="ATATT3xFf..." type="password"
                        style={{ width: "100%", padding: "10px 13px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 9, fontSize: 13, fontFamily: "inherit", background: "#fafaf9", transition: "border-color 0.2s, box-shadow 0.2s" }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6, color: "#0d1321" }}>
                        Clé(s) projet
                        <span style={{ fontSize: 11, fontWeight: 400, color: "#748cab", marginLeft: 6 }}>ex : SCRUM, DEV</span>
                      </label>
                      <input value={jiraProjects} onChange={e => setJiraProjects(e.target.value)}
                        placeholder="SCRUM"
                        style={{ width: "100%", padding: "10px 13px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 9, fontSize: 13, fontFamily: "inherit", background: "#fafaf9", transition: "border-color 0.2s, box-shadow 0.2s" }} />
                    </div>
                  </div>

                  {jiraError && (
                    <div style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 9, padding: "10px 14px", color: "#dc2626", fontSize: 13, marginBottom: "1rem" }}>
                      {jiraError}
                    </div>
                  )}

                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <button onClick={connectJira} disabled={jiraConnecting}
                      style={{ background: jiraConnecting ? "#93b4e0" : "#0052CC", color: "#fff", border: "none", borderRadius: 10, padding: "11px 28px", fontSize: 14, fontWeight: 600, cursor: jiraConnecting ? "not-allowed" : "pointer", fontFamily: "inherit", display: "flex", alignItems: "center", gap: 8, transition: "background 0.2s" }}>
                      {jiraConnecting
                        ? <><div style={{ width: 13, height: 13, border: "2px solid rgba(255,255,255,0.35)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} /> Connexion...</>
                        : "Valider →"}
                    </button>
                    <span style={{ fontSize: 12, color: "#748cab" }}>Les credentials sont stockés de façon sécurisée</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="ob-anim-2" style={{ textAlign: "center", marginTop: "1rem" }}>
          <button
            className="dash-btn"
            onClick={() => window.location.href = "/dashboard"}
            style={{ padding: "15px 52px", borderRadius: 14, border: "none", background: "linear-gradient(135deg, #1d2d44, #3e5c76)", color: "#f0ebd8", fontSize: "0.95rem", fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif", letterSpacing: "0.01em" }}>
            Accéder au dashboard →
          </button>
          <p style={{ marginTop: 10, fontSize: "0.72rem", color: "#748cab" }}>
            {[
              { key: "slack",   label: "Slack"   },
              { key: "gmail",   label: "Gmail"   },
              { key: "outlook", label: "Outlook" },
              { key: "teams",   label: "Teams"   },
              { key: "jira",    label: "Jira"    },
            ].map(({ key, label }) =>
              isConnected(key)
                ? <span key={key} style={{ color: "#16a34a", fontWeight: 600 }}>{label} ✓</span>
                : <span key={key} style={{ color: "#748cab" }}>{label}</span>
            ).reduce((acc: React.ReactNode[], el, i) => i === 0 ? [el] : [...acc, <span key={`sep-${i}`} style={{ margin: "0 6px", opacity: 0.4 }}>·</span>, el], [])}
          </p>
        </div>

      </div>
    </div>
  );
}
