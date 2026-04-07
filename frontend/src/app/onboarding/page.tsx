"use client";
import { useEffect, useState } from "react";
import API, { Source, SourcesResponse } from "@/lib/api";

export default function Onboarding() {
  const [sourcesByCategory, setSourcesByCategory] = useState<SourcesResponse>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get("/api/sources/categories")
      .then((res) => setSourcesByCategory(res.data))
      .catch((err) => console.error("Sources fetch error:", err))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (key: string, available: boolean) => {
    if (!available) return;
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((s) => s !== key) : [...prev, key]
    );
  };

  const handleConnect = () => {
    if (selected.length === 0) return;
    if (selected.includes("gmail")) {
      API.get("/auth/google").then((res) => {
        localStorage.setItem("pending_sources", JSON.stringify(selected));
        window.location.href = res.data.url;
      });
    }
  };

  if (loading) return (
    <div style={{
      minHeight: "100vh", background: "#f0ebd8",
      display: "flex", alignItems: "center", justifyContent: "center",
      flexDirection: "column", gap: 14
    }}>
      <div style={{
        width: 36, height: 36,
        border: "2px solid rgba(62,92,118,0.15)",
        borderTop: "2px solid #3e5c76",
        borderRadius: "50%", animation: "spin 0.8s linear infinite"
      }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <p style={{ color: "#748cab", fontFamily: "DM Sans, sans-serif", fontSize: 13 }}>
        Chargement des sources...
      </p>
    </div>
  );

  return (
    <div style={{
      minHeight: "100vh",
      background: "#f0ebd8",
      color: "#0d1321",
      fontFamily: "DM Sans, sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        .ob-anim{animation:fadeUp 0.5s ease forwards;}
        .ob-anim-1{animation:fadeUp 0.5s ease 0.1s forwards;opacity:0;}
        .ob-anim-2{animation:fadeUp 0.5s ease 0.2s forwards;opacity:0;}
        .source-card{transition:all 0.2s ease;position:relative;}
        .source-card:hover:not([data-disabled]){transform:translateY(-2px);box-shadow:0 8px 32px rgba(13,19,33,0.1);}
        .connect-btn{transition:all 0.25s ease;}
        .connect-btn:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 24px rgba(29,45,68,0.25);}
      `}</style>

      <div style={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        background: "radial-gradient(ellipse 80% 60% at 10% 0%, rgba(116,140,171,0.12) 0%, transparent 60%), radial-gradient(ellipse 60% 50% at 90% 100%, rgba(62,92,118,0.1) 0%, transparent 60%)"
      }} />
      <div style={{
        position: "fixed", top: 0, left: 0, right: 0, height: 3, zIndex: 1,
        background: "linear-gradient(90deg, #1d2d44, #3e5c76, #748cab, #3e5c76, #1d2d44)"
      }} />

      <div style={{ maxWidth: 960, margin: "0 auto", padding: "4rem 2rem 3rem", position: "relative", zIndex: 1 }}>

        <div className="ob-anim" style={{ textAlign: "center", marginBottom: "3.5rem" }}>
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "6px 16px", borderRadius: 100,
            background: "rgba(29,45,68,0.08)", border: "1px solid rgba(62,92,118,0.2)",
            marginBottom: "1.5rem"
          }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#3e5c76" }} />
            <span style={{ fontSize: "0.7rem", letterSpacing: "0.2em", textTransform: "uppercase", color: "#3e5c76", fontWeight: 600 }}>
              InsightFlow Executive
            </span>
          </div>
          <h1 style={{
            fontFamily: "DM Serif Display, serif", fontSize: "3rem",
            color: "#0d1321", letterSpacing: "-0.02em", lineHeight: 1.1,
            marginBottom: "1rem"
          }}>
            Connectez vos sources
          </h1>
          <p style={{ color: "#748cab", fontSize: "1rem", maxWidth: 480, margin: "0 auto" }}>
            Sélectionnez les plateformes à analyser pour votre dashboard CEO
          </p>
        </div>

        <div className="ob-anim-1">
          {Object.entries(sourcesByCategory).map(([category, sources]) => (
            <div key={category} style={{ marginBottom: "2.5rem" }}>
              <div style={{
                fontSize: "0.65rem", letterSpacing: "0.2em", textTransform: "uppercase",
                color: "#748cab", marginBottom: "1rem", paddingLeft: "0.25rem",
                display: "flex", alignItems: "center", gap: 8
              }}>
                <div style={{ width: 20, height: 1, background: "rgba(116,140,171,0.4)" }} />
                {category}
                <div style={{ flex: 1, height: 1, background: "rgba(116,140,171,0.15)" }} />
              </div>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
                gap: "1rem"
              }}>
                {sources.map((source: Source) => {
                  const isSelected = selected.includes(source.key);
                  const isAvailable = source.available;
                  return (
                    <div
                      key={source.key}
                      className="source-card"
                      data-disabled={!isAvailable ? "true" : undefined}
                      onClick={() => toggle(source.key, isAvailable)}
                      style={{
                        background: isSelected ? "rgba(29,45,68,0.06)" : "#ffffff",
                        border: `1.5px solid ${isSelected ? "#1d2d44" : "rgba(62,92,118,0.15)"}`,
                        borderRadius: 16,
                        padding: "1.4rem",
                        cursor: isAvailable ? "pointer" : "not-allowed",
                        opacity: isAvailable ? 1 : 0.45,
                        boxShadow: isSelected
                          ? "0 4px 20px rgba(29,45,68,0.12)"
                          : "0 2px 8px rgba(13,19,33,0.04)",
                      }}
                    >
                      <div style={{ fontSize: "1.9rem", marginBottom: "0.6rem" }}>{source.icon}</div>
                      <div style={{ fontWeight: 600, fontSize: "0.9rem", color: "#0d1321", marginBottom: "0.3rem" }}>
                        {source.name}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "#748cab", lineHeight: 1.5 }}>
                        {source.description}
                      </div>
                      {source.coming_soon && !isSelected && (
                        <div style={{
                          position: "absolute", top: 12, right: 12,
                          fontSize: "0.58rem", background: "rgba(116,140,171,0.12)",
                          color: "#748cab", border: "1px solid rgba(116,140,171,0.25)",
                          borderRadius: 4, padding: "2px 6px", letterSpacing: "0.06em", fontWeight: 600
                        }}>
                          BIENTÔT
                        </div>
                      )}
                      {isSelected && (
                        <div style={{
                          position: "absolute", top: 12, right: 12,
                          width: 22, height: 22, borderRadius: "50%",
                          background: "#1d2d44", display: "flex",
                          alignItems: "center", justifyContent: "center",
                          fontSize: "0.65rem", color: "#f0ebd8", fontWeight: 700
                        }}>
                          ✓
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="ob-anim-2" style={{ textAlign: "center", marginTop: "2.5rem" }}>
          <button
            className="connect-btn"
            onClick={handleConnect}
            disabled={selected.length === 0}
            style={{
              padding: "15px 48px",
              borderRadius: 14,
              border: "none",
              background: selected.length > 0
                ? "linear-gradient(135deg, #1d2d44, #3e5c76)"
                : "rgba(116,140,171,0.15)",
              color: selected.length > 0 ? "#f0ebd8" : "#748cab",
              fontSize: "0.95rem",
              fontWeight: 600,
              cursor: selected.length > 0 ? "pointer" : "not-allowed",
              fontFamily: "DM Sans, sans-serif",
              letterSpacing: "0.01em",
            }}
          >
            {selected.length === 0
              ? "Sélectionnez au moins une source"
              : `Connecter ${selected.length} source${selected.length > 1 ? "s" : ""} \u2192`}
          </button>
          {selected.length > 0 && (
            <p style={{ marginTop: 12, fontSize: "0.75rem", color: "#748cab" }}>
              Vous serez redirigé vers l&apos;authentification OAuth
            </p>
          )}
        </div>

      </div>
    </div>
  );
}
