"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import API, { ApiError } from "@/lib/api";
import { getUser, setUser, isLoggedIn, logout, type AuthUser } from "@/lib/auth";

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600;700&display=swap');
`;

const PLANS = [
  { key: "free",       label: "Free",       price: "0€",     color: "#748cab", bg: "rgba(116,140,171,0.08)", features: ["1 connecteur", "Fonctionnalités de base"] },
  { key: "pro",        label: "Pro",        price: "—",      color: "#2563eb", bg: "rgba(37,99,235,0.06)",   features: ["4 connecteurs", "Anomalies, OHS, recommandations", "Calendrier, brief hebdo, temps réel"] },
  { key: "enterprise", label: "Enterprise", price: "—",      color: "#9333ea", bg: "rgba(147,51,234,0.06)",  features: ["Connecteurs illimités", "Toutes les fonctionnalités Pro"] },
] as const;

export default function CreateOrganisationPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [plan, setPlan] = useState<string>("free");
  const [sector, setSector] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [country, setCountry] = useState("");
  const [website, setWebsite] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isLoggedIn()) { router.replace("/login"); return; }
    const u = getUser();
    if (!u?.email_verified) { router.replace("/verify-email"); return; }
    if (u.org_id) { router.replace("/onboarding"); return; }
    // Vérifie que la session est toujours valide côté serveur (ex: compte supprimé entretemps).
    API.get("/auth/me").catch((e) => { if (e instanceof ApiError && e.status === 401) logout(); });
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await API.post("/organisations", {
        name,
        plan,
        sector: sector || undefined,
        company_size: companySize || undefined,
        country: country || undefined,
        website: website || undefined,
      });
      setUser(r.data as AuthUser);
      router.replace("/onboarding");
    } catch (e) {
      setError(e instanceof ApiError ? (e.body?.detail ?? "Erreur") : "Impossible de contacter le serveur");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(135deg, #1d2d44 0%, #0d1321 100%)",
      fontFamily: "DM Sans, sans-serif", padding: "2rem",
    }}>
      <style>{GLOBAL_CSS}</style>
      <div style={{
        background: "#fff", borderRadius: 24, padding: "2.5rem 2.75rem",
        width: "100%", maxWidth: 560,
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
      }}>
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 4 }}>
            InsightFlow Executive
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 24, color: "#0d1321", marginTop: 6 }}>
            Créons votre espace InsightFlow
          </h1>
          <p style={{ fontSize: 13, color: "#748cab", marginTop: 8 }}>
            Le nom de votre entreprise, tel qu'il apparaîtra dans votre tableau de bord.
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={fieldLabelStyle}>Nom de l'entreprise</label>
            <input
              type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="Acme Corp" required minLength={2}
              style={fieldInputStyle}
            />
          </div>

          <div>
            <label style={fieldLabelStyle}>Plan</label>
            <div className="rf-grid-3-eq" style={{ gap: 10 }}>
              {PLANS.map(p => {
                const active = plan === p.key;
                return (
                  <div
                    key={p.key}
                    onClick={() => setPlan(p.key)}
                    style={{
                      cursor: "pointer", borderRadius: 12, padding: "12px 12px",
                      border: `1.5px solid ${active ? p.color : "#e2e8f0"}`,
                      background: active ? p.bg : "#fff",
                      transition: "all 0.15s",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: active ? p.color : "#0d1321" }}>{p.label}</span>
                      {active && (
                        <span style={{ width: 15, height: 15, borderRadius: "50%", background: p.color, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        </span>
                      )}
                    </div>
                    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 3 }}>
                      {p.features.map(f => (
                        <li key={f} style={{ fontSize: 10.5, color: "#748cab", lineHeight: 1.4 }}>{f}</li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ height: 1, background: "#f1f5f9", margin: "2px 0" }} />
          <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: -8 }}>
            Facultatif
          </div>

          <div className="rf-grid-2" style={{ gap: 14 }}>
            <div>
              <label style={fieldLabelStyle}>Secteur d'activité</label>
              <input
                type="text" value={sector} onChange={e => setSector(e.target.value)}
                placeholder="SaaS, Retail…" style={fieldInputStyle}
              />
            </div>
            <div>
              <label style={fieldLabelStyle}>Taille de l'entreprise</label>
              <select
                value={companySize} onChange={e => setCompanySize(e.target.value)}
                style={fieldInputStyle}
              >
                <option value="">—</option>
                <option value="1-10">1-10</option>
                <option value="11-50">11-50</option>
                <option value="51-200">51-200</option>
                <option value="201-500">201-500</option>
                <option value="500+">500+</option>
              </select>
            </div>
            <div>
              <label style={fieldLabelStyle}>Pays</label>
              <input
                type="text" value={country} onChange={e => setCountry(e.target.value)}
                placeholder="France" style={fieldInputStyle}
              />
            </div>
            <div>
              <label style={fieldLabelStyle}>Site web</label>
              <input
                type="text" value={website} onChange={e => setWebsite(e.target.value)}
                placeholder="acme.com" style={fieldInputStyle}
              />
            </div>
          </div>

          {error && (
            <div style={{
              background: "#fef2f2", border: "1px solid #fca5a5",
              borderRadius: 10, padding: "10px 14px",
              fontSize: 13, color: "#991b1b",
            }}>
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={{
            background: loading ? "#94a3b8" : "#1d2d44",
            color: "#f0ebd8", border: "none", borderRadius: 12,
            padding: "12px 0", fontSize: 14, fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer", marginTop: 4,
          }}>
            {loading ? "Création..." : "Créer mon organisation"}
          </button>
        </form>
      </div>
    </div>
  );
}

const fieldLabelStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6,
};

const fieldInputStyle: React.CSSProperties = {
  width: "100%", padding: "10px 14px", borderRadius: 10,
  border: "1px solid #e2e8f0", fontSize: 13, outline: "none",
  background: "#f8fafc", color: "#0d1321", boxSizing: "border-box",
};
