"use client";
import { useEffect, useState, useRef } from "react";

import API from "@/lib/api";

const SOURCE_META: Record<string, { label: string; color: string; icon: string }> = {
  outlook_calendar: { label: "Outlook",  color: "#0078D4", icon: "📨" },
  google_calendar:  { label: "Google",   color: "#EA4335", icon: "📅" },
  teams:            { label: "Teams",    color: "#6264A7", icon: "💬" },
  jira:             { label: "Jira",     color: "#0052CC", icon: "🎫" },
  clickup:          { label: "ClickUp",  color: "#7B68EE", icon: "✅" },
  slack:            { label: "Slack",    color: "#4A154B", icon: "💼" },
};

const DAY_NAMES_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const HOURS       = Array.from({ length: 12 }, (_, i) => i + 8); // 8h → 19h
const HOUR_HEIGHT = 64;
const GRID_START  = 8;

interface CalendarEvent {
  id: string; source: string; title: string;
  start: string; end: string; all_day: boolean;
  location: string; description: string; url: string;
  attendees: { name: string; email: string }[];
  color: string; organizer: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getMondayOfWeek(date: Date): Date {
  const d = new Date(date);
  const diff = d.getDay() === 0 ? -6 : 1 - d.getDay();
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}
function formatDate(d: Date) { return d.toISOString().slice(0, 10); }
function formatWeekLabel(monday: Date) {
  const sunday = new Date(monday); sunday.setDate(sunday.getDate() + 6);
  return `${monday.getDate()} ${monday.toLocaleDateString("fr-FR", { month: "long" })} → ${sunday.getDate()} ${sunday.toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}`;
}
function eventTopPx(start: Date)  { return (start.getHours() + start.getMinutes() / 60 - GRID_START) * HOUR_HEIGHT; }
function eventHeightPx(s: Date, e: Date) { return Math.max(30, ((e.getTime() - s.getTime()) / 3600000) * HOUR_HEIGHT); }

function computeOverlapLayout(events: CalendarEvent[]): Map<string, { colIndex: number; totalCols: number }> {
  const sorted = [...events].sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
  const columns: number[] = [];
  const placement = new Map<string, number>();
  for (const ev of sorted) {
    const s = new Date(ev.start).getTime(), e = new Date(ev.end).getTime();
    let placed = false;
    for (let c = 0; c < columns.length; c++) {
      if (columns[c] <= s) { columns[c] = e; placement.set(ev.id, c); placed = true; break; }
    }
    if (!placed) { placement.set(ev.id, columns.length); columns.push(e); }
  }
  const result = new Map<string, { colIndex: number; totalCols: number }>();
  for (const ev of sorted) {
    const evS = new Date(ev.start).getTime(), evE = new Date(ev.end).getTime();
    const myCol = placement.get(ev.id) ?? 0;
    let maxCol = myCol;
    for (const o of sorted) {
      if (o.id === ev.id) continue;
      const oS = new Date(o.start).getTime(), oE = new Date(o.end).getTime();
      if (oS < evE && oE > evS) maxCol = Math.max(maxCol, placement.get(o.id) ?? 0);
    }
    result.set(ev.id, { colIndex: myCol, totalCols: maxCol + 1 });
  }
  return result;
}

function totalMeetingMinutes(events: CalendarEvent[]) {
  return events.filter(e => !e.all_day).reduce((sum, e) => sum + (new Date(e.end).getTime() - new Date(e.start).getTime()) / 60000, 0);
}

function getNextMeeting(events: CalendarEvent[], now: Date): CalendarEvent | null {
  const upcoming = events
    .filter(e => !e.all_day && new Date(e.start) > now && new Date(e.start).toDateString() === now.toDateString())
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
  return upcoming[0] ?? null;
}

function formatCountdown(ms: number): string {
  const min = Math.floor(ms / 60000);
  if (min < 60) return `dans ${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return `dans ${h}h${m > 0 ? `${m}min` : ""}`;
}

function getDayHeatColor(hours: number): string {
  if (hours === 0)  return "rgba(62,92,118,0.1)";
  if (hours < 2)    return "#22c55e";
  if (hours < 4)    return "#f59e0b";
  if (hours < 6)    return "#f97316";
  return "#ef4444";
}

function detectAlerts(eventsByDay: CalendarEvent[][], weekDays: Date[]): { type: string; label: string; day: string; color: string }[] {
  const alerts: { type: string; label: string; day: string; color: string }[] = [];
  eventsByDay.forEach((dayEvents, i) => {
    const timed = dayEvents.filter(e => !e.all_day).sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
    const dayLabel = weekDays[i].toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "short" });

    // Back-to-back : 3+ réunions consécutives avec < 15min de pause
    let consecutive = 1;
    for (let j = 1; j < timed.length; j++) {
      const gap = (new Date(timed[j].start).getTime() - new Date(timed[j - 1].end).getTime()) / 60000;
      if (gap < 15) { consecutive++; } else { consecutive = 1; }
      if (consecutive >= 3) {
        alerts.push({ type: "back-to-back", label: `3 réunions consécutives sans pause`, day: dayLabel, color: "#f59e0b" });
        break;
      }
    }

    // Jour surchargé : > 5h de réunions
    const hrs = totalMeetingMinutes(timed) / 60;
    if (hrs > 5) alerts.push({ type: "overload", label: `Journée surchargée (${hrs.toFixed(1)}h en réunion)`, day: dayLabel, color: "#ef4444" });

    // Réunion très tôt (avant 8h30)
    if (timed.some(e => new Date(e.start).getHours() < 8 || (new Date(e.start).getHours() === 8 && new Date(e.start).getMinutes() < 30))) {
      alerts.push({ type: "early", label: "Réunion avant 8h30", day: dayLabel, color: "#6264A7" });
    }

    // Réunion très tard (après 19h)
    if (timed.some(e => new Date(e.end).getHours() >= 19)) {
      alerts.push({ type: "late", label: "Réunion après 19h", day: dayLabel, color: "#6264A7" });
    }
  });
  return alerts.slice(0, 6);
}

function getTopParticipants(events: CalendarEvent[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  events.filter(e => !e.all_day).forEach(ev => {
    ev.attendees.forEach(a => {
      const key = a.name || a.email;
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
    });
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function CalendarPage() {
  const [monday, setMonday]               = useState<Date>(() => getMondayOfWeek(new Date()));
  const [events, setEvents]               = useState<CalendarEvent[]>([]);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [popoverPos, setPopoverPos]       = useState({ x: 0, y: 0 });
  const [now, setNow]                     = useState(new Date());
  const containerRef                      = useRef<HTMLDivElement>(null);

  // Refresh "now" every minute for the countdown
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(t);
  }, []);

  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday); d.setDate(d.getDate() + i); return d;
  });

  useEffect(() => {
    const sunday = new Date(monday); sunday.setDate(sunday.getDate() + 6);
    setLoading(true); setError(null);
    API.get(`/api/calendar/events?start=${formatDate(monday)}&end=${formatDate(sunday)}`)
      .then(r => {
        setEvents(r.data.events ?? []);
        setActiveFilters(new Set<string>((r.data.events ?? []).map((e: CalendarEvent) => e.source)));
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [monday]);

  const prevWeek = () => { const d = new Date(monday); d.setDate(d.getDate() - 7); setMonday(d); setSelectedEvent(null); };
  const nextWeek = () => { const d = new Date(monday); d.setDate(d.getDate() + 7); setMonday(d); setSelectedEvent(null); };
  const goToday  = () => { setMonday(getMondayOfWeek(new Date())); setSelectedEvent(null); };
  const toggleFilter = (src: string) => {
    setActiveFilters(prev => { const n = new Set(prev); n.has(src) ? n.delete(src) : n.add(src); return n; });
    setSelectedEvent(null);
  };

  const visibleEvents  = events.filter(e => activeFilters.has(e.source));
  const allSources     = Array.from(new Set(events.map(e => e.source)));
  const totalMin       = totalMeetingMinutes(visibleEvents);
  const totalHours     = Math.floor(totalMin / 60);
  const remMin         = Math.round(totalMin % 60);

  const eventsByDay: CalendarEvent[][] = Array.from({ length: 7 }, () => []);
  visibleEvents.forEach(ev => {
    const evDate = new Date(ev.start);
    weekDays.forEach((day, i) => {
      if (evDate.getFullYear() === day.getFullYear() && evDate.getMonth() === day.getMonth() && evDate.getDate() === day.getDate())
        eventsByDay[i].push(ev);
    });
  });

  // ── CEO Intelligence ──────────────────────────────────────────────────────
  const isCurrentWeek  = getMondayOfWeek(now).toDateString() === monday.toDateString();
  const nextMeeting    = isCurrentWeek ? getNextMeeting(visibleEvents, now) : null;
  const alerts         = detectAlerts(eventsByDay, weekDays);
  const topParticipants = getTopParticipants(visibleEvents);
  const dayHours       = eventsByDay.map(d => totalMeetingMinutes(d.filter(e => !e.all_day)) / 60);
  const overloadedDays = dayHours.filter(h => h > 4).length;
  const focusDays      = dayHours.slice(0, 5).filter(h => h < 2).length; // weekdays only
  const uniquePeople   = new Set(visibleEvents.flatMap(e => e.attendees.map(a => a.email || a.name))).size;
  const weekLoad       = Math.min(100, Math.round((totalMin / 60 / 40) * 100)); // 40h = full week

  function handleEventClick(ev: CalendarEvent, e: React.MouseEvent) {
    if (selectedEvent?.id === ev.id) { setSelectedEvent(null); return; }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const container = containerRef.current?.getBoundingClientRect();
    setPopoverPos({ x: rect.right - (container?.left ?? 0) + 8, y: rect.top - (container?.top ?? 0) });
    setSelectedEvent(ev);
  }

  const gridHeight = HOURS.length * HOUR_HEIGHT;

  return (
    <div ref={containerRef} style={{ position: "relative" }} onClick={e => {
      if (!(e.target as HTMLElement).closest("[data-event]") && !(e.target as HTMLElement).closest("[data-popover]"))
        setSelectedEvent(null);
    }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}`}</style>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: "1.25rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "#748cab", marginBottom: 4, fontWeight: 600 }}>
            📅 Calendrier Unifié
          </div>
          <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", margin: 0 }}>Agenda Exécutif</h1>
          <p style={{ color: "#748cab", fontSize: 12, marginTop: 4 }}>Outlook · Google · Teams · Jira · ClickUp</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <button onClick={prevWeek} style={navBtnStyle}>←</button>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{formatWeekLabel(monday)}</div>
          <button onClick={nextWeek} style={navBtnStyle}>→</button>
          <button onClick={goToday} style={{ ...navBtnStyle, padding: "5px 14px", fontSize: 12, color: "#3e5c76", border: "1px solid rgba(62,92,118,0.4)" }}>
            Aujourd&apos;hui
          </button>
        </div>
      </div>

      {/* ── Prochaine réunion ──────────────────────────────────────────────── */}
      {nextMeeting && (() => {
        const meta = SOURCE_META[nextMeeting.source] ?? { color: nextMeeting.color, icon: "◈", label: nextMeeting.source };
        const start = new Date(nextMeeting.start);
        const msUntil = start.getTime() - now.getTime();
        return (
          <div style={{ background: `linear-gradient(135deg, ${meta.color}12, ${meta.color}06)`, border: `1.5px solid ${meta.color}35`, borderRadius: 14, padding: "0.875rem 1.25rem", marginBottom: "1.25rem", display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: meta.color, animation: "pulse 2s infinite", flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: meta.color, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 2 }}>
                Prochaine réunion · {formatCountdown(msUntil)}
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#0d1321" }}>{nextMeeting.title}</div>
              {nextMeeting.location && <div style={{ fontSize: 11, color: "#748cab", marginTop: 1 }}>📍 {nextMeeting.location}</div>}
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: meta.color }}>
                {start.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
              </div>
              <div style={{ fontSize: 10, color: "#748cab" }}>{meta.icon} {meta.label}</div>
            </div>
            {nextMeeting.url && (
              <a href={nextMeeting.url} target="_blank" rel="noreferrer" style={{ background: meta.color, color: "#fff", borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 700, textDecoration: "none", flexShrink: 0 }}>
                Rejoindre →
              </a>
            )}
          </div>
        );
      })()}

      {/* ── KPIs de charge CEO ─────────────────────────────────────────────── */}
      {!loading && visibleEvents.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: "0.875rem", marginBottom: "1.25rem" }}>
          {/* Charge réunions */}
          <div style={kpiCardStyle}>
            <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600, marginBottom: 6 }}>Charge réunions</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: weekLoad > 60 ? "#ef4444" : weekLoad > 35 ? "#f59e0b" : "#22c55e" }}>{weekLoad}%</div>
            <div style={{ marginTop: 6, height: 4, borderRadius: 4, background: "rgba(62,92,118,0.1)", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${weekLoad}%`, borderRadius: 4, background: weekLoad > 60 ? "#ef4444" : weekLoad > 35 ? "#f59e0b" : "#22c55e", transition: "width 0.4s" }} />
            </div>
            <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>{totalHours}h{remMin > 0 ? `${remMin}min` : ""} en réunion</div>
          </div>

          {/* Jours surchargés */}
          <div style={kpiCardStyle}>
            <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600, marginBottom: 6 }}>Jours surchargés</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: overloadedDays > 2 ? "#ef4444" : overloadedDays > 0 ? "#f59e0b" : "#22c55e" }}>{overloadedDays}</div>
            <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>sur 5 jours ouvrés</div>
            <div style={{ fontSize: 11, color: overloadedDays > 0 ? "#f59e0b" : "#22c55e", fontWeight: 600, marginTop: 2 }}>
              {overloadedDays > 0 ? "⚠ +4h de réunions" : "✓ Charge équilibrée"}
            </div>
          </div>

          {/* Jours de focus */}
          <div style={kpiCardStyle}>
            <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600, marginBottom: 6 }}>Jours de focus</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: focusDays >= 2 ? "#22c55e" : focusDays === 1 ? "#f59e0b" : "#ef4444" }}>{focusDays}</div>
            <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>jours avec &lt; 2h de réunion</div>
            <div style={{ fontSize: 11, color: focusDays >= 2 ? "#22c55e" : "#ef4444", fontWeight: 600, marginTop: 2 }}>
              {focusDays >= 2 ? "✓ Bon équilibre" : "⚠ Peu de temps libre"}
            </div>
          </div>

          {/* Participants uniques */}
          <div style={kpiCardStyle}>
            <div style={{ fontSize: 10, color: "#748cab", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600, marginBottom: 6 }}>Personnes rencontrées</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#3e5c76" }}>{uniquePeople}</div>
            <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>{visibleEvents.filter(e => !e.all_day).length} réunions cette semaine</div>
          </div>
        </div>
      )}

      {/* ── Heatmap charge par jour ─────────────────────────────────────────── */}
      {!loading && visibleEvents.length > 0 && (
        <div style={{ background: "#fff", borderRadius: 12, padding: "0.875rem 1.25rem", boxShadow: "0 2px 8px rgba(13,19,33,0.05)", border: "1px solid rgba(62,92,118,0.1)", marginBottom: "1.25rem", display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", marginRight: 6 }}>Intensité</span>
          {weekDays.map((day, i) => {
            const hrs   = dayHours[i];
            const color = getDayHeatColor(hrs);
            const isToday = day.toDateString() === now.toDateString();
            return (
              <div key={i} style={{ textAlign: "center", flex: 1, minWidth: 44 }}>
                <div style={{ fontSize: 10, color: "#748cab", marginBottom: 4 }}>{DAY_NAMES_FR[i]}</div>
                <div style={{
                  height: 28, borderRadius: 8,
                  background: color,
                  border: isToday ? "2px solid #3e5c76" : "2px solid transparent",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color: hrs === 0 ? "#748cab" : "#fff" }}>
                    {hrs > 0 ? `${hrs.toFixed(1)}h` : "—"}
                  </span>
                </div>
              </div>
            );
          })}
          <div style={{ display: "flex", gap: 8, marginLeft: 8, flexShrink: 0 }}>
            {[["#22c55e", "< 2h"], ["#f59e0b", "2–4h"], ["#f97316", "4–6h"], ["#ef4444", "> 6h"]].map(([c, l]) => (
              <div key={l} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: c }} />
                <span style={{ fontSize: 10, color: "#748cab" }}>{l}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Source filters ─────────────────────────────────────────────────── */}
      {allSources.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: "1.25rem" }}>
          {allSources.map(src => {
            const meta   = SOURCE_META[src] ?? { label: src, color: "#748cab", icon: "◈" };
            const active = activeFilters.has(src);
            return (
              <button key={src} onClick={() => toggleFilter(src)} style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "5px 13px", borderRadius: 20, cursor: "pointer",
                border: `1.5px solid ${active ? meta.color : "rgba(62,92,118,0.2)"}`,
                background: active ? `${meta.color}18` : "transparent",
                color: active ? meta.color : "#748cab",
                fontSize: 12, fontWeight: active ? 600 : 400, transition: "all 0.15s",
              }}>
                <span>{meta.icon}</span>{meta.label}
                <span style={{ background: active ? meta.color : "rgba(62,92,118,0.15)", color: active ? "#fff" : "#748cab", borderRadius: 10, padding: "0 5px", fontSize: 10, fontWeight: 700 }}>
                  {events.filter(e => e.source === src).length}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Loading / Error ─────────────────────────────────────────────────── */}
      {loading && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "40vh" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ width: 32, height: 32, border: "3px solid rgba(62,92,118,0.15)", borderTop: "3px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 10px" }} />
            <p style={{ color: "#748cab", fontSize: 13 }}>Chargement du calendrier...</p>
          </div>
        </div>
      )}
      {error && (
        <div style={{ background: "#fef2f2", border: "1px solid #ef4444", borderRadius: 12, padding: "1.5rem", color: "#ef4444" }}>
          <strong>Erreur :</strong> {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {/* ── Grille calendrier ────────────────────────────────────────────── */}
          <div style={{ background: "#fff", borderRadius: 16, boxShadow: "0 2px 16px rgba(13,19,33,0.07)", border: "1px solid rgba(62,92,118,0.1)", overflow: "hidden", marginBottom: "1.5rem" }}>
            {/* Day headers */}
            <div style={{ display: "grid", gridTemplateColumns: "52px repeat(7, 1fr)", borderBottom: "2px solid rgba(62,92,118,0.1)" }}>
              <div />
              {weekDays.map((day, i) => {
                const isToday = day.toDateString() === now.toDateString();
                const hrs     = dayHours[i];
                return (
                  <div key={i} style={{ padding: "8px 6px", textAlign: "center", borderLeft: "1px solid rgba(62,92,118,0.08)" }}>
                    <div style={{ fontSize: 11, color: "#748cab", fontWeight: 500 }}>{DAY_NAMES_FR[i]}</div>
                    <div style={{
                      fontSize: 18, fontWeight: 700,
                      color: isToday ? "#fff" : "#0d1321",
                      background: isToday ? "#3e5c76" : "transparent",
                      borderRadius: isToday ? "50%" : 0,
                      width: isToday ? 32 : "auto", height: isToday ? 32 : "auto",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      margin: isToday ? "2px auto 2px" : "2px 0 2px",
                    }}>{day.getDate()}</div>
                    {hrs > 0 && (
                      <div style={{ width: "60%", height: 3, borderRadius: 3, background: getDayHeatColor(hrs), margin: "0 auto" }} />
                    )}
                  </div>
                );
              })}
            </div>

            {/* All-day row */}
            {visibleEvents.some(e => e.all_day) && (
              <div style={{ display: "grid", gridTemplateColumns: "52px repeat(7, 1fr)", borderBottom: "1px solid rgba(62,92,118,0.08)", minHeight: 32 }}>
                <div style={{ padding: "4px 6px", fontSize: 9, color: "#748cab", fontWeight: 600, textTransform: "uppercase", display: "flex", alignItems: "center" }}>Jour</div>
                {weekDays.map((_, i) => (
                  <div key={i} style={{ borderLeft: "1px solid rgba(62,92,118,0.08)", padding: "4px", display: "flex", flexDirection: "column", gap: 2 }}>
                    {eventsByDay[i].filter(e => e.all_day).map(ev => {
                      const meta = SOURCE_META[ev.source] ?? { color: ev.color };
                      return (
                        <div key={ev.id} data-event="1" onClick={e => handleEventClick(ev, e)} style={{ background: `${meta.color}20`, borderLeft: `3px solid ${meta.color}`, borderRadius: "0 4px 4px 0", padding: "2px 6px", fontSize: 11, fontWeight: 600, color: meta.color, cursor: "pointer", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {ev.title}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}

            {/* Time grid */}
            <div style={{ overflowX: "auto" }}>
              <div style={{ display: "grid", gridTemplateColumns: "52px repeat(7, 1fr)", minWidth: 600 }}>
                <div style={{ position: "relative", height: gridHeight }}>
                  {HOURS.map(h => (
                    <div key={h} style={{ position: "absolute", top: (h - GRID_START) * HOUR_HEIGHT - 8, right: 8, fontSize: 11, color: "#b0bec5", fontWeight: 500 }}>{h}h</div>
                  ))}
                </div>
                {weekDays.map((day, colIdx) => {
                  const dayEvents  = eventsByDay[colIdx].filter(e => !e.all_day);
                  const isToday    = day.toDateString() === now.toDateString();
                  const overlapMap = computeOverlapLayout(dayEvents);
                  const nowMinutes = now.getHours() * 60 + now.getMinutes();
                  const nowTop     = ((nowMinutes / 60) - GRID_START) * HOUR_HEIGHT;

                  return (
                    <div key={colIdx} style={{ position: "relative", height: gridHeight, borderLeft: "1px solid rgba(62,92,118,0.08)", background: isToday ? "rgba(62,92,118,0.02)" : "transparent" }}>
                      {HOURS.map(h => (
                        <div key={h} style={{ position: "absolute", top: (h - GRID_START) * HOUR_HEIGHT, left: 0, right: 0, borderTop: "1px solid rgba(62,92,118,0.07)" }} />
                      ))}
                      {/* Ligne "maintenant" */}
                      {isToday && nowTop >= 0 && nowTop <= gridHeight && (
                        <div style={{ position: "absolute", top: nowTop, left: 0, right: 0, height: 2, background: "#ef4444", zIndex: 10 }}>
                          <div style={{ position: "absolute", left: -4, top: -4, width: 10, height: 10, borderRadius: "50%", background: "#ef4444" }} />
                        </div>
                      )}
                      {dayEvents.map(ev => {
                        const evStart = new Date(ev.start), evEnd = new Date(ev.end);
                        const top     = eventTopPx(evStart), height = eventHeightPx(evStart, evEnd);
                        const meta    = SOURCE_META[ev.source] ?? { color: ev.color };
                        const showTime = (evEnd.getTime() - evStart.getTime()) / 60000 >= 45;
                        const isSelected = selectedEvent?.id === ev.id;
                        const { colIndex, totalCols } = overlapMap.get(ev.id) ?? { colIndex: 0, totalCols: 1 };
                        const colW = 100 / totalCols;
                        return (
                          <div key={ev.id} data-event="1" onClick={e => handleEventClick(ev, e)} style={{
                            position: "absolute", top,
                            left: `calc(${colIndex * colW}% + 2px)`,
                            width: `calc(${colW}% - 4px)`,
                            height, background: `${meta.color}18`,
                            borderLeft: `3px solid ${meta.color}`,
                            borderRadius: "0 6px 6px 0", padding: "3px 6px",
                            cursor: "pointer", overflow: "hidden",
                            boxShadow: isSelected ? `0 0 0 2px ${meta.color}60` : "none",
                            transition: "box-shadow 0.15s", zIndex: isSelected ? 5 : 2,
                          }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: meta.color, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ev.title}</div>
                            {showTime && (
                              <div style={{ fontSize: 10, color: meta.color, opacity: 0.75 }}>
                                {evStart.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })} – {evEnd.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* ── Empty state ──────────────────────────────────────────────────── */}
          {visibleEvents.length === 0 && (
            <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📅</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: "#0d1321", marginBottom: 6 }}>Aucun événement cette semaine</div>
              <div style={{ fontSize: 13 }}>Essayez une autre semaine ou vérifiez vos connexions sources</div>
            </div>
          )}

          {/* ── Alertes + Top participants ────────────────────────────────────── */}
          {visibleEvents.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: alerts.length > 0 ? "1fr 1fr" : "1fr", gap: "1.25rem", marginBottom: "1.25rem" }}>

              {/* Alertes agenda */}
              {alerts.length > 0 && (
                <div style={{ background: "#fff", borderRadius: 14, padding: "1rem 1.25rem", boxShadow: "0 2px 8px rgba(13,19,33,0.05)", border: "1px solid rgba(62,92,118,0.1)" }}>
                  <div style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12 }}>⚠ Alertes agenda</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {alerts.map((a, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 10px", borderRadius: 10, background: `${a.color}0e`, borderLeft: `3px solid ${a.color}` }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "#0d1321" }}>{a.label}</div>
                          <div style={{ fontSize: 11, color: "#748cab", marginTop: 2 }}>{a.day}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top participants */}
              {topParticipants.length > 0 && (
                <div style={{ background: "#fff", borderRadius: 14, padding: "1rem 1.25rem", boxShadow: "0 2px 8px rgba(13,19,33,0.05)", border: "1px solid rgba(62,92,118,0.1)" }}>
                  <div style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12 }}>👥 Personnes rencontrées</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {topParticipants.map((p, i) => {
                      const maxCount = topParticipants[0].count;
                      const pct = Math.round((p.count / maxCount) * 100);
                      return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <div style={{ width: 28, height: 28, borderRadius: "50%", background: `rgba(62,92,118,${0.1 + (1 - i / topParticipants.length) * 0.15})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#3e5c76", flexShrink: 0 }}>
                            {p.name.charAt(0).toUpperCase()}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                              <span style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
                              <span style={{ fontSize: 11, color: "#748cab", flexShrink: 0, marginLeft: 6 }}>{p.count}×</span>
                            </div>
                            <div style={{ height: 4, borderRadius: 4, background: "rgba(62,92,118,0.08)", overflow: "hidden" }}>
                              <div style={{ height: "100%", width: `${pct}%`, borderRadius: 4, background: "#3e5c76", transition: "width 0.4s" }} />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Footer stats ─────────────────────────────────────────────────── */}
          {visibleEvents.length > 0 && (
            <div style={{ background: "#fff", borderRadius: 14, padding: "1rem 1.5rem", boxShadow: "0 2px 8px rgba(13,19,33,0.05)", border: "1px solid rgba(62,92,118,0.1)", display: "flex", alignItems: "center", gap: "2rem", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em" }}>Total événements</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: "#0d1321" }}>{visibleEvents.length}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em" }}>Temps en réunion</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: "#3e5c76" }}>{totalHours}h{remMin > 0 ? `${remMin}min` : ""}</div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: "#748cab", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>Par source</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {Array.from(new Set(visibleEvents.map(e => e.source))).map(src => {
                    const meta  = SOURCE_META[src] ?? { label: src, color: "#748cab", icon: "◈" };
                    const count = visibleEvents.filter(e => e.source === src).length;
                    return (
                      <span key={src} style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 10px", borderRadius: 20, background: `${meta.color}15`, border: `1px solid ${meta.color}40`, fontSize: 12, fontWeight: 600, color: meta.color }}>
                        {meta.icon} {meta.label} · {count}
                      </span>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Event Popover ───────────────────────────────────────────────────── */}
      {selectedEvent && (
        <div data-popover="1" style={{ position: "absolute", top: Math.max(0, popoverPos.y), left: Math.min(popoverPos.x, (containerRef.current?.offsetWidth ?? 800) - 300), width: 280, background: "#fff", borderRadius: 14, boxShadow: "0 8px 32px rgba(13,19,33,0.18)", border: `1.5px solid ${(SOURCE_META[selectedEvent.source]?.color ?? selectedEvent.color)}40`, padding: "1rem", zIndex: 100 }}>
          {(() => {
            const meta  = SOURCE_META[selectedEvent.source] ?? { label: selectedEvent.source, color: selectedEvent.color, icon: "◈" };
            const start = new Date(selectedEvent.start), end = new Date(selectedEvent.end);
            const extra = selectedEvent.attendees.length - 3;
            return (
              <>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10 }}>
                  <div style={{ flex: 1, fontSize: 14, fontWeight: 700, color: "#0d1321", lineHeight: 1.3 }}>{selectedEvent.title}</div>
                  <span style={{ fontSize: 10, fontWeight: 700, color: meta.color, background: `${meta.color}15`, border: `1px solid ${meta.color}30`, borderRadius: 6, padding: "2px 7px", whiteSpace: "nowrap", flexShrink: 0 }}>{meta.icon} {meta.label}</span>
                </div>
                {!selectedEvent.all_day && (
                  <div style={{ fontSize: 12, color: "#748cab", marginBottom: 6, display: "flex", alignItems: "center", gap: 5 }}>
                    🕐 {start.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })} · {start.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })} – {end.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                  </div>
                )}
                {selectedEvent.location && <div style={{ fontSize: 12, color: "#748cab", marginBottom: 6 }}>📍 {selectedEvent.location}</div>}
                {selectedEvent.attendees.length > 0 && (
                  <div style={{ fontSize: 12, color: "#748cab", marginBottom: 6 }}>
                    <div style={{ marginBottom: 4 }}>👥 Participants</div>
                    <div style={{ paddingLeft: 18 }}>
                      {selectedEvent.attendees.slice(0, 3).map((a, i) => <div key={i} style={{ color: "#3e5c76", fontWeight: 500 }}>{a.name || a.email}</div>)}
                      {extra > 0 && <div style={{ color: "#748cab" }}>+{extra} autres</div>}
                    </div>
                  </div>
                )}
                {selectedEvent.description && (
                  <div style={{ fontSize: 11, color: "#748cab", borderTop: "1px solid rgba(62,92,118,0.1)", paddingTop: 8, marginTop: 4, lineHeight: 1.5 }}>
                    {selectedEvent.description.slice(0, 120)}{selectedEvent.description.length > 120 ? "…" : ""}
                  </div>
                )}
                {selectedEvent.url && (
                  <a href={selectedEvent.url} target="_blank" rel="noreferrer" style={{ display: "block", marginTop: 10, padding: "7px 14px", background: meta.color, color: "#fff", borderRadius: 8, textDecoration: "none", fontSize: 12, fontWeight: 700, textAlign: "center" }}>
                    Rejoindre →
                  </a>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

const navBtnStyle: React.CSSProperties = {
  padding: "5px 12px", borderRadius: 8, border: "1px solid rgba(62,92,118,0.25)",
  background: "transparent", color: "#3e5c76", fontSize: 14, cursor: "pointer",
  fontFamily: "inherit", transition: "all 0.15s",
};

const kpiCardStyle: React.CSSProperties = {
  background: "#fff", borderRadius: 14, padding: "1rem 1.25rem",
  boxShadow: "0 2px 8px rgba(13,19,33,0.05)", border: "1px solid rgba(62,92,118,0.1)",
};
