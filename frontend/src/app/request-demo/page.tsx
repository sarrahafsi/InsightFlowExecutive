"use client";
import { useState } from "react";
import Link from "next/link";
import API, { ApiError } from "@/lib/api";

const SOURCES = [
  { key: "gmail",   label: "Gmail" },
  { key: "outlook", label: "Outlook" },
  { key: "slack",   label: "Slack" },
  { key: "teams",   label: "Microsoft Teams" },
  { key: "jira",    label: "Jira" },
  { key: "clickup", label: "ClickUp" },
];

const COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-500", "500+"];

export default function RequestDemoPage() {
  const [firstName, setFirstName]     = useState("");
  const [lastName, setLastName]       = useState("");
  const [email, setEmail]             = useState("");
  const [company, setCompany]         = useState("");
  const [jobTitle, setJobTitle]       = useState("");
  const [companySize, setCompanySize] = useState("");
  const [sources, setSources]         = useState<Set<string>>(new Set());
  const [message, setMessage]         = useState("");
  const [error, setError]             = useState("");
  const [loading, setLoading]         = useState(false);
  const [submitted, setSubmitted]     = useState(false);

  function toggleSource(key: string) {
    setSources(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await API.post("/demo-requests", {
        first_name: firstName,
        last_name: lastName,
        email,
        company,
        job_title: jobTitle || undefined,
        company_size: companySize || undefined,
        sources: Array.from(sources),
        message: message || undefined,
      });
      setSubmitted(true);
    } catch (e) {
      setError(e instanceof ApiError ? "Une erreur est survenue, réessayez." : "Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ background: "#FAFBFF", minHeight: "100vh", fontFamily: "'Inter', sans-serif", color: "#0F172A" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        .df-input{width:100%;padding:11px 14px;border-radius:10px;border:1.5px solid rgba(0,0,0,0.09);font-size:14px;outline:none;background:#fff;color:#0F172A;box-sizing:border-box;font-family:'Inter',sans-serif;transition:border-color 0.15s;}
        .df-input:focus{border-color:#6366F1;}
        .df-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(135deg,#6366F1 0%,#8B5CF6 50%,#EC4899 100%);color:#fff;font-size:15px;font-weight:700;padding:14px 0;border-radius:14px;border:none;cursor:pointer;box-shadow:0 8px 32px rgba(99,102,241,0.3);transition:opacity 0.15s;width:100%;}
        .df-btn:disabled{opacity:0.6;cursor:not-allowed;}
        .df-chip{display:flex;align-items:center;gap:8px;padding:9px 14px;border-radius:10px;border:1.5px solid rgba(0,0,0,0.09);cursor:pointer;font-size:13px;font-weight:500;transition:all 0.15s;user-select:none;}
      `}</style>

      <nav style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1.5rem 2.5rem" }}>
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, background: "linear-gradient(135deg,#6366F1,#8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="17" height="17" viewBox="0 0 18 18" fill="none">
              <path d="M3 14L7 8L10 11L13 5L16 8" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 8, letterSpacing: "0.15em", textTransform: "uppercase", color: "#94A3B8", lineHeight: 1 }}>InsightFlow</div>
            <div style={{ fontSize: 14, fontWeight: 800, color: "#0F172A", lineHeight: 1.2 }}>Executive</div>
          </div>
        </Link>
        <Link href="/login" style={{ fontSize: 13, color: "#64748B", textDecoration: "none", fontWeight: 500 }}>
          Se connecter
        </Link>
      </nav>

      <div style={{ maxWidth: 640, margin: "0 auto", padding: "2rem 1.5rem 5rem" }}>
        {submitted ? (
          <div style={{ textAlign: "center", padding: "5rem 1rem" }}>
            <div style={{ width: 64, height: 64, borderRadius: "50%", background: "linear-gradient(135deg,#6366F1,#8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1.75rem", boxShadow: "0 8px 32px rgba(99,102,241,0.3)" }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 800, marginBottom: 12 }}>
              Merci pour votre intérêt pour InsightFlow Executive.
            </h1>
            <p style={{ fontSize: 15, color: "#64748B", lineHeight: 1.7 }}>
              Votre demande a bien été enregistrée. Notre équipe vous recontactera très prochainement.
            </p>
            <Link href="/" className="df-btn" style={{ display: "inline-flex", width: "auto", padding: "12px 28px", marginTop: 24, textDecoration: "none" }}>
              Retour à l'accueil
            </Link>
          </div>
        ) : (
          <>
            <div style={{ textAlign: "center", padding: "2.5rem 0 2.5rem" }}>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 100, padding: "6px 16px", marginBottom: "1.5rem" }}>
                <span style={{ fontSize: 12, color: "#6366F1", fontWeight: 600 }}>✦ Demande de démo</span>
              </div>
              <h1 style={{ fontSize: "clamp(1.8rem,4vw,2.4rem)", fontWeight: 800, lineHeight: 1.2, marginBottom: 14 }}>
                Découvrez comment InsightFlow peut transformer vos données en intelligence décisionnelle.
              </h1>
              <p style={{ fontSize: 14, color: "#64748B", lineHeight: 1.7 }}>
                Remplissez ce formulaire — un membre de notre équipe vous contactera pour organiser une démonstration.
              </p>
            </div>

            <form onSubmit={handleSubmit} style={{ background: "#fff", borderRadius: 20, padding: "2.25rem", border: "1px solid rgba(0,0,0,0.06)", boxShadow: "0 4px 24px rgba(15,23,42,0.05)", display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="rf-grid-2" style={{ gap: 14 }}>
                <div>
                  <label style={labelStyle}>Prénom *</label>
                  <input className="df-input" value={firstName} onChange={e => setFirstName(e.target.value)} required placeholder="Jean" />
                </div>
                <div>
                  <label style={labelStyle}>Nom *</label>
                  <input className="df-input" value={lastName} onChange={e => setLastName(e.target.value)} required placeholder="Dupont" />
                </div>
              </div>

              <div>
                <label style={labelStyle}>E-mail professionnel *</label>
                <input className="df-input" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="jean.dupont@entreprise.com" />
              </div>

              <div className="rf-grid-2" style={{ gap: 14 }}>
                <div>
                  <label style={labelStyle}>Entreprise *</label>
                  <input className="df-input" value={company} onChange={e => setCompany(e.target.value)} required placeholder="Acme Corp" />
                </div>
                <div>
                  <label style={labelStyle}>Fonction</label>
                  <input className="df-input" value={jobTitle} onChange={e => setJobTitle(e.target.value)} placeholder="CEO, COO…" />
                </div>
              </div>

              <div>
                <label style={labelStyle}>Taille de l'entreprise</label>
                <select className="df-input" value={companySize} onChange={e => setCompanySize(e.target.value)}>
                  <option value="">—</option>
                  {COMPANY_SIZES.map(s => <option key={s} value={s}>{s} employés</option>)}
                </select>
              </div>

              <div>
                <label style={labelStyle}>Sources actuellement utilisées</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                  {SOURCES.map(s => {
                    const active = sources.has(s.key);
                    return (
                      <div
                        key={s.key}
                        className="df-chip"
                        onClick={() => toggleSource(s.key)}
                        style={{
                          background: active ? "rgba(99,102,241,0.08)" : "#fff",
                          borderColor: active ? "#6366F1" : "rgba(0,0,0,0.09)",
                          color: active ? "#6366F1" : "#0F172A",
                        }}
                      >
                        <span style={{
                          width: 14, height: 14, borderRadius: 4, border: `1.5px solid ${active ? "#6366F1" : "rgba(0,0,0,0.2)"}`,
                          background: active ? "#6366F1" : "transparent", flexShrink: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                          {active && <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>}
                        </span>
                        {s.label}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div>
                <label style={labelStyle}>Message / besoin</label>
                <textarea
                  className="df-input" value={message} onChange={e => setMessage(e.target.value)}
                  placeholder="Parlez-nous de votre besoin…" rows={4}
                  style={{ resize: "vertical", fontFamily: "'Inter', sans-serif" }}
                />
              </div>

              {error && (
                <div style={{ background: "#FEF2F2", border: "1px solid #FCA5A5", borderRadius: 10, padding: "10px 14px", fontSize: 13, color: "#991B1B" }}>
                  {error}
                </div>
              )}

              <button type="submit" className="df-btn" disabled={loading} style={{ marginTop: 6 }}>
                {loading ? "Envoi..." : "Demander une démo"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: 12.5, fontWeight: 600, color: "#334155", display: "block", marginBottom: 6,
};
