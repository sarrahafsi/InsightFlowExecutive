"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getUser, isCEO } from "@/lib/auth";

const COLORS = ["#3e5c76", "#0052CC", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#be185d"];

interface MemberDraft { name: string; email: string; role: string; }

export default function NewProjectPage() {
  const router      = useRouter();
  const { t }       = useI18n();
  const [step, setStep]               = useState<1 | 2>(1);

  useEffect(() => {
    const user = getUser();
    if (user && !isCEO(user)) router.replace("/dashboard/projects");
  }, [router]);

  // Step 1
  const [name, setName]               = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor]             = useState("#3e5c76");
  const [error, setError]             = useState("");

  // Step 2
  const [members, setMembers]         = useState<MemberDraft[]>([]);
  const [mName,  setMName]            = useState("");
  const [mEmail, setMEmail]           = useState("");
  const [mRole,  setMRole]            = useState("member");
  const [loading, setLoading]         = useState(false);

  function goToStep2() {
    if (!name.trim()) { setError(t.proj_form_name); return; }
    setError("");
    setStep(2);
  }

  function addMemberDraft() {
    if (!mName.trim() || !mEmail.trim()) return;
    setMembers(prev => [...prev, { name: mName.trim(), email: mEmail.trim(), role: mRole }]);
    setMName(""); setMEmail(""); setMRole("member");
  }

  function removeMemberDraft(idx: number) {
    setMembers(prev => prev.filter((_, i) => i !== idx));
  }

  async function handleCreate() {
    setLoading(true);
    setError("");
    try {
      const res = await API.post("/api/projects", { name: name.trim(), description, color });
      const projectId = res.data.id;

      // Add members in parallel
      await Promise.all(members.map(m =>
        API.post(`/api/projects/${projectId}/members`, m)
      ));

      router.push(`/dashboard/projects/${projectId}`);
    } catch {
      setError("Erreur lors de la création du projet.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 580, margin: "3rem auto" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        input:focus, textarea:focus, select:focus { border-color: #3e5c76 !important; box-shadow: 0 0 0 3px rgba(62,92,118,0.1); }
      `}</style>

      {/* Back */}
      <button onClick={() => step === 2 ? setStep(1) : router.back()}
        style={{ background: "none", border: "none", color: "#748cab", fontSize: 13, cursor: "pointer", marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: 6, padding: 0, fontFamily: "DM Sans, sans-serif" }}>
        {step === 2 ? "← Retour" : t.proj_form_back}
      </button>

      {/* Progress */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "2rem" }}>
        {[1, 2].map(s => (
          <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 28, height: 28, borderRadius: "50%", fontSize: 12, fontWeight: 700,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: step >= s ? "#1d2d44" : "rgba(62,92,118,0.1)",
              color: step >= s ? "#f0ebd8" : "#748cab",
              transition: "all 0.2s",
            }}>{s}</div>
            <span style={{ fontSize: 12, color: step >= s ? "#0d1321" : "#748cab", fontWeight: step === s ? 600 : 400 }}>
              {s === 1 ? "Informations" : "Membres"}
            </span>
            {s < 2 && <div style={{ width: 32, height: 1, background: step > s ? "#1d2d44" : "rgba(62,92,118,0.15)", transition: "background 0.2s" }} />}
          </div>
        ))}
      </div>

      {/* ── STEP 1 ── */}
      {step === 1 && (
        <>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", marginBottom: "0.25rem" }}>
            {t.proj_form_title}
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginBottom: "2rem" }}>{t.proj_form_sub}</p>

          <div style={{ background: "#fff", borderRadius: 16, padding: "2rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)", display: "flex", flexDirection: "column", gap: "1.25rem" }}>

            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", display: "block", marginBottom: 6 }}>{t.proj_form_name}</label>
              <input value={name} onChange={e => setName(e.target.value)} placeholder={t.proj_form_name_ph}
                onKeyDown={e => e.key === "Enter" && goToStep2()}
                style={{ width: "100%", padding: "10px 13px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 9, fontSize: 14, fontFamily: "DM Sans, sans-serif", outline: "none", transition: "border-color 0.2s, box-shadow 0.2s" }} />
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", display: "block", marginBottom: 6 }}>
                {t.proj_form_desc} <span style={{ fontWeight: 400, color: "#748cab" }}>{t.proj_form_desc_opt}</span>
              </label>
              <textarea value={description} onChange={e => setDescription(e.target.value)} placeholder={t.proj_form_desc_ph} rows={3}
                style={{ width: "100%", padding: "10px 13px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 9, fontSize: 14, fontFamily: "DM Sans, sans-serif", outline: "none", resize: "vertical", transition: "border-color 0.2s, box-shadow 0.2s" }} />
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", display: "block", marginBottom: 8 }}>{t.proj_form_color}</label>
              <div style={{ display: "flex", gap: 8 }}>
                {COLORS.map(c => (
                  <button key={c} onClick={() => setColor(c)}
                    style={{ width: 28, height: 28, borderRadius: "50%", background: c, border: "none", cursor: "pointer", outline: color === c ? `3px solid ${c}` : "none", outlineOffset: 2 }} />
                ))}
              </div>
            </div>

            {/* Preview */}
            <div style={{ background: "#f8f9fa", borderRadius: 10, padding: "12px 14px", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 4, height: 32, borderRadius: 4, background: color }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#0d1321" }}>{name || t.proj_form_name_ph}</div>
                {description && <div style={{ fontSize: 12, color: "#748cab", marginTop: 2 }}>{description}</div>}
              </div>
            </div>

            {error && <div style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 9, padding: "10px 14px", color: "#dc2626", fontSize: 13 }}>{error}</div>}

            <button onClick={goToStep2}
              style={{ background: "linear-gradient(135deg, #1d2d44, #3e5c76)", color: "#f0ebd8", border: "none", borderRadius: 10, padding: "12px 0", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif", width: "100%" }}>
              Suivant → Ajouter des membres
            </button>
          </div>
        </>
      )}

      {/* ── STEP 2 ── */}
      {step === 2 && (
        <>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", marginBottom: "0.25rem" }}>
            Membres du projet
          </h1>
          <p style={{ color: "#748cab", fontSize: 13, marginBottom: "2rem" }}>
            Ajoutez les membres maintenant ou plus tard dans les paramètres.
          </p>

          <div style={{ background: "#fff", borderRadius: 16, padding: "2rem", boxShadow: "0 2px 12px rgba(13,19,33,0.06)", border: "1px solid rgba(62,92,118,0.1)", display: "flex", flexDirection: "column", gap: "1.25rem" }}>

            {/* Add member form */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", display: "block", marginBottom: 6 }}>{t.proj_member_name_ph}</label>
                  <input value={mName} onChange={e => setMName(e.target.value)} placeholder="Sarah Hafsi"
                    style={{ width: "100%", padding: "9px 12px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none" }} />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", display: "block", marginBottom: 6 }}>{t.proj_member_email_ph}</label>
                  <input value={mEmail} onChange={e => setMEmail(e.target.value)} placeholder="sarah@exemple.com" type="email"
                    style={{ width: "100%", padding: "9px 12px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none" }} />
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", display: "block", marginBottom: 6 }}>{t.proj_member_role}</label>
                  <select value={mRole} onChange={e => setMRole(e.target.value)}
                    style={{ width: "100%", padding: "9px 12px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none", background: "#fff" }}>
                    <option value="member">Member</option>
                    <option value="owner">Owner</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </div>
                <button onClick={addMemberDraft} disabled={!mName.trim() || !mEmail.trim()}
                  style={{ padding: "9px 20px", background: mName.trim() && mEmail.trim() ? "#1d2d44" : "#e5e7eb", color: mName.trim() && mEmail.trim() ? "#f0ebd8" : "#9ca3af", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif", whiteSpace: "nowrap" }}>
                  + Ajouter
                </button>
              </div>
            </div>

            {/* Members list */}
            {members.length > 0 && (
              <div style={{ border: "1px solid rgba(62,92,118,0.1)", borderRadius: 10, overflow: "hidden" }}>
                {members.map((m, idx) => (
                  <div key={idx} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderBottom: idx < members.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none", background: "#fafafa" }}>
                    <div style={{ width: 30, height: 30, borderRadius: "50%", background: "#1d2d44", color: "#f0ebd8", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>
                      {m.name[0].toUpperCase()}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{m.name}</div>
                      <div style={{ fontSize: 11, color: "#748cab" }}>{m.email}</div>
                    </div>
                    <span style={{ fontSize: 11, background: "rgba(62,92,118,0.07)", color: "#3e5c76", borderRadius: 6, padding: "2px 8px", fontWeight: 600 }}>{m.role}</span>
                    <button onClick={() => removeMemberDraft(idx)}
                      style={{ background: "none", border: "none", color: "#ef4444", fontSize: 12, cursor: "pointer" }}>✕</button>
                  </div>
                ))}
              </div>
            )}

            {members.length === 0 && (
              <div style={{ textAlign: "center", padding: "1rem", color: "#a0b4c4", fontSize: 13, background: "#f8f9fa", borderRadius: 10 }}>
                Aucun membre — vous pouvez en ajouter plus tard
              </div>
            )}

            {error && <div style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 9, padding: "10px 14px", color: "#dc2626", fontSize: 13 }}>{error}</div>}

            <button onClick={handleCreate} disabled={loading}
              style={{ background: loading ? "#93b4e0" : "linear-gradient(135deg, #1d2d44, #3e5c76)", color: "#f0ebd8", border: "none", borderRadius: 10, padding: "12px 0", fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", fontFamily: "DM Sans, sans-serif", width: "100%" }}>
              {loading ? t.proj_form_creating : `${t.proj_form_submit}${members.length > 0 ? ` (${members.length} membre${members.length > 1 ? "s" : ""})` : ""}`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
