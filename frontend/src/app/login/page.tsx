"use client";
import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setToken, setUser, isLoggedIn, type AuthUser } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Mode = "login" | "register";

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode]         = useState<Mode>("login");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName]   = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (isLoggedIn()) router.replace("/dashboard");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
    const body = mode === "login"
      ? { email, password }
      : { email, password, full_name: fullName, org_name: orgName };

    try {
      const res = await fetch(`${BASE_URL}${endpoint}`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Erreur de connexion");
        return;
      }
      setToken(data.access_token);
      setUser(data.user as AuthUser);
      const user: AuthUser = data.user;
      // New CEO registration always goes to onboarding wizard
      const defaultNext = mode === "register"
        ? "/onboarding"
        : user.role === "superadmin" ? "/dashboard/admin" : "/dashboard";
      const next = params.get("next") ?? defaultNext;
      router.replace(next);
    } catch {
      setError("Impossible de contacter le serveur");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(135deg, #1d2d44 0%, #0d1321 100%)",
      fontFamily: "DM Sans, sans-serif",
    }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');`}</style>

      <div style={{
        background: "#fff", borderRadius: 24, padding: "2.5rem 2.75rem",
        width: "100%", maxWidth: 420,
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
      }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "#748cab", marginBottom: 4 }}>
            InsightFlow
          </div>
          <div style={{ fontFamily: "DM Serif Display, serif", fontSize: 24, color: "#0d1321" }}>
            Executive
          </div>
          <div style={{ fontSize: 13, color: "#748cab", marginTop: 6 }}>
            {mode === "login" ? "Connexion à votre espace" : "Créer votre organisation"}
          </div>
        </div>

        {/* Tab switcher */}
        <div style={{ display: "flex", background: "#f5f3ee", borderRadius: 12, padding: 4, marginBottom: "1.5rem" }}>
          {(["login", "register"] as Mode[]).map(m => (
            <button key={m} onClick={() => { setMode(m); setError(""); }}
              style={{
                flex: 1, padding: "8px 0", borderRadius: 10, border: "none", cursor: "pointer",
                background: mode === m ? "#fff" : "transparent",
                color: mode === m ? "#0d1321" : "#748cab",
                fontWeight: mode === m ? 700 : 400, fontSize: 13,
                boxShadow: mode === m ? "0 1px 4px rgba(0,0,0,0.08)" : "none",
                transition: "all 0.15s",
              }}>
              {m === "login" ? "Se connecter" : "Créer un compte"}
            </button>
          ))}
        </div>

        {mode === "register" && (
          <div style={{
            background: "#eff6ff", border: "1px solid #93c5fd",
            borderRadius: 10, padding: "10px 14px", marginBottom: "1rem",
            fontSize: 12, color: "#1e40af",
          }}>
            Créez votre organisation et votre compte <strong>CEO</strong>. Vous pourrez ensuite inviter vos Project Managers.
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {mode === "register" && (
            <>
              <div>
                <label style={labelStyle}>Nom de l'organisation</label>
                <input
                  type="text" value={orgName} onChange={e => setOrgName(e.target.value)}
                  placeholder="Acme Corp" required minLength={2}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Votre nom complet</label>
                <input
                  type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                  placeholder="Jean Dupont" required
                  style={inputStyle}
                />
              </div>
            </>
          )}

          <div>
            <label style={labelStyle}>Email</label>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="ceo@company.com" required
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Mot de passe</label>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••" required minLength={6}
              style={inputStyle}
            />
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
            cursor: loading ? "not-allowed" : "pointer",
            transition: "background 0.15s", marginTop: 4,
          }}>
            {loading
              ? (mode === "login" ? "Connexion..." : "Création...")
              : (mode === "login" ? "Se connecter" : "Créer mon organisation")}
          </button>
        </form>

        <div style={{ textAlign: "center", marginTop: "1.5rem", fontSize: 11, color: "#94a3b8" }}>
          InsightFlow Executive © 2026
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "linear-gradient(135deg, #1d2d44 0%, #0d1321 100%)",
        fontFamily: "DM Sans, sans-serif",
      }}>
        <div style={{ width: 32, height: 32, border: "2px solid rgba(255,255,255,0.2)", borderTop: "2px solid #3d5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      </div>
    }>
      <LoginInner />
    </Suspense>
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "10px 14px", borderRadius: 10,
  border: "1px solid #e2e8f0", fontSize: 13, outline: "none",
  background: "#f8fafc", color: "#0d1321",
  boxSizing: "border-box",
  transition: "border-color 0.15s",
};
