"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import API, { ApiError } from "@/lib/api";
import { getUser, setUser, isLoggedIn, logout, type AuthUser } from "@/lib/auth";

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600;700&display=swap');
  @keyframes spin{to{transform:rotate(360deg)}}
`;

function shell(children: React.ReactNode) {
  return (
    <div style={{ minHeight: "100vh", background: "#f5f3ee", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "DM Sans, sans-serif", padding: "2rem" }}>
      <style>{GLOBAL_CSS}</style>
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 3, background: "linear-gradient(90deg, #1d2d44, #3e5c76, #748cab)" }} />
      {children}
    </div>
  );
}

function VerifyEmailInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");

  const [checking, setChecking] = useState(!!token);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);
  const [email, setEmail] = useState<string>("");

  useEffect(() => {
    if (!isLoggedIn()) { router.replace("/login"); return; }
    const u = getUser();
    if (u) setEmail(u.email);
    if (u?.email_verified && u.org_id) { router.replace("/dashboard"); return; }
    // Vérifie que la session est toujours valide côté serveur (ex: compte supprimé entretemps).
    API.get("/auth/me").catch((e) => { if (e instanceof ApiError && e.status === 401) logout(); });
  }, [router]);

  useEffect(() => {
    if (!token) return;
    API.post("/auth/verify-email", { token })
      .then(r => {
        setUser(r.data as AuthUser);
        router.replace("/create-organisation");
      })
      .catch((e: any) => setVerifyError(e.body?.detail ?? "Lien de vérification invalide ou expiré."))
      .finally(() => setChecking(false));
  }, [token, router]);

  async function resend() {
    setResending(true); setResendMsg(null);
    try {
      await API.post("/auth/resend-verification", {});
      setResendMsg("Un nouveau lien de vérification vous a été envoyé.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        // Session invalide (compte supprimé, token expiré...) — repartir de zéro proprement.
        logout();
        return;
      }
      setResendMsg("Erreur — réessayez dans quelques instants.");
    } finally {
      setResending(false);
    }
  }

  if (checking) return shell(
    <div style={{ textAlign: "center" }}>
      <div style={{ width: 28, height: 28, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
      <p style={{ color: "#748cab", fontSize: 13 }}>Vérification en cours…</p>
    </div>
  );

  return shell(
    <div style={{ textAlign: "center", maxWidth: 460, background: "#fff", borderRadius: 24, padding: "2.75rem 2.5rem", boxShadow: "0 20px 60px rgba(0,0,0,0.12)" }}>
      <div style={{ width: 64, height: 64, borderRadius: "50%", background: "#1d2d44", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1.75rem", fontSize: 26 }}>
        ✉️
      </div>
      <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 24, color: "#0d1321", marginBottom: 12 }}>
        Vérifiez votre boîte mail
      </h1>
      <p style={{ color: "#748cab", fontSize: 14, lineHeight: 1.7, marginBottom: "1.5rem" }}>
        {verifyError
          ? verifyError
          : <>Un lien de vérification a été envoyé à <strong style={{ color: "#0d1321" }}>{email}</strong>. Cliquez dessus pour activer votre compte.</>}
      </p>

      <button
        onClick={resend}
        disabled={resending}
        style={{
          background: "#1d2d44", color: "#f0ebd8", border: "none", borderRadius: 12,
          padding: "11px 26px", fontSize: 13, fontWeight: 700,
          cursor: resending ? "not-allowed" : "pointer", opacity: resending ? 0.6 : 1,
        }}
      >
        {resending ? "Envoi..." : "Renvoyer le lien"}
      </button>

      {resendMsg && (
        <div style={{ marginTop: 14, fontSize: 12, color: "#3e5c76" }}>{resendMsg}</div>
      )}

      <div style={{ marginTop: 20 }}>
        <button
          onClick={logout}
          style={{ background: "none", border: "none", color: "#94a3b8", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}
        >
          Se déconnecter / utiliser un autre email
        </button>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh", background: "#f5f3ee" }} />}>
      <VerifyEmailInner />
    </Suspense>
  );
}
