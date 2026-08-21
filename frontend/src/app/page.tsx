"use client";
import React from "react";
import Link from "next/link";
import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn, getUser } from "@/lib/auth";

function useTypewriter(words: string[], speed = 80, pause = 1800) {
  const [display, setDisplay] = useState("");
  const [wordIdx, setWordIdx] = useState(0);
  const [charIdx, setCharIdx] = useState(0);
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    const word = words[wordIdx];
    const delay = deleting ? speed / 2 : charIdx === word.length ? pause : speed;
    const t = setTimeout(() => {
      if (!deleting && charIdx < word.length) { setDisplay(word.slice(0, charIdx + 1)); setCharIdx((c) => c + 1); }
      else if (!deleting && charIdx === word.length) { setDeleting(true); }
      else if (deleting && charIdx > 0) { setDisplay(word.slice(0, charIdx - 1)); setCharIdx((c) => c - 1); }
      else { setDeleting(false); setWordIdx((i) => (i + 1) % words.length); }
    }, delay);
    return () => clearTimeout(t);
  }, [charIdx, deleting, wordIdx, words, speed, pause]);
  return display;
}

function useCountUp(target: number, duration = 1600, start = false) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!start) return;
    let raf: number;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - t0) / duration, 1);
      setVal(Math.floor((1 - Math.pow(1 - p, 3)) * target));
      if (p < 1) raf = requestAnimationFrame(tick); else setVal(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [start, target, duration]);
  return val;
}

function useInView() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    setVisible(true);
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) setVisible(true); },
      { threshold: 0.05 }
    );
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return { ref, visible };
}

function BlobBackground() {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: "-20%", left: "-10%", width: 700, height: 700, borderRadius: "50%", background: "radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%)", animation: "blobMove1 12s ease-in-out infinite" }} />
      <div style={{ position: "absolute", top: "10%", right: "-15%", width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(236,72,153,0.09) 0%, transparent 70%)", animation: "blobMove2 15s ease-in-out infinite" }} />
      <div style={{ position: "absolute", bottom: "-10%", left: "30%", width: 500, height: 500, borderRadius: "50%", background: "radial-gradient(circle, rgba(20,184,166,0.09) 0%, transparent 70%)", animation: "blobMove3 18s ease-in-out infinite" }} />
      <div style={{ position: "absolute", top: "55%", left: "15%", width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle, rgba(139,92,246,0.07) 0%, transparent 70%)", animation: "blobMove1 20s ease-in-out infinite reverse" }} />
    </div>
  );
}

function GridPattern() {
  return <div style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none", backgroundImage: "radial-gradient(circle, rgba(99,102,241,0.07) 1px, transparent 1px)", backgroundSize: "32px 32px" }} />;
}

function StatCard({ value, suffix, label, icon, color }: { value: number; suffix: string; label: string; icon: string; color: string }) {
  const { ref, visible } = useInView();
  const count = useCountUp(value, 1600, visible);
  return (
    <div ref={ref} style={{ background: "white", borderRadius: 24, padding: "2rem", boxShadow: "0 4px 24px rgba(0,0,0,0.06)", border: "1px solid rgba(0,0,0,0.06)", opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(24px)", transition: "opacity 0.6s ease, transform 0.6s ease", position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: -20, right: -20, width: 100, height: 100, borderRadius: "50%", background: `${color}12` }} />
      <div style={{ width: 48, height: 48, borderRadius: 16, background: `${color}15`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, marginBottom: 16 }}>{icon}</div>
      <div style={{ fontSize: "2.4rem", fontWeight: 800, color: "#0F172A", lineHeight: 1 }}>{count}<span style={{ color, fontSize: "1.8rem" }}>{suffix}</span></div>
      <div style={{ fontSize: 14, color: "#64748B", marginTop: 8, fontWeight: 500 }}>{label}</div>
    </div>
  );
}

function FeatureCard({ icon, title, desc, gradient, delay }: { icon: string; title: string; desc: string; gradient: string; delay: number }) {
  const { ref, visible } = useInView();
  const [hovered, setHovered] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const color1 = gradient.match(/#[0-9A-Fa-f]{6}/g)?.[0] ?? "#6366F1";
  const onMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const card = cardRef.current; if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.transform = `perspective(800px) rotateX(${((e.clientY - r.top - r.height / 2) / r.height) * -12}deg) rotateY(${((e.clientX - r.left - r.width / 2) / r.width) * 12}deg) translateY(-4px)`;
  }, []);
  const onLeave = useCallback(() => {
    if (cardRef.current) cardRef.current.style.transform = "perspective(800px) rotateX(0) rotateY(0) translateY(0)";
    setHovered(false);
  }, []);
  return (
    <div ref={ref} style={{ opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(32px)", transition: `opacity 0.6s ${delay}ms ease, transform 0.6s ${delay}ms ease`, padding: 2, borderRadius: 24, background: hovered ? gradient : "transparent", boxShadow: hovered ? `0 20px 60px ${color1}33` : "none" }} onMouseEnter={() => setHovered(true)} onMouseLeave={onLeave}>
      <div ref={cardRef} onMouseMove={onMove} style={{ background: "white", borderRadius: 22, padding: "1.75rem", border: hovered ? "none" : "1px solid rgba(0,0,0,0.08)", cursor: "pointer", transition: "transform 0.2s ease", height: "100%" }}>
        <div style={{ width: 52, height: 52, borderRadius: 16, background: gradient, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, marginBottom: "1.25rem", boxShadow: `0 8px 20px ${color1}44` }}>{icon}</div>
        <div style={{ fontSize: 17, fontWeight: 700, color: "#0F172A", marginBottom: 10 }}>{title}</div>
        <div style={{ fontSize: 14, color: "#64748B", lineHeight: 1.75 }}>{desc}</div>
      </div>
    </div>
  );
}

function StepCard({ num, title, desc, color, delay, isLast }: { num: string; title: string; desc: string; color: string; delay: number; isLast?: boolean }) {
  const { ref, visible } = useInView();
  return (
    <div ref={ref} style={{ display: "flex", gap: 20, opacity: visible ? 1 : 0, transform: visible ? "translateX(0)" : "translateX(-24px)", transition: `opacity 0.6s ${delay}ms ease, transform 0.6s ${delay}ms ease` }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        <div style={{ width: 48, height: 48, borderRadius: "50%", background: color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 800, color: "white", boxShadow: `0 8px 20px ${color}55`, flexShrink: 0 }}>{num}</div>
        {!isLast && <div style={{ width: 2, flex: 1, minHeight: 40, background: `linear-gradient(${color}, transparent)`, marginTop: 4, opacity: 0.3 }} />}
      </div>
      <div style={{ paddingBottom: isLast ? 0 : 32 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#0F172A", marginBottom: 6 }}>{title}</div>
        <div style={{ fontSize: 14, color: "#64748B", lineHeight: 1.7 }}>{desc}</div>
      </div>
    </div>
  );
}

function DashboardPreview() {
  const [tick, setTick] = useState(0);
  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 2200); return () => clearInterval(t); }, []);
  const kpis = [
    { label: "Chiffre d'affaires", val: ["+14.2%", "+15.1%", "+13.8%"][tick % 3], color: "#10B981", icon: "💰" },
    { label: "OHS Équipes", val: ["87/100", "89/100", "86/100"][tick % 3], color: "#6366F1", icon: "❤️" },
    { label: "Anomalies", val: ["3 critiques", "2 critiques", "4 critiques"][tick % 3], color: "#F59E0B", icon: "⚠️" },
    { label: "Projets actifs", val: "24", color: "#8B5CF6", icon: "📋" },
  ];
  const bars = [40, 65, 50, 80, 70, 90, 75];
  return (
    <div style={{ background: "white", borderRadius: 24, boxShadow: "0 40px 120px rgba(99,102,241,0.15), 0 8px 32px rgba(0,0,0,0.08)", overflow: "hidden", border: "1px solid rgba(99,102,241,0.12)", maxWidth: 720, width: "100%" }}>
      <div style={{ background: "#F8FAFC", padding: "12px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)", display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#FF5F57" }} />
        <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#FEBC2E" }} />
        <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#28C840" }} />
        <div style={{ flex: 1, height: 26, background: "white", borderRadius: 8, marginLeft: 12, border: "1px solid rgba(0,0,0,0.08)", display: "flex", alignItems: "center", paddingLeft: 12, gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#10B981", animation: "pulse 2s infinite" }} />
          <span style={{ fontSize: 11, color: "#94A3B8", fontFamily: "monospace" }}>insightflow.ai/dashboard</span>
        </div>
      </div>
      <div style={{ padding: "1.25rem", background: "#F8FAFF" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 13, color: "#6366F1", fontWeight: 600 }}>Bonjour, Sarah 👋</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: "#0F172A" }}>Tableau de bord exécutif</div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {["📧", "🔔"].map((ic, i) => <div key={i} style={{ width: 34, height: 34, borderRadius: 10, background: "white", border: "1px solid rgba(0,0,0,0.08)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>{ic}</div>)}
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 14 }}>
          {kpis.map((k) => (
            <div key={k.label} style={{ background: "white", borderRadius: 14, padding: "12px", border: "1px solid rgba(0,0,0,0.06)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
              <div style={{ fontSize: 18, marginBottom: 4 }}>{k.icon}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: k.color, transition: "all 0.5s" }}>{k.val}</div>
              <div style={{ fontSize: 10, color: "#94A3B8", marginTop: 2 }}>{k.label}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 10, marginBottom: 14 }}>
          <div style={{ background: "white", borderRadius: 14, padding: "12px", border: "1px solid rgba(0,0,0,0.06)" }}>
            <div style={{ fontSize: 11, color: "#94A3B8", fontWeight: 600, marginBottom: 10 }}>Activité 7 jours</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 50 }}>
              {bars.map((h, i) => <div key={i} style={{ flex: 1 }}><div style={{ width: "100%", height: `${h + (tick % 2 === 0 && i === 5 ? 8 : 0)}%`, background: i === 5 ? "linear-gradient(180deg,#6366F1,#8B5CF6)" : "rgba(99,102,241,0.12)", borderRadius: 4, transition: "height 0.8s ease" }} /></div>)}
            </div>
          </div>
          <div style={{ background: "white", borderRadius: 14, padding: "12px", border: "1px solid rgba(0,0,0,0.06)" }}>
            <div style={{ fontSize: 11, color: "#94A3B8", fontWeight: 600, marginBottom: 10 }}>Sentiment global</div>
            {[{ l: "Positif", v: 68, c: "#10B981" }, { l: "Neutre", v: 22, c: "#94A3B8" }, { l: "Négatif", v: 10, c: "#EF4444" }].map((s) => (
              <div key={s.l} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                <div style={{ fontSize: 10, color: "#64748B", width: 42, flexShrink: 0 }}>{s.l}</div>
                <div style={{ flex: 1, height: 7, background: "#F1F5F9", borderRadius: 4, overflow: "hidden" }}><div style={{ width: `${s.v}%`, height: "100%", background: s.c, borderRadius: 4 }} /></div>
                <div style={{ fontSize: 10, color: "#64748B", width: 24, textAlign: "right" }}>{s.v}%</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ background: "white", borderRadius: 14, padding: "12px", border: "1px solid rgba(0,0,0,0.06)" }}>
          <div style={{ fontSize: 11, color: "#94A3B8", fontWeight: 600, marginBottom: 10 }}>Priorité Inbox IA</div>
          {[
            { dot: "#EF4444", text: "Budget Q3 en attente — CFO", time: "2m", pulse: true },
            { dot: "#F59E0B", text: "Retard détecté sur Sprint Alpha", time: "15m", pulse: false },
            { dot: "#10B981", text: "Demo client confirmée vendredi", time: "1h", pulse: false }
          ].map((m, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderBottom: i < 2 ? "1px solid #F1F5F9" : "none" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: m.dot, flexShrink: 0, animation: m.pulse ? "pulse 1.2s infinite" : "none", boxShadow: m.pulse ? `0 0 0 3px ${m.dot}33` : "none" }} />
              <div style={{ fontSize: 11, color: "#334155", flex: 1 }}>{m.text}</div>
              <div style={{ fontSize: 10, color: "#94A3B8" }}>{m.time}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FloatingBadge({ label, icon, extraStyle }: { label: string; icon: string; extraStyle?: React.CSSProperties }) {
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "white", borderRadius: 100, padding: "8px 16px", boxShadow: "0 8px 32px rgba(0,0,0,0.10)", border: "1px solid rgba(0,0,0,0.06)", fontSize: 13, fontWeight: 600, color: "#0F172A", whiteSpace: "nowrap", ...extraStyle }}>
      <span>{icon}</span>{label}
    </div>
  );
}

function TestiCard({ quote, name, role, avatar }: { quote: string; name: string; role: string; avatar: string }) {
  const { ref, visible } = useInView();
  return (
    <div ref={ref} style={{ background: "white", borderRadius: 20, padding: "1.75rem", boxShadow: "0 4px 24px rgba(0,0,0,0.06)", border: "1px solid rgba(0,0,0,0.06)", opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(20px)", transition: "opacity 0.6s ease, transform 0.6s ease" }}>
      <div style={{ fontSize: 28, color: "#6366F1", marginBottom: 12, lineHeight: 1, fontFamily: "Georgia, serif" }}>&ldquo;</div>
      <div style={{ fontSize: 14, color: "#475569", lineHeight: 1.8, marginBottom: 16 }}>{quote}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: "50%", background: "linear-gradient(135deg,#6366F1,#EC4899)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>{avatar}</div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#0F172A" }}>{name}</div>
          <div style={{ fontSize: 12, color: "#94A3B8" }}>{role}</div>
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const [scrolled, setScrolled] = useState(false);
  const [mouse, setMouse] = useState({ x: 0, y: 0 });
  const typed = useTypewriter(["vos emails", "vos projets", "vos KPIs", "vos équipes", "vos décisions"], 70, 2000);

  useEffect(() => {
    if (isLoggedIn()) {
      const user = getUser();
      router.replace(user?.role === "superadmin" ? "/dashboard/admin" : "/dashboard");
    }
  }, [router]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    const onMouse = (e: MouseEvent) => setMouse({ x: e.clientX, y: e.clientY });
    window.addEventListener("scroll", onScroll);
    window.addEventListener("mousemove", onMouse);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("mousemove", onMouse); };
  }, []);

  return (
    <div style={{ background: "#FAFBFF", minHeight: "100vh", fontFamily: "'Inter', sans-serif", overflowX: "hidden", color: "#0F172A" }}>
      <BlobBackground />
      <GridPattern />
      <div style={{ position: "fixed", width: 480, height: 480, borderRadius: "50%", pointerEvents: "none", zIndex: 0, background: "radial-gradient(circle, rgba(99,102,241,0.06) 0%, transparent 70%)", transform: `translate(${mouse.x - 240}px, ${mouse.y - 240}px)`, transition: "transform 0.12s ease-out" }} />

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        @keyframes blobMove1{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(60px,-40px) scale(1.1)}66%{transform:translate(-40px,60px) scale(0.95)}}
        @keyframes blobMove2{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(-80px,40px) scale(1.05)}66%{transform:translate(40px,-60px) scale(1.1)}}
        @keyframes blobMove3{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-60px,-40px) scale(1.1)}}
        @keyframes fadeUp{from{opacity:0;transform:translateY(32px)}to{opacity:1;transform:translateY(0)}}
        @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}
        @keyframes floatA{0%,100%{transform:translateY(0) rotate(-2deg)}50%{transform:translateY(-10px) rotate(2deg)}}
        @keyframes floatB{0%,100%{transform:translateY(0) rotate(1deg)}50%{transform:translateY(-14px) rotate(-1deg)}}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes gradientShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
        *{box-sizing:border-box}
        .btn-primary{display:inline-flex;align-items:center;gap:10px;background:linear-gradient(135deg,#6366F1 0%,#8B5CF6 50%,#EC4899 100%);background-size:200% 200%;color:white;text-decoration:none;font-size:15px;font-weight:700;padding:14px 32px;border-radius:14px;border:none;cursor:pointer;box-shadow:0 8px 32px rgba(99,102,241,0.35);transition:all 0.3s ease;animation:gradientShift 4s ease infinite}
        .btn-primary:hover{transform:translateY(-2px);box-shadow:0 16px 48px rgba(99,102,241,0.45)}
        .btn-secondary{display:inline-flex;align-items:center;gap:10px;background:white;color:#0F172A;text-decoration:none;font-size:15px;font-weight:600;padding:14px 28px;border-radius:14px;border:1.5px solid rgba(0,0,0,0.1);transition:all 0.2s ease;box-shadow:0 2px 8px rgba(0,0,0,0.06)}
        .btn-secondary:hover{border-color:rgba(99,102,241,0.4);box-shadow:0 4px 16px rgba(99,102,241,0.12);transform:translateY(-1px)}
        .nav-link{font-size:14px;font-weight:500;color:#475569;text-decoration:none;padding:6px 12px;border-radius:8px;transition:all 0.2s}
        .nav-link:hover{color:#6366F1;background:rgba(99,102,241,0.06)}
        .gradient-text{background:linear-gradient(135deg,#6366F1 0%,#8B5CF6 50%,#EC4899 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
      `}</style>

      {/* Navbar */}
      <nav style={{ position: "fixed", top: 0, left: 0, right: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 2.5rem", height: 68, background: scrolled ? "rgba(255,255,255,0.88)" : "transparent", backdropFilter: scrolled ? "blur(20px)" : "none", borderBottom: scrolled ? "1px solid rgba(0,0,0,0.07)" : "none", transition: "all 0.3s ease" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 11, background: "linear-gradient(135deg,#6366F1,#8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 12px rgba(99,102,241,0.35)" }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M3 14L7 8L10 11L13 5L16 8" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="16" cy="8" r="2" fill="#34D399"><animate attributeName="r" values="1.5;2.2;1.5" dur="2s" repeatCount="indefinite"/></circle>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 8, letterSpacing: "0.15em", textTransform: "uppercase", color: "#94A3B8", lineHeight: 1 }}>InsightFlow</div>
            <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A", lineHeight: 1.2 }}>Executive</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {["Fonctionnalités", "Comment ça marche", "Témoignages"].map((l) => (
            <a key={l} href="#" className="nav-link">{l}</a>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Link href="/login" className="nav-link">Se connecter</Link>
          <Link href="/login" className="btn-primary" style={{ padding: "9px 20px", fontSize: 13 }}>
            Démarrer gratuitement
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "8rem 2rem 4rem", position: "relative", zIndex: 1, textAlign: "center" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 100, padding: "6px 16px", marginBottom: "2rem", animation: "fadeUp 0.5s 0.1s both" }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#10B981", animation: "pulse 1.5s infinite" }} />
          <span style={{ fontSize: 12, color: "#6366F1", fontWeight: 600 }}>✦ Nouvelle génération d&apos;intelligence exécutive</span>
        </div>
        <h1 style={{ fontSize: "clamp(2.8rem,6.5vw,5.5rem)", fontWeight: 900, lineHeight: 1.08, letterSpacing: "-0.03em", maxWidth: 900, marginBottom: "1.5rem", animation: "fadeUp 0.6s 0.2s both", color: "#0F172A" }}>
          Pilotez <span className="gradient-text">{typed}<span style={{ animation: "pulse 1s infinite", marginLeft: 2 }}>|</span></span><br />avec l&apos;IA.
        </h1>
        <p style={{ fontSize: "clamp(1rem,2vw,1.2rem)", color: "#64748B", maxWidth: 560, lineHeight: 1.8, marginBottom: "2.5rem", animation: "fadeUp 0.6s 0.35s both" }}>
          InsightFlow Executive agrège toutes vos sources de données, détecte les anomalies critiques en temps réel et vous répond en langage naturel.
        </p>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center", animation: "fadeUp 0.6s 0.5s both" }}>
          <Link href="/login" className="btn-primary" style={{ fontSize: 15, padding: "15px 36px" }}>
            Créer mon espace gratuitement
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </Link>
          <Link href="/login" className="btn-secondary" style={{ fontSize: 15, padding: "15px 28px" }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="#6366F1" strokeWidth="1.5"/><path d="M6.5 5.5l4 2.5-4 2.5V5.5z" fill="#6366F1"/></svg>
            Voir la démo
          </Link>
        </div>
        <div style={{ display: "flex", gap: 24, marginTop: "1.5rem", flexWrap: "wrap", justifyContent: "center", animation: "fadeUp 0.6s 0.65s both" }}>
          {["✓ Sans carte bancaire", "✓ Démarrage en 3 min", "✓ 100% sécurisé RGPD"].map((b) => (
            <span key={b} style={{ fontSize: 13, color: "#94A3B8", fontWeight: 500 }}>{b}</span>
          ))}
        </div>
        <div style={{ marginTop: "5rem", width: "100%", display: "flex", justifyContent: "center", position: "relative", animation: "fadeUp 0.8s 0.7s both" }}>
          <FloatingBadge label="Anomalie détectée !" icon="⚡" extraStyle={{ position: "absolute", top: -16, left: "7%", animation: "floatA 4s ease-in-out infinite", zIndex: 2, borderColor: "rgba(245,158,11,0.25)", boxShadow: "0 8px 32px rgba(245,158,11,0.15)" }} />
          <FloatingBadge label="NLP — 98% précision" icon="🧠" extraStyle={{ position: "absolute", top: 36, right: "5%", animation: "floatB 5s ease-in-out infinite", zIndex: 2, borderColor: "rgba(99,102,241,0.25)", boxShadow: "0 8px 32px rgba(99,102,241,0.15)" }} />
          <FloatingBadge label="OHS: 87/100 ↑" icon="❤️" extraStyle={{ position: "absolute", bottom: 50, left: "3%", animation: "floatA 6s ease-in-out infinite 1s", zIndex: 2, borderColor: "rgba(16,185,129,0.25)", boxShadow: "0 8px 32px rgba(16,185,129,0.15)" }} />
          <div style={{ animation: "float 6s ease-in-out infinite" }}><DashboardPreview /></div>
        </div>
      </section>

      {/* Integrations */}
      <section style={{ padding: "4rem 2rem", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 900, margin: "0 auto", textAlign: "center" }}>
          <p style={{ fontSize: 12, color: "#94A3B8", fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: "2rem" }}>Connecté nativement à vos outils</p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            {[
              { icon: "📧", name: "Gmail" }, { icon: "📋", name: "Jira" }, { icon: "✅", name: "ClickUp" },
              { icon: "💬", name: "Slack" }, { icon: "📅", name: "Google Calendar" }, { icon: "📁", name: "OneDrive" },
              { icon: "📮", name: "Outlook" }, { icon: "👥", name: "Teams" }
            ].map((t) => (
              <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 8, background: "white", borderRadius: 12, padding: "10px 18px", border: "1px solid rgba(0,0,0,0.08)", boxShadow: "0 2px 8px rgba(0,0,0,0.04)", fontSize: 13, fontWeight: 600, color: "#374151" }}>
                <span style={{ fontSize: 18 }}>{t.icon}</span>{t.name}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Stats */}
      <section style={{ padding: "5rem 2rem", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "3rem" }}>
            <div style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6366F1", fontWeight: 700, marginBottom: 12 }}>Impact mesuré</div>
            <h2 style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", fontWeight: 800, letterSpacing: "-0.02em" }}>Des résultats concrets, <span className="gradient-text">dès le premier jour</span></h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 20 }}>
            <StatCard value={12} suffix="+" label="Sources de données connectées" icon="🔌" color="#6366F1" />
            <StatCard value={98} suffix="%" label="Précision modèle NLP multilingue" icon="🧠" color="#8B5CF6" />
            <StatCard value={3} suffix="s" label="Temps de réponse IA moyen" icon="⚡" color="#EC4899" />
            <StatCard value={87} suffix="%" label="Réduction du temps de reporting" icon="📊" color="#10B981" />
          </div>
        </div>
      </section>

      {/* Features */}
      <section style={{ padding: "5rem 2rem", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "3.5rem" }}>
            <div style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6366F1", fontWeight: 700, marginBottom: 12 }}>Fonctionnalités</div>
            <h2 style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", fontWeight: 800, letterSpacing: "-0.02em" }}>Tout ce qu&apos;il faut pour <span className="gradient-text">décider vite et bien</span></h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 20 }}>
            <FeatureCard icon="🤖" title="Ask Anything" desc="Posez n'importe quelle question sur vos données. L'IA interroge emails, tickets, KPIs et vous répond en secondes." gradient="linear-gradient(135deg,#6366F1,#8B5CF6)" delay={0} />
            <FeatureCard icon="⚡" title="Détection d'anomalies temps réel" desc="Alertes sur déviations de budget, retards projets, tensions d'équipe — avant que ça devienne critique." gradient="linear-gradient(135deg,#F59E0B,#EF4444)" delay={100} />
            <FeatureCard icon="💬" title="Analyse de sentiment XLM-RoBERTa" desc="Modèle multilingue FR+EN détecte les signaux émotionnels dans toutes vos communications." gradient="linear-gradient(135deg,#8B5CF6,#EC4899)" delay={200} />
            <FeatureCard icon="❤️" title="Score OHS organisationnel" desc="Santé des équipes calculée en continu : burnout, surcharge, satisfaction — visible en un coup d'œil." gradient="linear-gradient(135deg,#10B981,#06B6D4)" delay={300} />
            <FeatureCard icon="📝" title="Monday Brief automatisé" desc="Rapport exécutif généré chaque lundi : 3 priorités, 3 décisions à prendre, contexte complet." gradient="linear-gradient(135deg,#EC4899,#F59E0B)" delay={400} />
            <FeatureCard icon="🔐" title="Sécurité & conformité RGPD" desc="Chiffrement end-to-end, OAuth 2.0, données hébergées en Europe. Aucune donnée partagée." gradient="linear-gradient(135deg,#06B6D4,#6366F1)" delay={500} />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section style={{ padding: "5rem 2rem", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "5rem", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6366F1", fontWeight: 700, marginBottom: 12 }}>Mise en route</div>
              <h2 style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: "3rem", lineHeight: 1.25 }}>Opérationnel en <span className="gradient-text">moins de 5 minutes</span></h2>
              <div style={{ display: "flex", flexDirection: "column" }}>
                <StepCard num="01" title="Connectez vos sources" desc="Autorisez Gmail, ClickUp, Jira, Outlook en un clic via OAuth sécurisé. Zéro configuration requise." color="#6366F1" delay={0} />
                <StepCard num="02" title="L'IA indexe et apprend" desc="Pipeline NLP analyse en continu tous vos messages, tickets, KPIs. Modèles entraînés sur vos données." color="#8B5CF6" delay={100} />
                <StepCard num="03" title="Posez vos questions" desc="Interface chat naturelle. L'IA répond avec les sources, le contexte et les actions recommandées." color="#EC4899" delay={200} isLast />
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ position: "relative", width: 320, height: 320 }}>
                {[0, 1, 2].map((i) => (
                  <div key={i} style={{ position: "absolute", inset: `${i * 18}%`, borderRadius: "50%", border: `1.5px ${i === 0 ? "solid" : "dashed"} rgba(99,102,241,${0.15 - i * 0.04})`, animation: `spin ${25 + i * 10}s linear infinite ${i % 2 === 0 ? "" : "reverse"}` }} />
                ))}
                <div style={{ position: "absolute", inset: "32%", background: "linear-gradient(135deg,#6366F1,#8B5CF6)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 60px rgba(99,102,241,0.4)" }}>
                  <svg width="44" height="44" viewBox="0 0 36 36" fill="none">
                    <path d="M6 26L11 16L16 20L22 10L28 14" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                    <circle cx="28" cy="14" r="3" fill="#34D399"><animate attributeName="r" values="2;3.5;2" dur="2s" repeatCount="indefinite"/></circle>
                  </svg>
                </div>
                {[
                  { angle: 0, icon: "📧", bg: "#EEF2FF" }, { angle: 51, icon: "📋", bg: "#FEF3C7" },
                  { angle: 102, icon: "✅", bg: "#D1FAE5" }, { angle: 153, icon: "💬", bg: "#FCE7F3" },
                  { angle: 204, icon: "📅", bg: "#E0E7FF" }, { angle: 255, icon: "📁", bg: "#F0FDF4" },
                  { angle: 306, icon: "📮", bg: "#FEF2F2" }
                ].map(({ angle, icon, bg }) => {
                  const rad = (angle * Math.PI) / 180;
                  return (
                    <div key={icon} style={{ position: "absolute", left: Math.round(160 + 128 * Math.cos(rad) - 22), top: Math.round(160 + 128 * Math.sin(rad) - 22), width: 44, height: 44, borderRadius: 14, background: bg, border: "1.5px solid rgba(0,0,0,0.08)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, boxShadow: "0 4px 16px rgba(0,0,0,0.08)" }}>{icon}</div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section style={{ padding: "5rem 2rem", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "3rem" }}>
            <div style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6366F1", fontWeight: 700, marginBottom: 12 }}>Témoignages</div>
            <h2 style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", fontWeight: 800, letterSpacing: "-0.02em" }}>Ils pilotent déjà avec <span className="gradient-text">InsightFlow</span></h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 20 }}>
            <TestiCard quote="En 3 clics je vois l'état de mes 12 projets, les emails urgents et l'humeur de mes équipes. C'est comme avoir un assistant exécutif H24." name="Karim B." role="CEO, Startup FinTech" avatar="👨💼" />
            <TestiCard quote="Le Monday Brief m'économise 2h chaque semaine. L'analyse de sentiment sur Slack m'a permis d'éviter un burnout dans l'équipe dev." name="Sofia M." role="Directrice Générale, Scale-up" avatar="👩💼" />
            <TestiCard quote="Les alertes d'anomalie sont bluffantes. Ça a détecté un dérapage budgétaire 3 semaines avant que mon CFO ne le voit." name="Thomas L." role="Co-Founder, SaaS B2B" avatar="🧑💼" />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section style={{ padding: "6rem 2rem", position: "relative", zIndex: 1 }}>
        <div style={{ maxWidth: 800, margin: "0 auto" }}>
          <div style={{ background: "linear-gradient(135deg,#6366F1 0%,#8B5CF6 50%,#EC4899 100%)", borderRadius: 32, padding: "4rem 3rem", textAlign: "center", position: "relative", overflow: "hidden", boxShadow: "0 32px 80px rgba(99,102,241,0.3)" }}>
            <div style={{ position: "absolute", top: -60, right: -60, width: 200, height: 200, borderRadius: "50%", background: "rgba(255,255,255,0.08)" }} />
            <div style={{ position: "absolute", bottom: -40, left: -40, width: 160, height: 160, borderRadius: "50%", background: "rgba(255,255,255,0.06)" }} />
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.7)", letterSpacing: "0.14em", textTransform: "uppercase", fontWeight: 700, marginBottom: 16, position: "relative" }}>Prêt à transformer votre façon de décider ?</div>
            <h2 style={{ fontSize: "clamp(2rem,4vw,3rem)", fontWeight: 900, color: "white", marginBottom: 16, letterSpacing: "-0.02em", position: "relative" }}>Votre cockpit exécutif<br />vous attend.</h2>
            <p style={{ color: "rgba(255,255,255,0.75)", fontSize: 16, maxWidth: 480, margin: "0 auto 2.5rem", lineHeight: 1.6, position: "relative" }}>Rejoignez les dirigeants qui pilotent leur organisation avec clarté, vitesse et confiance.</p>
            <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap", position: "relative" }}>
              <Link href="/login" style={{ display: "inline-flex", alignItems: "center", gap: 10, background: "white", color: "#6366F1", textDecoration: "none", fontSize: 15, fontWeight: 700, padding: "15px 36px", borderRadius: 14, boxShadow: "0 8px 32px rgba(0,0,0,0.15)", transition: "all 0.2s" }}>
                ✨ Créer mon organisation gratuitement
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="#6366F1" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </Link>
            </div>
            <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 12, marginTop: 20, position: "relative" }}>✓ Gratuit · ✓ Aucune carte requise · ✓ Données hébergées en France</p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ padding: "2.5rem", borderTop: "1px solid rgba(0,0,0,0.07)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16, position: "relative", zIndex: 1, background: "rgba(255,255,255,0.6)", backdropFilter: "blur(10px)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: 9, background: "linear-gradient(135deg,#6366F1,#8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" viewBox="0 0 18 18" fill="none"><path d="M3 14L7 8L10 11L13 5L16 8" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <span style={{ fontSize: 14, color: "#64748B", fontWeight: 500 }}>InsightFlow Executive © 2026</span>
        </div>
        <div style={{ display: "flex", gap: 24 }}>
          {["Connexion", "Inscription", "Contact", "Confidentialité"].map((l) => (
            <Link key={l} href="/login" style={{ fontSize: 13, color: "#94A3B8", textDecoration: "none" }}>{l}</Link>
          ))}
        </div>
      </footer>
    </div>
  );
}


