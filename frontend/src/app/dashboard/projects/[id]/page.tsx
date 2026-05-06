"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import API from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import ProjectOHSCard from "@/components/intelligence/ProjectOHSCard";

type Tab = "overview" | "activity" | "plans" | "teams" | "notes" | "files" | "preferences";

interface Project {
  id: string;
  name: string;
  description?: string;
  color: string;
  created_by: string;
  created_at: string;
  members: { id: number; name: string; email: string; role: string }[];
  sources: { id: number; source_type: string; config: Record<string, string> }[];
  notes_count: number;
  files_count: number;
}

interface Note {
  id: number;
  title?: string;
  content: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface ActivityItem {
  id: number;
  actor: string;
  action: string;
  detail: string;
  created_at: string;
}

const ACTION_META: Record<string, { icon: string; color: string }> = {
  created_project: { icon: "🚀", color: "#3e5c76" },
  created_note:    { icon: "📝", color: "#0891b2" },
  deleted_note:    { icon: "🗑️", color: "#ef4444" },
  uploaded_file:   { icon: "📁", color: "#16a34a" },
  linked_source:   { icon: "🔗", color: "#9333ea" },
  added_member:    { icon: "👤", color: "#ea580c" },
  removed_member:  { icon: "👤", color: "#ef4444" },
  deleted_file:    { icon: "🗑️", color: "#ef4444" },
  updated_project: { icon: "✏️", color: "#748cab" },
};

export default function ProjectPage() {
  const { id }       = useParams<{ id: string }>();
  const router       = useRouter();
  const searchParams = useSearchParams();
  const { t, locale } = useI18n();

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: "overview",    label: locale === "fr" ? "Vue d'ensemble" : "Overview", icon: "🧠" },
    { key: "activity",    label: t.proj_tab_activity, icon: "⚡" },
    { key: "plans",       label: t.proj_tab_plans,    icon: "📋" },
    { key: "teams",       label: locale === "fr" ? "Équipe" : "Team", icon: "💬" },
    { key: "notes",       label: t.proj_tab_notes,    icon: "📝" },
    { key: "files",       label: t.proj_tab_files,    icon: "📁" },
    { key: "preferences", label: t.proj_tab_prefs,    icon: "⚙️" },
  ];

  const ACTION_LABELS: Record<string, string> = {
    created_project: locale === "fr" ? "a créé le projet"     : "created the project",
    created_note:    locale === "fr" ? "a ajouté une note"    : "added a note",
    deleted_note:    locale === "fr" ? "a supprimé une note"  : "deleted a note",
    uploaded_file:   locale === "fr" ? "a uploadé un fichier" : "uploaded a file",
    linked_source:   locale === "fr" ? "a connecté une source": "connected a source",
    added_member:    locale === "fr" ? "a ajouté un membre"   : "added a member",
    removed_member:  locale === "fr" ? "a retiré un membre"   : "removed a member",
    deleted_file:    locale === "fr" ? "a supprimé un fichier": "deleted a file",
    updated_project: locale === "fr" ? "a modifié le projet"  : "updated the project",
  };

  const [tab, setTab]           = useState<Tab>("overview");
  const [project, setProject]   = useState<Project | null>(null);
  const [notes, setNotes]       = useState<Note[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading]   = useState(true);

  // Notes
  const [noteContent, setNoteContent] = useState("");
  const [noteTitle, setNoteTitle]     = useState("");
  const [savingNote, setSavingNote]   = useState(false);

  // Files
  interface ProjectFile { id: number; filename: string; source: string; size_bytes: number; mime_type: string; uploaded_by: string; uploaded_at: string; }
  const [files, setFiles]         = useState<ProjectFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver]   = useState(false);

  // Members
  const [memberName,  setMemberName]  = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole,  setMemberRole]  = useState("member");
  const [addingMember, setAddingMember] = useState(false);

  // OneDrive
  const [onedriveConnected, setOnedriveConnected] = useState(false);
  const [folders, setFolders]                     = useState<{id: string; name: string}[]>([]);
  const [loadingFolders, setLoadingFolders]        = useState(false);
  const [showFolderPicker, setShowFolderPicker]   = useState(false);

  // ClickUp
  const [clickupConnected, setClickupConnected]   = useState(false);
  const [clickupToken,     setClickupToken]        = useState("");
  const [clickupUser,      setClickupUser]         = useState("");
  const [connectingCU,     setConnectingCU]        = useState(false);
  const [cuError,          setCuError]             = useState("");

  // ClickUp list picker
  interface CUList { list_id: string; list_name: string; space_name: string; task_count: number; }
  const [cuLists,       setCuLists]       = useState<CUList[]>([]);
  const [loadingCULists, setLoadingCULists] = useState(false);
  const [showCUPicker,  setShowCUPicker]  = useState(false);

  // Plans tab
  interface Task { id: string; title: string; status: string; is_done: boolean; priority: string; assignee: string; due_date: string|null; list_name: string; url: string; tags: string[]; }
  interface PlanStats { total: number; done: number; open: number; urgent: number; blocked: number; overdue: number; progress: number; }
  interface Assignee  { name: string; total: number; done: number; urgent: number; }
  interface Signal { id: string; source: string; icon: string; title: string; excerpt: string; author: string; date: string; sentiment: string; emotion: string; url: string; keywords?: string[]; match_type?: string; rag_distance?: number; }
  interface TaskSignal { task_id: string; task_title: string; priority: string; assignee: string; signals: Signal[]; }
  const [tasks,         setTasks]         = useState<Task[]>([]);
  const [loadingTasks,  setLoadingTasks]  = useState(false);
  const [taskFilter,    setTaskFilter]    = useState<"all"|"open"|"done">("all");
  const [planStats,     setPlanStats]     = useState<PlanStats|null>(null);
  const [planSummary,   setPlanSummary]   = useState("");
  const [planAssignees, setPlanAssignees] = useState<Assignee[]>([]);
  const [loadingSummary,setLoadingSummary]= useState(false);
  const [signals,       setSignals]       = useState<TaskSignal[]>([]);
  const [loadingSignals,setLoadingSignals]= useState(false);
  const [showSignals,   setShowSignals]   = useState(true);

  // Overview
  interface OverviewData {
    sources: { clickup: {connected:boolean;config:Record<string,string>}; slack: {connected:boolean;config:Record<string,string>}; onedrive: {connected:boolean;config:Record<string,string>} };
    clickup: { total:number; done:number; open:number; urgent:number; blocked:number; overdue:number; progress:number } | null;
    clickup_brief: string;
    slack: { total:number; positive:number; negative:number; neutral:number; top_emotion:string; channel:string } | null;
    gmail: { total:number; negative:number; risk_count:number } | null;
    signals_count: number;
    climate: { label:string; color:string; icon:string; fr:string };
    risk_score: number;
  }
  const [overview,        setOverview]        = useState<OverviewData|null>(null);
  const [loadingOverview, setLoadingOverview] = useState(false);

  // Slack (Teams)
  interface SlackChannel { channel_id: string; channel_name: string; is_private: boolean; num_members: number; }
  interface SlackMessage  { id: string; author: string; content: string; timestamp: string; sentiment: string; }
  const [slackChannels,     setSlackChannels]     = useState<SlackChannel[]>([]);
  const [loadingSlackCh,    setLoadingSlackCh]    = useState(false);
  const [showSlackPicker,   setShowSlackPicker]   = useState(false);
  const [slackMessages,     setSlackMessages]     = useState<SlackMessage[]>([]);
  const [loadingSlackMsgs,  setLoadingSlackMsgs]  = useState(false);

  useEffect(() => {
    Promise.all([
      API.get(`/api/projects/${id}`),
      API.get(`/api/projects/${id}/activity`),
      API.get(`/auth/onedrive/status?project_id=${id}`),
      API.get(`/api/sources/clickup/status`),
    ]).then(([p, a, od, cu]) => {
      setProject(p.data);
      setActivity(a.data);
      setOnedriveConnected(od.data.connected);
      setClickupConnected(cu.data.connected);
    }).catch(() => router.push("/dashboard/projects"))
      .finally(() => setLoading(false));

    // If returning from OneDrive OAuth
    if (searchParams.get("onedrive") === "connected") {
      setOnedriveConnected(true);
      setTab("preferences");
    }
  }, [id]);

  useEffect(() => {
    if (tab === "overview") {
      setLoadingOverview(true);
      API.get(`/api/projects/${id}/overview`)
        .then(r => setOverview(r.data))
        .catch(() => {})
        .finally(() => setLoadingOverview(false));
    }
    if (tab === "notes")
      API.get(`/api/projects/${id}/notes`).then(r => setNotes(r.data)).catch(() => {});
    if (tab === "files")
      API.get(`/api/projects/${id}/files`).then(r => setFiles(r.data)).catch(() => {});
    if (tab === "plans") {
      setLoadingTasks(true);
      setLoadingSummary(true);
      setLoadingSignals(true);
      API.get(`/api/projects/${id}/clickup/tasks`)
        .then(r => setTasks(r.data))
        .catch(() => setTasks([]))
        .finally(() => setLoadingTasks(false));
      API.get(`/api/projects/${id}/clickup/summary`)
        .then(r => { setPlanStats(r.data.stats); setPlanSummary(r.data.summary); setPlanAssignees(r.data.assignees || []); })
        .catch(() => {})
        .finally(() => setLoadingSummary(false));
      API.get(`/api/projects/${id}/clickup/signals`)
        .then(r => setSignals(r.data))
        .catch(() => setSignals([]))
        .finally(() => setLoadingSignals(false));
    }
    if (tab === "teams") {
      setLoadingSlackMsgs(true);
      API.get(`/api/projects/${id}/slack/messages`)
        .then(r => setSlackMessages(r.data))
        .catch(() => setSlackMessages([]))
        .finally(() => setLoadingSlackMsgs(false));
    }
  }, [tab, id]);

  async function saveNote() {
    if (!noteContent.trim()) return;
    setSavingNote(true);
    try {
      const res = await API.post(`/api/projects/${id}/notes`, { title: noteTitle || null, content: noteContent });
      setNotes(prev => [res.data, ...prev]);
      setNoteContent("");
      setNoteTitle("");
    } finally {
      setSavingNote(false);
    }
  }

  async function uploadFile(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`http://localhost:8000/api/projects/${id}/files/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setFiles(prev => [data, ...prev]);
      setProject(p => p ? { ...p, files_count: p.files_count + 1 } : p);
      setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "uploaded_file", detail: file.name, created_at: new Date().toISOString() }, ...prev]);
    } finally {
      setUploading(false);
    }
  }

  async function deleteFile(fileId: number, filename: string) {
    await API.delete(`/api/projects/${id}/files/${fileId}`);
    setFiles(prev => prev.filter(f => f.id !== fileId));
    setProject(p => p ? { ...p, files_count: Math.max(0, p.files_count - 1) } : p);
    setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "deleted_file", detail: filename, created_at: new Date().toISOString() }, ...prev]);
  }

  async function addMember() {
    if (!memberName.trim() || !memberEmail.trim()) return;
    setAddingMember(true);
    try {
      const res = await API.post(`/api/projects/${id}/members`, { name: memberName, email: memberEmail, role: memberRole });
      setProject(p => p ? { ...p, members: [...p.members, res.data] } : p);
      setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "added_member", detail: `${memberName} (${memberRole})`, created_at: new Date().toISOString() }, ...prev]);
      setMemberName(""); setMemberEmail(""); setMemberRole("member");
    } finally {
      setAddingMember(false);
    }
  }

  async function removeMember(memberId: number, name: string) {
    await API.delete(`/api/projects/${id}/members/${memberId}`);
    setProject(p => p ? { ...p, members: p.members.filter(m => m.id !== memberId) } : p);
    setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "removed_member", detail: name, created_at: new Date().toISOString() }, ...prev]);
  }

  async function deleteNote(noteId: number) {
    await API.delete(`/api/projects/${id}/notes/${noteId}`);
    setNotes(prev => prev.filter(n => n.id !== noteId));
    setActivity(prev => [{
      id: Date.now(), actor: "CEO", action: "deleted_note",
      detail: notes.find(n => n.id === noteId)?.title || "Note sans titre",
      created_at: new Date().toISOString(),
    }, ...prev]);
  }

  async function connectOneDrive() {
    window.location.href = `http://localhost:8000/auth/onedrive/connect?project_id=${id}`;
  }

  async function loadFolders() {
    setLoadingFolders(true);
    try {
      const res = await API.get(`/auth/onedrive/folders?project_id=${id}`);
      setFolders(res.data);
      setShowFolderPicker(true);
    } finally {
      setLoadingFolders(false);
    }
  }

  async function selectFolder(folderId: string, folderName: string) {
    await fetch(`http://localhost:8000/auth/onedrive/link?project_id=${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId, folder_name: folderName }),
    });
    setShowFolderPicker(false);
    setProject(p => p ? { ...p, sources: [...p.sources.filter(s => s.source_type !== "onedrive"), { id: Date.now(), source_type: "onedrive", config: { folder_id: folderId, folder_name: folderName } }] } : p);
    setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "linked_source", detail: `OneDrive — ${folderName}`, created_at: new Date().toISOString() }, ...prev]);
  }

  async function loadSlackChannels() {
    setLoadingSlackCh(true);
    try {
      const r = await API.get(`/api/projects/${id}/slack/channels`);
      setSlackChannels(r.data);
      setShowSlackPicker(true);
    } catch {
      setShowSlackPicker(false);
    } finally {
      setLoadingSlackCh(false);
    }
  }

  async function selectSlackChannel(ch: SlackChannel) {
    await API.post(`/api/projects/${id}/slack/link`, { channel_id: ch.channel_id, channel_name: ch.channel_name });
    setShowSlackPicker(false);
    setProject(p => p ? {
      ...p,
      sources: [...p.sources.filter(s => s.source_type !== "slack"),
        { id: Date.now(), source_type: "slack", config: { channel_id: ch.channel_id, channel_name: ch.channel_name } }]
    } : p);
    setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "linked_source", detail: `Slack — #${ch.channel_name}`, created_at: new Date().toISOString() }, ...prev]);
    setLoadingSlackMsgs(true);
    API.get(`/api/projects/${id}/slack/messages`)
      .then(r => setSlackMessages(r.data))
      .catch(() => {})
      .finally(() => setLoadingSlackMsgs(false));
  }

  async function refreshSummary() {
    setLoadingSummary(true);
    try {
      const r = await API.get(`/api/projects/${id}/clickup/summary`);
      setPlanStats(r.data.stats);
      setPlanSummary(r.data.summary);
      setPlanAssignees(r.data.assignees || []);
    } finally {
      setLoadingSummary(false);
    }
  }

  async function loadCULists() {
    setLoadingCULists(true);
    try {
      const res = await API.get(`/api/projects/${id}/clickup/lists`);
      setCuLists(res.data);
      setShowCUPicker(true);
    } catch {
      setCuError(locale === "fr" ? "Impossible de charger les listes ClickUp." : "Failed to load ClickUp lists.");
    } finally {
      setLoadingCULists(false);
    }
  }

  async function selectCUList(list: { list_id: string; list_name: string; space_name: string }) {
    await API.post(`/api/projects/${id}/clickup/link`, list);
    setShowCUPicker(false);
    setProject(p => p ? {
      ...p,
      sources: [
        ...p.sources.filter(s => s.source_type !== "clickup"),
        { id: Date.now(), source_type: "clickup", config: { list_id: list.list_id, list_name: list.list_name, space_name: list.space_name } }
      ]
    } : p);
    setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "linked_source", detail: `ClickUp — ${list.list_name}`, created_at: new Date().toISOString() }, ...prev]);
    // Refresh tasks
    setLoadingTasks(true);
    API.get(`/api/projects/${id}/clickup/tasks`)
      .then(r => setTasks(r.data))
      .catch(() => setTasks([]))
      .finally(() => setLoadingTasks(false));
  }

  async function connectClickUp() {
    if (!clickupToken.trim()) return;
    setConnectingCU(true);
    setCuError("");
    try {
      const res = await API.post("/api/sources/clickup/connect", { api_token: clickupToken.trim() });
      setClickupConnected(true);
      setClickupUser(res.data.user || "");
      setClickupToken("");
      setActivity(prev => [{ id: Date.now(), actor: "CEO", action: "linked_source", detail: "ClickUp", created_at: new Date().toISOString() }, ...prev]);
    } catch {
      setCuError(locale === "fr" ? "Token invalide ou connexion impossible." : "Invalid token or connection failed.");
    } finally {
      setConnectingCU(false);
    }
  }

  async function disconnectClickUp() {
    await API.delete("/api/sources/clickup/disconnect");
    setClickupConnected(false);
    setClickupUser("");
  }

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", flexDirection: "column", gap: 12 }}>
      <div style={{ width: 32, height: 32, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
  if (!project) return null;

  return (
    <div style={{ maxWidth: 880, margin: "0 auto" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin   { to { transform: rotate(360deg) } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(10px) } to { opacity:1; transform:translateY(0) } }
        .tab-btn:hover { color: #0d1321 !important; }
        .note-card { transition: box-shadow 0.15s; }
        .note-card:hover { box-shadow: 0 4px 16px rgba(13,19,33,0.08) !important; }
        .del-btn { opacity: 0; transition: opacity 0.15s; }
        .note-card:hover .del-btn { opacity: 1; }
      `}</style>

      {/* Back */}
      <button
        onClick={() => router.push("/dashboard/projects")}
        style={{ background: "none", border: "none", color: "#748cab", fontSize: 13, cursor: "pointer", marginBottom: "1.25rem", display: "flex", alignItems: "center", gap: 5, padding: 0, fontFamily: "DM Sans, sans-serif" }}
      >
        {t.proj_back}
      </button>

      {/* Header card */}
      <div style={{ background: "#fff", borderRadius: 18, overflow: "hidden", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 2px 12px rgba(13,19,33,0.05)", marginBottom: "1.75rem" }}>
        <div style={{ height: 6, background: project.color }} />
        <div style={{ padding: "1.5rem 1.75rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontFamily: "DM Serif Display, serif", fontSize: 26, color: "#0d1321", margin: "0 0 6px" }}>
              {project.name}
            </h1>
            {project.description && (
              <p style={{ color: "#748cab", fontSize: 13, margin: 0, lineHeight: 1.6 }}>{project.description}</p>
            )}
          </div>
          <div style={{ display: "flex", gap: 20, flexShrink: 0 }}>
            {[
              { val: project.notes_count, label: t.proj_stat_notes + "s" },
              { val: project.files_count, label: t.proj_stat_files + "s" },
              { val: project.members.length, label: t.proj_stat_members + "s" },
            ].map(s => (
              <div key={s.label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 20, fontWeight: 800, color: "#0d1321", lineHeight: 1, fontFamily: "DM Serif Display, serif" }}>{s.val}</div>
                <div style={{ fontSize: 10, color: "#748cab", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.06em" }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, background: "#fff", borderRadius: 12, padding: "5px", border: "1px solid rgba(62,92,118,0.09)", marginBottom: "1.75rem", boxShadow: "0 1px 4px rgba(13,19,33,0.04)" }}>
        {TABS.map(t2 => (
          <button
            key={t2.key}
            className="tab-btn"
            onClick={() => setTab(t2.key)}
            style={{
              flex: 1, padding: "8px 12px",
              background: tab === t2.key ? "#1d2d44" : "transparent",
              border: "none", borderRadius: 9,
              color: tab === t2.key ? "#f0ebd8" : "#748cab",
              fontWeight: tab === t2.key ? 600 : 400,
              fontSize: 12.5, cursor: "pointer",
              fontFamily: "DM Sans, sans-serif",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              transition: "all 0.18s",
            }}
          >
              {t2.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div key={tab} style={{ animation: "fadeUp 0.2s ease" }}>

        {/* OVERVIEW */}
        {tab === "overview" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {loadingOverview ? (
              <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
                <div style={{ width: 28, height: 28, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
                <p style={{ fontSize: 13 }}>{locale === "fr" ? "Analyse en cours…" : "Analyzing project…"}</p>
              </div>
            ) : !overview ? (
              <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
                <div style={{ fontSize: 36, marginBottom: 10 }}>🧠</div>
                <p style={{ fontSize: 14 }}>{locale === "fr" ? "Impossible de charger l'aperçu." : "Could not load overview."}</p>
              </div>
            ) : (
              <>
                {/* Climate banner */}
                <div style={{ background: `${overview.climate.color}12`, border: `1.5px solid ${overview.climate.color}40`, borderRadius: 14, padding: "1rem 1.5rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 28 }}>{overview.climate.icon}</span>
                    <div>
                      <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: 1, fontFamily: "DM Sans, sans-serif" }}>
                        {locale === "fr" ? "Santé du projet" : "Project Health"}
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: overview.climate.color, fontFamily: "DM Serif Display, serif" }}>
                        {locale === "fr" ? overview.climate.fr : overview.climate.label}
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 11, color: "#748cab", fontFamily: "DM Sans, sans-serif" }}>Risk Score</div>
                    <div style={{ fontSize: 24, fontWeight: 700, color: overview.climate.color }}>{overview.risk_score}<span style={{ fontSize: 13, fontWeight: 400 }}>/100</span></div>
                  </div>
                </div>

                {/* Project OHS */}
                <ProjectOHSCard projectId={id} />

                {/* Stat cards */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.875rem" }}>
                  {/* Tasks */}
                  <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", padding: "1.1rem 1.25rem", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                    <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6, fontFamily: "DM Sans, sans-serif" }}>
                      {locale === "fr" ? "Tâches" : "Tasks"}
                    </div>
                    {overview.clickup ? (
                      <>
                        <div style={{ fontSize: 26, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>
                          {overview.clickup.done}<span style={{ fontSize: 14, color: "#748cab", fontWeight: 400 }}>/{overview.clickup.total}</span>
                        </div>
                        <div style={{ marginTop: 8, height: 4, background: "rgba(62,92,118,0.1)", borderRadius: 2 }}>
                          <div style={{ height: "100%", width: `${overview.clickup.progress}%`, background: overview.clickup.progress >= 70 ? "#22c55e" : overview.clickup.progress >= 40 ? "#f59e0b" : "#ef4444", borderRadius: 2, transition: "width 0.5s" }} />
                        </div>
                        <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>{overview.clickup.progress}% {locale === "fr" ? "terminé" : "done"}</div>
                      </>
                    ) : (
                      <div style={{ fontSize: 13, color: "#a0b4c4", marginTop: 4 }}>
                        {locale === "fr" ? "ClickUp non lié" : "ClickUp not linked"}
                      </div>
                    )}
                  </div>

                  {/* Signals */}
                  <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", padding: "1.1rem 1.25rem", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                    <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6, fontFamily: "DM Sans, sans-serif" }}>
                      {locale === "fr" ? "Signaux croisés" : "Cross Signals"}
                    </div>
                    <div style={{ fontSize: 26, fontWeight: 700, color: overview.signals_count > 0 ? "#f59e0b" : "#0d1321", fontFamily: "DM Serif Display, serif" }}>
                      {overview.signals_count}
                    </div>
                    <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                      {locale === "fr" ? "messages liés aux tâches" : "messages linked to tasks"}
                    </div>
                  </div>

                  {/* Slack mood */}
                  <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", padding: "1.1rem 1.25rem", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                    <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6, fontFamily: "DM Sans, sans-serif" }}>
                      {locale === "fr" ? "Ambiance Slack" : "Slack Mood"}
                    </div>
                    {overview.slack ? (
                      <>
                        <div style={{ fontSize: 22, fontWeight: 700, color: "#0d1321", fontFamily: "DM Serif Display, serif" }}>
                          {{ frustration:"🔥", concern:"⚠️", urgency:"⚡", satisfaction:"✅", neutral:"○" }[overview.slack.top_emotion] || "○"}
                          <span style={{ fontSize: 13, color: "#748cab", fontWeight: 400, marginLeft: 6 }}>{overview.slack.top_emotion}</span>
                        </div>
                        <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                          {overview.slack.negative}% {locale === "fr" ? "négatif" : "negative"} · {overview.slack.total} msgs
                        </div>
                      </>
                    ) : (
                      <div style={{ fontSize: 13, color: "#a0b4c4", marginTop: 4 }}>
                        {locale === "fr" ? "Slack non lié" : "Slack not linked"}
                      </div>
                    )}
                  </div>

                  {/* Gmail risk */}
                  <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", padding: "1.1rem 1.25rem", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                    <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6, fontFamily: "DM Sans, sans-serif" }}>
                      Gmail · 7j
                    </div>
                    {overview.gmail ? (
                      <>
                        <div style={{ fontSize: 26, fontWeight: 700, color: overview.gmail.risk_count > 0 ? "#ef4444" : "#0d1321", fontFamily: "DM Serif Display, serif" }}>
                          {overview.gmail.risk_count}
                          <span style={{ fontSize: 14, color: "#748cab", fontWeight: 400 }}>/{overview.gmail.total}</span>
                        </div>
                        <div style={{ fontSize: 11, color: "#748cab", marginTop: 4 }}>
                          {locale === "fr" ? "emails à risque" : "risk emails"}
                        </div>
                      </>
                    ) : (
                      <div style={{ fontSize: 13, color: "#a0b4c4", marginTop: 4 }}>
                        {locale === "fr" ? "Gmail non connecté" : "Gmail not connected"}
                      </div>
                    )}
                  </div>
                </div>

                {/* ClickUp urgent/blocked alerts */}
                {overview.clickup && (overview.clickup.urgent > 0 || overview.clickup.blocked > 0 || overview.clickup.overdue > 0) && (
                  <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", padding: "1rem 1.5rem", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", marginBottom: 10, fontFamily: "DM Sans, sans-serif" }}>
                      {locale === "fr" ? "⚠️ Points d'attention" : "⚠️ Attention Points"}
                    </div>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                      {overview.clickup.urgent > 0 && (
                        <span style={{ background: "#fef3c7", color: "#92400e", borderRadius: 8, padding: "4px 12px", fontSize: 12, fontWeight: 500 }}>
                          🔴 {overview.clickup.urgent} {locale === "fr" ? "tâche(s) urgente(s)" : "urgent task(s)"}
                        </span>
                      )}
                      {overview.clickup.blocked > 0 && (
                        <span style={{ background: "#fee2e2", color: "#991b1b", borderRadius: 8, padding: "4px 12px", fontSize: 12, fontWeight: 500 }}>
                          🚫 {overview.clickup.blocked} {locale === "fr" ? "bloquée(s)" : "blocked"}
                        </span>
                      )}
                      {overview.clickup.overdue > 0 && (
                        <span style={{ background: "#fce7f3", color: "#9d174d", borderRadius: 8, padding: "4px 12px", fontSize: 12, fontWeight: 500 }}>
                          ⏰ {overview.clickup.overdue} {locale === "fr" ? "en retard" : "overdue"}
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* AI Brief */}
                {overview.clickup_brief && (
                  <div style={{ background: "linear-gradient(135deg, #0d1321 0%, #1d2d44 100%)", borderRadius: 14, padding: "1.25rem 1.5rem", color: "#f0ebd8" }}>
                    <div style={{ fontSize: 11, color: "#748cab", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8, fontFamily: "DM Sans, sans-serif" }}>
                      🧠 {locale === "fr" ? "Résumé IA" : "AI Brief"}
                    </div>
                    <p style={{ fontSize: 13.5, lineHeight: 1.7, margin: 0, color: "#e0e8f0", fontFamily: "DM Sans, sans-serif" }}>
                      {overview.clickup_brief}
                    </p>
                  </div>
                )}

                {/* Sources status */}
                <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", padding: "1.1rem 1.5rem", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", marginBottom: 12, fontFamily: "DM Sans, sans-serif" }}>
                    {locale === "fr" ? "Sources connectées" : "Connected Sources"}
                  </div>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {[
                      { key: "clickup",  label: "ClickUp",  icon: "📋", sub: overview.sources.clickup.config?.list_name  || "" },
                      { key: "slack",    label: "Slack",    icon: "💬", sub: overview.sources.slack.config?.channel_name ? `#${overview.sources.slack.config.channel_name}` : "" },
                      { key: "onedrive", label: "OneDrive", icon: "📁", sub: overview.sources.onedrive.config?.folder_name || "" },
                    ].map(src => {
                      const connected = overview.sources[src.key as keyof typeof overview.sources].connected;
                      return (
                        <div key={src.key} style={{ display: "flex", alignItems: "center", gap: 8, background: connected ? "rgba(34,197,94,0.07)" : "rgba(62,92,118,0.05)", border: `1px solid ${connected ? "rgba(34,197,94,0.25)" : "rgba(62,92,118,0.1)"}`, borderRadius: 10, padding: "6px 14px" }}>
                          <span style={{ fontSize: 15 }}>{src.icon}</span>
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 600, color: connected ? "#166534" : "#748cab" }}>{src.label}</div>
                            {src.sub && <div style={{ fontSize: 10, color: "#748cab" }}>{src.sub}</div>}
                            {!connected && <div style={{ fontSize: 10, color: "#a0b4c4" }}>{locale === "fr" ? "Non lié" : "Not linked"}</div>}
                          </div>
                          <span style={{ fontSize: 10, marginLeft: 4 }}>{connected ? "✅" : "○"}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ACTIVITY */}
        {tab === "activity" && (
          <div style={{ background: "#fff", borderRadius: 16, border: "1px solid rgba(62,92,118,0.09)", overflow: "hidden", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
            {activity.length === 0 ? (
              <div style={{ textAlign: "center", padding: "3rem", color: "#748cab" }}>
                <div style={{ fontSize: 36, marginBottom: 10 }}>⚡</div>
                <p style={{ fontSize: 14 }}>{t.proj_act_empty}</p>
              </div>
            ) : (
              activity.map((a, idx) => {
                const meta = ACTION_META[a.action] ?? { icon: "·", color: "#748cab" };
                return (
                  <div key={a.id} style={{ display: "flex", alignItems: "flex-start", gap: 14, padding: "14px 20px", borderBottom: idx < activity.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none" }}>
                    <div style={{ width: 34, height: 34, borderRadius: "50%", background: `${meta.color}14`, border: `1.5px solid ${meta.color}30`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, flexShrink: 0 }}>
                      {meta.icon}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, color: "#0d1321" }}>
                        <span style={{ fontWeight: 700 }}>{a.actor}</span>
                        <span style={{ color: "#748cab" }}> {ACTION_LABELS[a.action] ?? a.action}</span>
                        {a.detail && <span style={{ color: "#748cab" }}> — <span style={{ fontStyle: "italic" }}>{a.detail}</span></span>}
                      </div>
                      <div style={{ fontSize: 11, color: "#a0b4c4", marginTop: 3 }}>
                        {new Date(a.created_at).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* PLANS */}
        {tab === "plans" && (() => {
          const linkedList = project?.sources.find(s => s.source_type === "clickup");
          const PRIORITY_COLOR: Record<string, string> = { Urgent: "#ef4444", High: "#f97316", Normal: "#3e5c76", Low: "#748cab" };
          const filtered = tasks.filter(tk =>
            taskFilter === "all" ? true : taskFilter === "done" ? tk.is_done : !tk.is_done
          );

          if (!clickupConnected) return (
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid rgba(62,92,118,0.09)", padding: "4rem 2rem", textAlign: "center", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
              <div style={{ fontSize: 48, marginBottom: "1rem" }}>✅</div>
              <p style={{ fontSize: 16, fontWeight: 700, color: "#0d1321", marginBottom: 8, fontFamily: "DM Serif Display, serif" }}>
                {locale === "fr" ? "ClickUp non connecté" : "ClickUp not connected"}
              </p>
              <p style={{ fontSize: 13, color: "#748cab", maxWidth: 320, margin: "0 auto 1.5rem" }}>
                {locale === "fr" ? "Connectez ClickUp dans l'onglet Préférences pour voir les tâches ici." : "Connect ClickUp in the Preferences tab to see tasks here."}
              </p>
              <button onClick={() => setTab("preferences")}
                style={{ background: "#7B68EE", color: "#fff", border: "none", borderRadius: 9, padding: "10px 24px", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                {locale === "fr" ? "Aller aux préférences" : "Go to Preferences"}
              </button>
            </div>
          );

          if (!linkedList) return (
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid rgba(62,92,118,0.09)", padding: "4rem 2rem", textAlign: "center", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
              <div style={{ fontSize: 48, marginBottom: "1rem" }}>📋</div>
              <p style={{ fontSize: 16, fontWeight: 700, color: "#0d1321", marginBottom: 8, fontFamily: "DM Serif Display, serif" }}>
                {locale === "fr" ? "Aucune liste ClickUp liée" : "No ClickUp list linked"}
              </p>
              <p style={{ fontSize: 13, color: "#748cab", maxWidth: 320, margin: "0 auto 1.5rem" }}>
                {locale === "fr" ? "Choisissez une liste ClickUp dans Préférences pour afficher les tâches." : "Choose a ClickUp list in Preferences to display tasks here."}
              </p>
              <button onClick={() => setTab("preferences")}
                style={{ background: "#7B68EE", color: "#fff", border: "none", borderRadius: 9, padding: "10px 24px", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                {locale === "fr" ? "Lier une liste" : "Link a list"}
              </button>
            </div>
          );

          return (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>

              {/* ── AI Summary ── */}
              <div style={{ background: "linear-gradient(135deg, #1d2d44 0%, #3e5c76 100%)", borderRadius: 16, padding: "1.4rem 1.6rem", color: "#f0ebd8", position: "relative", overflow: "hidden" }}>
                <div style={{ position: "absolute", top: -20, right: -20, width: 100, height: 100, borderRadius: "50%", background: "rgba(255,255,255,0.04)" }} />
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <span style={{ fontSize: 16 }}>🤖</span>
                    <span style={{ fontSize: 12, fontWeight: 700, opacity: 0.7, letterSpacing: 1, textTransform: "uppercase" }}>
                      {locale === "fr" ? "Résumé IA" : "AI Brief"}
                    </span>
                  </div>
                  <button onClick={refreshSummary} disabled={loadingSummary}
                    style={{ background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.15)", color: "#f0ebd8", borderRadius: 8, padding: "4px 12px", fontSize: 11, cursor: "pointer", fontFamily: "DM Sans, sans-serif", flexShrink: 0 }}>
                    {loadingSummary ? "⏳" : "↻ " + (locale === "fr" ? "Actualiser" : "Refresh")}
                  </button>
                </div>
                {loadingSummary ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, opacity: 0.7 }}>
                    <div style={{ width: 16, height: 16, border: "2px solid rgba(240,235,216,0.3)", borderTop: "2px solid #f0ebd8", borderRadius: "50%", animation: "spin 0.8s linear infinite", flexShrink: 0 }} />
                    <span style={{ fontSize: 13 }}>{locale === "fr" ? "Génération du résumé..." : "Generating summary..."}</span>
                  </div>
                ) : (
                  <p style={{ fontSize: 13.5, lineHeight: 1.75, margin: 0, opacity: 0.92 }}>
                    {planSummary || (locale === "fr" ? "Résumé indisponible." : "Summary unavailable.")}
                  </p>
                )}
              </div>

              {/* ── Stats cards ── */}
              {planStats && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                  {[
                    { label: locale === "fr" ? "Tâches" : "Tasks",      value: planStats.total,    icon: "📋", color: "#3e5c76",  sub: `${planStats.progress}% terminé` },
                    { label: locale === "fr" ? "Urgentes" : "Urgent",   value: planStats.urgent,   icon: "🔴", color: "#ef4444",  sub: locale === "fr" ? "en attente" : "pending" },
                    { label: locale === "fr" ? "Bloquées" : "Blocked",  value: planStats.blocked,  icon: "⚠️", color: "#f97316",  sub: locale === "fr" ? "≥5j sans update" : "≥5d no update" },
                    { label: locale === "fr" ? "En retard" : "Overdue", value: planStats.overdue,  icon: "📅", color: "#9333ea",  sub: locale === "fr" ? "date dépassée" : "past due date" },
                  ].map(s => (
                    <div key={s.label} style={{ background: "#fff", borderRadius: 14, padding: "1rem", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 1px 4px rgba(13,19,33,0.04)", position: "relative", overflow: "hidden" }}>
                      <div style={{ position: "absolute", top: 10, right: 12, fontSize: 20, opacity: 0.15 }}>{s.icon}</div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: s.value > 0 ? s.color : "#a0b4c4", lineHeight: 1, fontFamily: "DM Serif Display, serif" }}>{s.value}</div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#0d1321", marginTop: 4 }}>{s.label}</div>
                      <div style={{ fontSize: 10, color: "#a0b4c4", marginTop: 2 }}>{s.sub}</div>
                      {s.value > 0 && (
                        <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: `${s.color}30` }}>
                          <div style={{ height: "100%", width: `${Math.min(100, (s.value / Math.max(planStats.total, 1)) * 100)}%`, background: s.color, borderRadius: 2 }} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* ── Progress bar ── */}
              {planStats && (
                <div style={{ background: "#fff", borderRadius: 12, padding: "12px 16px", border: "1px solid rgba(62,92,118,0.09)", display: "flex", alignItems: "center", gap: 14 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#0d1321", flexShrink: 0 }}>
                    {locale === "fr" ? "Avancement" : "Progress"}
                  </span>
                  <div style={{ flex: 1, height: 8, background: "rgba(62,92,118,0.08)", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${planStats.progress}%`, background: planStats.progress >= 75 ? "#16a34a" : planStats.progress >= 40 ? "#3e5c76" : "#f97316", borderRadius: 4, transition: "width 0.6s ease" }} />
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 800, color: "#0d1321", flexShrink: 0 }}>{planStats.progress}%</span>
                  <span style={{ fontSize: 11, color: "#748cab", flexShrink: 0 }}>{planStats.done}/{planStats.total}</span>
                </div>
              )}

              {/* ── Assignees ── */}
              {planAssignees.length > 0 && (
                <div style={{ background: "#fff", borderRadius: 14, padding: "1rem 1.25rem", border: "1px solid rgba(62,92,118,0.09)" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#748cab", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                    {locale === "fr" ? "Par membre" : "By member"}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {planAssignees.map(a => (
                      <div key={a.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{ width: 28, height: 28, borderRadius: "50%", background: "#1d2d44", color: "#f0ebd8", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
                          {a.name[0]?.toUpperCase()}
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", width: 100, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                        <div style={{ flex: 1, height: 6, background: "rgba(62,92,118,0.08)", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ height: "100%", width: `${a.total > 0 ? (a.done / a.total) * 100 : 0}%`, background: "#3e5c76", borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: 11, color: "#748cab", flexShrink: 0 }}>{a.done}/{a.total}</span>
                        {a.urgent > 0 && <span style={{ fontSize: 10, color: "#ef4444", fontWeight: 700, flexShrink: 0 }}>🔴 {a.urgent}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Signaux croisés ── */}
              <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", overflow: "hidden" }}>
                  <div
                    onClick={() => setShowSignals(v => !v)}
                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", cursor: "pointer", borderBottom: showSignals ? "1px solid rgba(62,92,118,0.07)" : "none" }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 14 }}>🔗</span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>
                        {locale === "fr" ? "Signaux croisés" : "Cross Signals"}
                      </span>
                      {!loadingSignals && (() => {
                        const total = signals.reduce((acc, s) => acc + s.signals.length, 0);
                        return (
                          <span style={{ fontSize: 11, background: total > 0 ? "rgba(62,92,118,0.08)" : "rgba(116,140,171,0.07)", color: total > 0 ? "#3e5c76" : "#a0b4c4", borderRadius: 10, padding: "1px 8px", fontWeight: 600 }}>
                            {total > 0
                              ? `${total} ${locale === "fr" ? "liens Gmail/Slack" : "Gmail/Slack links"}`
                              : (locale === "fr" ? "Aucun signal" : "No signals")}
                          </span>
                        );
                      })()}
                    </div>
                    <span style={{ fontSize: 11, color: "#748cab" }}>{showSignals ? "▲" : "▼"}</span>
                  </div>

                  {showSignals && (
                    <div>
                      {loadingSignals ? (
                        <div style={{ padding: "1rem", display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{ width: 16, height: 16, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                          <span style={{ fontSize: 12, color: "#748cab" }}>{locale === "fr" ? "Analyse des emails..." : "Analysing emails..."}</span>
                        </div>
                      ) : signals.length === 0 ? (
                        <div style={{ padding: "1.25rem 1rem", textAlign: "center" }}>
                          <p style={{ fontSize: 12, color: "#748cab", margin: "0 0 4px" }}>
                            {locale === "fr"
                              ? "Aucun signal trouvé — InsightFlow utilise la recherche sémantique pour relier tes emails Gmail et messages Slack à tes tâches ClickUp."
                              : "No signals found — InsightFlow uses semantic search to link Gmail emails and Slack messages to your ClickUp tasks."}
                          </p>
                          <p style={{ fontSize: 11, color: "#a0b4c4", margin: 0 }}>
                            {locale === "fr"
                              ? "Les titres de tâches trop courts ou génériques (ex: 'Task 1') ne génèrent pas de match."
                              : "Very short or generic task titles (e.g. 'Task 1') won't generate matches."}
                          </p>
                        </div>
                      ) : signals.map((sig, si) => {
                        const PRIORITY_COLOR: Record<string,string> = { Urgent:"#ef4444", High:"#f97316", Normal:"#3e5c76", Low:"#748cab" };
                        return (
                          <div key={sig.task_id} style={{ borderBottom: si < signals.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none" }}>
                            {/* Task header */}
                            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px 6px", background: "rgba(62,92,118,0.02)" }}>
                              <span style={{ fontSize: 11, fontWeight: 700, color: PRIORITY_COLOR[sig.priority] || "#3e5c76", background: `${PRIORITY_COLOR[sig.priority] || "#3e5c76"}14`, borderRadius: 5, padding: "1px 7px" }}>{sig.priority}</span>
                              <span style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>✅ {sig.task_title}</span>
                              {sig.assignee && <span style={{ fontSize: 11, color: "#748cab" }}>👤 {sig.assignee}</span>}
                            </div>
                            {/* Linked messages */}
                            {sig.signals.map((s, mi) => (
                              <div key={s.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 16px 8px 28px", borderTop: "1px solid rgba(62,92,118,0.04)" }}>
                                <span style={{ fontSize: 14, flexShrink: 0 }}>{s.icon}</span>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                  <div style={{ fontSize: 12, fontWeight: 600, color: "#0d1321", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {s.url ? <a href={s.url} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>{s.title}</a> : s.title}
                                  </div>
                                  {s.excerpt && s.excerpt !== s.title && (
                                    <div style={{ fontSize: 12, color: "#374151", marginTop: 3, lineHeight: 1.5, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                      {s.excerpt}
                                    </div>
                                  )}
                                  <div style={{ fontSize: 11, color: "#a0b4c4", display: "flex", gap: 8, marginTop: 3, flexWrap: "wrap" }}>
                                    <span>👤 {s.author}</span>
                                    <span>{new Date(s.date).toLocaleDateString(locale === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short" })}</span>
                                    {s.sentiment && (() => {
                                      const SENT_COLOR: Record<string,string> = { positive: "#16a34a", negative: "#ef4444", neutral: "#748cab" };
                                      const SENT_LABEL: Record<string,string> = { positive: "😊 positif", negative: "😟 négatif", neutral: "😐 neutre" };
                                      const EMOTION_ICON: Record<string,string> = {
                                        joy: "😄", anger: "😡", sadness: "😢", fear: "😨",
                                        surprise: "😲", disgust: "🤢", love: "❤️", neutral: "😐",
                                        joie: "😄", colère: "😡", tristesse: "😢", peur: "😨",
                                      };
                                      return (
                                        <>
                                          <span style={{ color: SENT_COLOR[s.sentiment.toLowerCase()] || "#748cab", fontWeight: 600 }}>
                                            {SENT_LABEL[s.sentiment.toLowerCase()] || s.sentiment}
                                          </span>
                                          {s.emotion && s.emotion.toLowerCase() !== "neutral" && s.emotion.toLowerCase() !== s.sentiment.toLowerCase() && (
                                            <span style={{ color: "#748cab" }}>
                                              {EMOTION_ICON[s.emotion.toLowerCase()] || "💭"} {s.emotion}
                                            </span>
                                          )}
                                        </>
                                      );
                                    })()}
                                    {s.match_type === "semantic" && s.rag_distance !== undefined && (
                                      <span style={{
                                        fontSize: 10, fontWeight: 600,
                                        color: "#6366f1",
                                        background: "rgba(99,102,241,0.08)",
                                        borderRadius: 4, padding: "1px 6px",
                                      }}>
                                        🔮 {locale === "fr" ? "sémantique" : "semantic"} {Math.round((1 - s.rag_distance / 2) * 100)}%
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  )}
              </div>

              {/* ── Header (list name + filters) ── */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#0d1321" }}>
                    ✅ {linkedList.config.list_name}
                  </span>
                  {linkedList.config.space_name && (
                    <span style={{ fontSize: 11, color: "#748cab", marginLeft: 8 }}>{linkedList.config.space_name}</span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {(["all", "open", "done"] as const).map(f => (
                    <button key={f} onClick={() => setTaskFilter(f)}
                      style={{ padding: "5px 14px", borderRadius: 20, border: "1.5px solid", fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif", transition: "all 0.15s",
                        background:   taskFilter === f ? "#1d2d44" : "transparent",
                        color:        taskFilter === f ? "#f0ebd8" : "#748cab",
                        borderColor:  taskFilter === f ? "#1d2d44" : "rgba(62,92,118,0.2)",
                      }}>
                      {f === "all" ? (locale === "fr" ? "Tout" : "All") : f === "open" ? (locale === "fr" ? "En cours" : "Open") : (locale === "fr" ? "Terminé" : "Done")}
                      {f !== "all" && (
                        <span style={{ marginLeft: 5, opacity: 0.7 }}>
                          {f === "open" ? tasks.filter(tk => !tk.is_done).length : tasks.filter(tk => tk.is_done).length}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tasks */}
              {loadingTasks ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem", gap: 10 }}>
                  <div style={{ width: 24, height: 24, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #7B68EE", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                  <span style={{ fontSize: 13, color: "#748cab" }}>{locale === "fr" ? "Chargement des tâches..." : "Loading tasks..."}</span>
                </div>
              ) : filtered.length === 0 ? (
                <div style={{ background: "#fff", borderRadius: 16, border: "1px dashed rgba(62,92,118,0.15)", padding: "3rem", textAlign: "center" }}>
                  <p style={{ fontSize: 13, color: "#748cab" }}>
                    {locale === "fr" ? "Aucune tâche trouvée." : "No tasks found."}
                  </p>
                </div>
              ) : (
                <div style={{ background: "#fff", borderRadius: 16, border: "1px solid rgba(62,92,118,0.09)", overflow: "hidden", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
                  {filtered.map((tk, idx) => (
                    <div key={tk.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderBottom: idx < filtered.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none", transition: "background 0.1s" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "#fafbfc")}
                      onMouseLeave={e => (e.currentTarget.style.background = "")}>

                      {/* Done indicator */}
                      <div style={{ width: 18, height: 18, borderRadius: "50%", border: `2px solid ${tk.is_done ? "#16a34a" : "rgba(62,92,118,0.3)"}`, background: tk.is_done ? "#16a34a" : "transparent", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        {tk.is_done && <span style={{ color: "#fff", fontSize: 10, lineHeight: 1 }}>✓</span>}
                      </div>

                      {/* Title */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: tk.is_done ? "#9ca3af" : "#0d1321", textDecoration: tk.is_done ? "line-through" : "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {tk.url ? <a href={tk.url} target="_blank" rel="noreferrer" style={{ color: "inherit", textDecoration: "inherit" }}>{tk.title}</a> : tk.title}
                        </div>
                        <div style={{ fontSize: 11, color: "#a0b4c4", marginTop: 2, display: "flex", gap: 8 }}>
                          {tk.assignee && <span>👤 {tk.assignee}</span>}
                          {tk.due_date && <span>📅 {new Date(tk.due_date).toLocaleDateString(locale === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short" })}</span>}
                        </div>
                      </div>

                      {/* Priority badge */}
                      <span style={{ fontSize: 11, fontWeight: 700, color: PRIORITY_COLOR[tk.priority] || "#748cab", background: `${PRIORITY_COLOR[tk.priority] || "#748cab"}14`, borderRadius: 6, padding: "2px 8px", flexShrink: 0 }}>
                        {tk.priority}
                      </span>

                      {/* Status badge */}
                      <span style={{ fontSize: 11, background: "rgba(62,92,118,0.07)", color: "#3e5c76", borderRadius: 6, padding: "2px 8px", fontWeight: 600, flexShrink: 0, maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {tk.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}

            </div>
          );
        })()}

        {/* TEAMS */}
        {tab === "teams" && (() => {
          const linkedSlack = project?.sources.find(s => s.source_type === "slack");
          const SENTIMENT_COLOR: Record<string,string> = { positive: "#16a34a", negative: "#ef4444", neutral: "#748cab" };

          return (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {/* Channel header */}
              <div style={{ background: "#fff", borderRadius: 14, padding: "1rem 1.25rem", border: "1px solid rgba(62,92,118,0.09)", display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 22 }}>💬</span>
                <div style={{ flex: 1 }}>
                  {linkedSlack?.config?.channel_name ? (
                    <>
                      <span style={{ fontSize: 14, fontWeight: 700, color: "#0d1321" }}>#{linkedSlack.config.channel_name}</span>
                      <span style={{ fontSize: 11, color: "#748cab", marginLeft: 8 }}>Slack</span>
                    </>
                  ) : (
                    <span style={{ fontSize: 13, color: "#748cab" }}>
                      {locale === "fr" ? "Aucun canal Slack lié" : "No Slack channel linked"}
                    </span>
                  )}
                </div>
                <button onClick={loadSlackChannels} disabled={loadingSlackCh}
                  style={{ padding: "6px 14px", background: "#4A154B", color: "#fff", border: "none", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                  {loadingSlackCh ? "..." : linkedSlack ? (locale === "fr" ? "Changer" : "Change") : (locale === "fr" ? "Lier un canal" : "Link channel")}
                </button>
              </div>

              {/* Channel picker */}
              {showSlackPicker && slackChannels.length > 0 && (
                <div style={{ background: "#fff", borderRadius: 14, border: "1px solid rgba(62,92,118,0.09)", overflow: "hidden", maxHeight: 250, overflowY: "auto" }}>
                  {slackChannels.map(ch => (
                    <div key={ch.channel_id} onClick={() => selectSlackChannel(ch)}
                      style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", borderBottom: "1px solid rgba(62,92,118,0.06)", cursor: "pointer" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "#faf5ff")}
                      onMouseLeave={e => (e.currentTarget.style.background = "")}>
                      <span style={{ fontSize: 14 }}>{ch.is_private ? "🔒" : "💬"}</span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", flex: 1 }}>#{ch.channel_name}</span>
                      <span style={{ fontSize: 11, color: "#748cab" }}>{ch.num_members} membres</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Messages */}
              {linkedSlack && (
                loadingSlackMsgs ? (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem", gap: 10 }}>
                    <div style={{ width: 24, height: 24, border: "2px solid rgba(74,21,75,0.15)", borderTop: "2px solid #4A154B", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                    <span style={{ fontSize: 13, color: "#748cab" }}>{locale === "fr" ? "Chargement des messages..." : "Loading messages..."}</span>
                  </div>
                ) : slackMessages.length === 0 ? (
                  <div style={{ background: "#fff", borderRadius: 14, border: "1px dashed rgba(62,92,118,0.15)", padding: "3rem", textAlign: "center" }}>
                    <div style={{ fontSize: 36, marginBottom: 8 }}>💬</div>
                    <p style={{ fontSize: 13, color: "#748cab" }}>
                      {locale === "fr" ? "Aucun message trouvé pour ce canal." : "No messages found for this channel."}
                    </p>
                  </div>
                ) : (
                  <div style={{ background: "#fff", borderRadius: 16, border: "1px solid rgba(62,92,118,0.09)", overflow: "hidden" }}>
                    {slackMessages.map((m, idx) => (
                      <div key={m.id} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 16px", borderBottom: idx < slackMessages.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none" }}>
                        <div style={{ width: 32, height: 32, borderRadius: "50%", background: "#4A154B", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                          {(m.author || "?")[0]?.toUpperCase()}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "#0d1321" }}>{m.author}</span>
                            <span style={{ fontSize: 11, color: "#a0b4c4" }}>
                              {new Date(m.timestamp).toLocaleString(locale === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                            </span>
                            {m.sentiment && (
                              <span style={{ fontSize: 10, color: SENTIMENT_COLOR[m.sentiment] || "#748cab", fontWeight: 600 }}>● {m.sentiment}</span>
                            )}
                          </div>
                          <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.6 }}>{m.content}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          );
        })()}

        {/* NOTES */}
        {tab === "notes" && (
          <div>
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.4rem", border: "1px solid rgba(62,92,118,0.09)", marginBottom: "1.25rem", boxShadow: "0 2px 8px rgba(13,19,33,0.04)" }}>
              <input
                value={noteTitle}
                onChange={e => setNoteTitle(e.target.value)}
                placeholder={t.proj_note_title_ph}
                style={{ width: "100%", border: "none", borderBottom: "1.5px solid rgba(62,92,118,0.1)", padding: "4px 0 10px", fontSize: 14, fontWeight: 600, fontFamily: "DM Sans, sans-serif", outline: "none", marginBottom: 12, background: "transparent", color: "#0d1321" }}
              />
              <textarea
                value={noteContent}
                onChange={e => setNoteContent(e.target.value)}
                placeholder={t.proj_note_content_ph}
                rows={4}
                style={{ width: "100%", border: "none", fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none", resize: "vertical", background: "transparent", color: "#374151", lineHeight: 1.7 }}
              />
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(62,92,118,0.07)" }}>
                <span style={{ fontSize: 11, color: "#a0b4c4" }}>{t.proj_note_chars(noteContent.length)}</span>
                <button
                  onClick={saveNote}
                  disabled={savingNote || !noteContent.trim()}
                  style={{ background: noteContent.trim() ? "linear-gradient(135deg, #1d2d44, #3e5c76)" : "#e5e7eb", color: noteContent.trim() ? "#f0ebd8" : "#9ca3af", border: "none", borderRadius: 9, padding: "8px 22px", fontSize: 13, fontWeight: 600, cursor: noteContent.trim() ? "pointer" : "not-allowed", fontFamily: "DM Sans, sans-serif" }}
                >
                  {savingNote ? t.proj_note_saving : t.proj_note_add}
                </button>
              </div>
            </div>

            {notes.length === 0 ? (
              <div style={{ textAlign: "center", padding: "2.5rem", color: "#748cab", background: "#fff", borderRadius: 16, border: "1px dashed rgba(62,92,118,0.15)" }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📝</div>
                <p style={{ fontSize: 14 }}>{t.proj_note_empty}</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {notes.map(n => (
                  <div key={n.id} className="note-card" style={{ background: "#fff", borderRadius: 14, padding: "1.1rem 1.3rem", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 1px 4px rgba(13,19,33,0.04)", position: "relative" }}>
                    {n.title && <div style={{ fontWeight: 700, fontSize: 14, color: "#0d1321", marginBottom: 6 }}>{n.title}</div>}
                    <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{n.content}</div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, paddingTop: 10, borderTop: "1px solid rgba(62,92,118,0.06)" }}>
                      <span style={{ fontSize: 11, color: "#a0b4c4" }}>
                        {n.created_by} · {new Date(n.created_at).toLocaleDateString(locale === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short", year: "numeric" })}
                      </span>
                      <button className="del-btn" onClick={() => deleteNote(n.id)} style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444", fontSize: 11, cursor: "pointer", borderRadius: 6, padding: "3px 10px", fontFamily: "DM Sans, sans-serif", fontWeight: 600 }}>
                        {t.proj_note_delete}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* FILES */}
        {tab === "files" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) uploadFile(f); }}
              onClick={() => { const inp = document.createElement("input"); inp.type = "file"; inp.onchange = (e) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) uploadFile(f); }; inp.click(); }}
              style={{
                border: `2px dashed ${dragOver ? "#3e5c76" : "rgba(62,92,118,0.25)"}`,
                borderRadius: 16, padding: "2.5rem", textAlign: "center",
                background: dragOver ? "rgba(62,92,118,0.04)" : "#fff",
                cursor: "pointer", transition: "all 0.2s",
              }}
            >
              {uploading ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 28, height: 28, border: "2px solid rgba(62,92,118,0.15)", borderTop: "2px solid #3e5c76", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                  <p style={{ fontSize: 13, color: "#748cab" }}>{t.proj_file_uploading}</p>
                </div>
              ) : (
                <>
                  <div style={{ fontSize: 36, marginBottom: 10 }}>📁</div>
                  <p style={{ fontSize: 14, color: "#3e5c76", fontWeight: 600 }}>{t.proj_file_upload}</p>
                  <p style={{ fontSize: 12, color: "#a0b4c4", marginTop: 4 }}>PDF, Word, Excel, images...</p>
                </>
              )}
            </div>

            {/* Files list */}
            {files.length === 0 ? (
              <p style={{ fontSize: 13, color: "#748cab", textAlign: "center", padding: "1rem" }}>{t.proj_file_empty}</p>
            ) : (
              <div style={{ background: "#fff", borderRadius: 16, border: "1px solid rgba(62,92,118,0.09)", overflow: "hidden" }}>
                {files.map((f, idx) => (
                  <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderBottom: idx < files.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none" }}>
                    <span style={{ fontSize: 22, flexShrink: 0 }}>
                      {f.mime_type?.includes("pdf") ? "📄" : f.mime_type?.includes("image") ? "🖼️" : f.mime_type?.includes("sheet") || f.mime_type?.includes("excel") ? "📊" : f.mime_type?.includes("word") ? "📝" : "📎"}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{f.filename}</div>
                      <div style={{ fontSize: 11, color: "#a0b4c4", marginTop: 2 }}>
                        {t.proj_file_size(f.size_bytes)} · {new Date(f.uploaded_at).toLocaleDateString(locale === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short" })}
                      </div>
                    </div>
                    <button onClick={() => deleteFile(f.id, f.filename)} style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444", fontSize: 11, cursor: "pointer", borderRadius: 6, padding: "3px 10px", fontFamily: "DM Sans, sans-serif", fontWeight: 600, flexShrink: 0 }}>
                      {t.proj_file_delete}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* PREFERENCES */}
        {tab === "preferences" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.4rem", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0d1321", marginBottom: "1rem" }}>
                {t.proj_members_title} <span style={{ color: "#748cab", fontWeight: 400 }}>({project.members.length})</span>
              </h3>

              {/* Add member form */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: 8, marginBottom: "1rem", alignItems: "center" }}>
                <input value={memberName} onChange={e => setMemberName(e.target.value)} placeholder={t.proj_member_name_ph}
                  style={{ padding: "8px 12px", border: "1.5px solid rgba(62,92,118,0.18)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none" }} />
                <input value={memberEmail} onChange={e => setMemberEmail(e.target.value)} placeholder={t.proj_member_email_ph} type="email"
                  style={{ padding: "8px 12px", border: "1.5px solid rgba(62,92,118,0.18)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none" }} />
                <select value={memberRole} onChange={e => setMemberRole(e.target.value)}
                  style={{ padding: "8px 10px", border: "1.5px solid rgba(62,92,118,0.18)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none", background: "#fff" }}>
                  <option value="member">Member</option>
                  <option value="owner">Owner</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button onClick={addMember} disabled={addingMember || !memberName.trim() || !memberEmail.trim()}
                  style={{ padding: "8px 16px", background: memberName.trim() && memberEmail.trim() ? "#1d2d44" : "#e5e7eb", color: memberName.trim() && memberEmail.trim() ? "#f0ebd8" : "#9ca3af", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif", whiteSpace: "nowrap" }}>
                  {addingMember ? "..." : "+ " + t.proj_member_add}
                </button>
              </div>

              {/* Members list */}
              {project.members.length === 0 ? (
                <p style={{ fontSize: 13, color: "#748cab" }}>{t.proj_members_empty}</p>
              ) : (
                project.members.map((m, idx) => (
                  <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: idx < project.members.length - 1 ? "1px solid rgba(62,92,118,0.06)" : "none" }}>
                    <div style={{ width: 34, height: 34, borderRadius: "50%", background: "#1d2d44", color: "#f0ebd8", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
                      {m.name?.[0]?.toUpperCase()}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{m.name}</div>
                      <div style={{ fontSize: 11, color: "#748cab" }}>{m.email}</div>
                    </div>
                    <span style={{ fontSize: 11, background: "rgba(62,92,118,0.07)", color: "#3e5c76", borderRadius: 6, padding: "3px 10px", fontWeight: 600 }}>{m.role}</span>
                    <button onClick={() => removeMember(m.id, m.name)} style={{ background: "none", border: "none", color: "#ef4444", fontSize: 12, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                      {t.proj_member_remove}
                    </button>
                  </div>
                ))
              )}
            </div>

            {/* OneDrive */}
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.4rem", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: "1rem" }}>
                <span style={{ fontSize: 24 }}>📁</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#0d1321" }}>OneDrive</div>
                  <div style={{ fontSize: 12, color: "#748cab" }}>Microsoft — Fichiers & Documents</div>
                </div>
                {onedriveConnected ? (
                  <span style={{ fontSize: 11, background: "rgba(34,197,94,0.08)", color: "#16a34a", borderRadius: 6, padding: "3px 10px", fontWeight: 600 }}>
                    {t.proj_sources_active}
                  </span>
                ) : (
                  <button onClick={connectOneDrive}
                    style={{ background: "#0078D4", color: "#fff", border: "none", borderRadius: 8, padding: "7px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                    Connecter
                  </button>
                )}
              </div>

              {/* Folder picker */}
              {onedriveConnected && (
                <div>
                  {(() => {
                    const od = project.sources.find(s => s.source_type === "onedrive");
                    return od?.config?.folder_name ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "rgba(34,197,94,0.04)", borderRadius: 8, border: "1px solid rgba(34,197,94,0.15)" }}>
                        <span>📂</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", flex: 1 }}>{od.config.folder_name}</span>
                        <button onClick={loadFolders} style={{ background: "none", border: "none", color: "#748cab", fontSize: 12, cursor: "pointer" }}>
                          Changer
                        </button>
                      </div>
                    ) : (
                      <button onClick={loadFolders} disabled={loadingFolders}
                        style={{ width: "100%", padding: "10px", background: "rgba(0,120,212,0.06)", border: "1.5px dashed rgba(0,120,212,0.3)", borderRadius: 9, fontSize: 13, color: "#0078D4", fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                        {loadingFolders ? "Chargement..." : "📂 Sélectionner un dossier OneDrive"}
                      </button>
                    );
                  })()}

                  {/* Folder list */}
                  {showFolderPicker && folders.length > 0 && (
                    <div style={{ marginTop: 10, border: "1px solid rgba(62,92,118,0.1)", borderRadius: 10, overflow: "hidden", maxHeight: 200, overflowY: "auto" }}>
                      {folders.map(f => (
                        <div key={f.id} onClick={() => selectFolder(f.id, f.name)}
                          style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderBottom: "1px solid rgba(62,92,118,0.06)", cursor: "pointer", transition: "background 0.15s" }}
                          onMouseEnter={e => (e.currentTarget.style.background = "#f0f4f8")}
                          onMouseLeave={e => (e.currentTarget.style.background = "#fff")}>
                          <span>📂</span>
                          <span style={{ fontSize: 13, color: "#0d1321" }}>{f.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ClickUp */}
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.4rem", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: clickupConnected ? 0 : "1rem" }}>
                <span style={{ fontSize: 24 }}>✅</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#0d1321" }}>ClickUp</div>
                  <div style={{ fontSize: 12, color: "#748cab" }}>
                    {clickupConnected
                      ? (clickupUser ? `Connecté en tant que ${clickupUser}` : (locale === "fr" ? "Connecté — synchronisation en cours" : "Connected — syncing in background"))
                      : (locale === "fr" ? "Tâches & Projets ClickUp" : "Tasks & ClickUp Projects")}
                  </div>
                </div>
                {clickupConnected ? (
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontSize: 11, background: "rgba(34,197,94,0.08)", color: "#16a34a", borderRadius: 6, padding: "3px 10px", fontWeight: 600 }}>
                      {locale === "fr" ? "Connecté" : "Connected"}
                    </span>
                    <button onClick={disconnectClickUp}
                      style={{ background: "none", border: "1px solid rgba(239,68,68,0.3)", color: "#ef4444", borderRadius: 6, padding: "3px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                      {locale === "fr" ? "Déconnecter" : "Disconnect"}
                    </button>
                  </div>
                ) : null}
              </div>

              {/* ClickUp list picker — shown when connected */}
              {clickupConnected && (() => {
                const linkedList = project?.sources.find(s => s.source_type === "clickup");
                return (
                  <div style={{ marginTop: "0.75rem" }}>
                    {linkedList?.config?.list_name ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "rgba(123,104,238,0.06)", borderRadius: 8, border: "1px solid rgba(123,104,238,0.2)" }}>
                        <span>📋</span>
                        <div style={{ flex: 1 }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{linkedList.config.list_name}</span>
                          {linkedList.config.space_name && <span style={{ fontSize: 11, color: "#748cab", marginLeft: 8 }}>{linkedList.config.space_name}</span>}
                        </div>
                        <button onClick={loadCULists} style={{ background: "none", border: "none", color: "#748cab", fontSize: 12, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                          {locale === "fr" ? "Changer" : "Change"}
                        </button>
                      </div>
                    ) : (
                      <button onClick={loadCULists} disabled={loadingCULists}
                        style={{ width: "100%", padding: "10px", background: "rgba(123,104,238,0.06)", border: "1.5px dashed rgba(123,104,238,0.35)", borderRadius: 9, fontSize: 13, color: "#7B68EE", fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                        {loadingCULists ? (locale === "fr" ? "Chargement..." : "Loading...") : "📋 " + (locale === "fr" ? "Lier une liste ClickUp à ce projet" : "Link a ClickUp list to this project")}
                      </button>
                    )}

                    {/* List picker dropdown */}
                    {showCUPicker && cuLists.length > 0 && (
                      <div style={{ marginTop: 8, border: "1px solid rgba(62,92,118,0.12)", borderRadius: 10, overflow: "hidden", maxHeight: 220, overflowY: "auto", background: "#fff" }}>
                        {cuLists.map(lst => (
                          <div key={lst.list_id} onClick={() => selectCUList(lst)}
                            style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderBottom: "1px solid rgba(62,92,118,0.06)", cursor: "pointer" }}
                            onMouseEnter={e => (e.currentTarget.style.background = "#f5f3ff")}
                            onMouseLeave={e => (e.currentTarget.style.background = "")}>
                            <span style={{ fontSize: 14 }}>📋</span>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 13, fontWeight: 600, color: "#0d1321" }}>{lst.list_name}</div>
                              <div style={{ fontSize: 11, color: "#748cab" }}>{lst.space_name}</div>
                            </div>
                            {lst.task_count > 0 && (
                              <span style={{ fontSize: 11, color: "#7B68EE", background: "rgba(123,104,238,0.08)", borderRadius: 6, padding: "2px 7px", fontWeight: 600 }}>
                                {lst.task_count}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {!clickupConnected && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      value={clickupToken}
                      onChange={e => setClickupToken(e.target.value)}
                      placeholder={locale === "fr" ? "Coller votre token API ClickUp..." : "Paste your ClickUp API token..."}
                      type="password"
                      style={{ flex: 1, padding: "9px 12px", border: "1.5px solid rgba(62,92,118,0.2)", borderRadius: 8, fontSize: 13, fontFamily: "DM Sans, sans-serif", outline: "none" }}
                    />
                    <button
                      onClick={connectClickUp}
                      disabled={connectingCU || !clickupToken.trim()}
                      style={{ padding: "9px 20px", background: clickupToken.trim() ? "#7B68EE" : "#e5e7eb", color: clickupToken.trim() ? "#fff" : "#9ca3af", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif", whiteSpace: "nowrap" }}>
                      {connectingCU ? "..." : (locale === "fr" ? "Connecter" : "Connect")}
                    </button>
                  </div>
                  <p style={{ fontSize: 11, color: "#a0b4c4", margin: 0 }}>
                    {locale === "fr"
                      ? "Trouvez votre token sur clickup.com → Paramètres → Applications → API Token"
                      : "Find your token on clickup.com → Settings → Apps → API Token"}
                  </p>
                  {cuError && (
                    <div style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8, padding: "8px 12px", color: "#dc2626", fontSize: 12 }}>
                      {cuError}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Slack / Team messages */}
            <div style={{ background: "#fff", borderRadius: 16, padding: "1.4rem", border: "1px solid rgba(62,92,118,0.09)", boxShadow: "0 1px 6px rgba(13,19,33,0.04)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: "0.75rem" }}>
                <span style={{ fontSize: 24 }}>💬</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#0d1321" }}>Slack</div>
                  <div style={{ fontSize: 12, color: "#748cab" }}>
                    {(() => {
                      const s = project.sources.find(s => s.source_type === "slack");
                      return s?.config?.channel_name ? `#${s.config.channel_name}` : (locale === "fr" ? "Canal d'équipe du projet" : "Project team channel");
                    })()}
                  </div>
                </div>
                {project.sources.find(s => s.source_type === "slack") ? (
                  <span style={{ fontSize: 11, background: "rgba(34,197,94,0.08)", color: "#16a34a", borderRadius: 6, padding: "3px 10px", fontWeight: 600 }}>
                    {locale === "fr" ? "Lié" : "Linked"}
                  </span>
                ) : null}
              </div>
              {(() => {
                const linked = project.sources.find(s => s.source_type === "slack");
                return linked?.config?.channel_name ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "rgba(74,21,75,0.05)", borderRadius: 8, border: "1px solid rgba(74,21,75,0.15)" }}>
                    <span>💬</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", flex: 1 }}>#{linked.config.channel_name}</span>
                    <button onClick={loadSlackChannels} style={{ background: "none", border: "none", color: "#748cab", fontSize: 12, cursor: "pointer" }}>
                      {locale === "fr" ? "Changer" : "Change"}
                    </button>
                  </div>
                ) : (
                  <button onClick={loadSlackChannels} disabled={loadingSlackCh}
                    style={{ width: "100%", padding: "10px", background: "rgba(74,21,75,0.05)", border: "1.5px dashed rgba(74,21,75,0.25)", borderRadius: 9, fontSize: 13, color: "#4A154B", fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}>
                    {loadingSlackCh ? "..." : "💬 " + (locale === "fr" ? "Lier un canal Slack au projet" : "Link a Slack channel to this project")}
                  </button>
                );
              })()}
              {showSlackPicker && slackChannels.length > 0 && (
                <div style={{ marginTop: 8, border: "1px solid rgba(62,92,118,0.1)", borderRadius: 10, overflow: "hidden", maxHeight: 200, overflowY: "auto", background: "#fff" }}>
                  {slackChannels.map(ch => (
                    <div key={ch.channel_id} onClick={() => selectSlackChannel(ch)}
                      style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderBottom: "1px solid rgba(62,92,118,0.06)", cursor: "pointer" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "#faf5ff")}
                      onMouseLeave={e => (e.currentTarget.style.background = "")}>
                      <span>{ch.is_private ? "🔒" : "💬"}</span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#0d1321", flex: 1 }}>#{ch.channel_name}</span>
                      <span style={{ fontSize: 11, color: "#748cab" }}>{ch.num_members}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ background: "rgba(239,68,68,0.03)", borderRadius: 16, padding: "1.4rem", border: "1px solid rgba(239,68,68,0.13)" }}>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "#dc2626", marginBottom: 6 }}>{t.proj_danger_title}</h3>
              <p style={{ fontSize: 13, color: "#748cab", marginBottom: "1rem" }}>{t.proj_danger_sub}</p>
              <button
                onClick={async () => {
                  if (!confirm(`${t.proj_danger_btn} "${project.name}" ?`)) return;
                  await API.delete(`/api/projects/${project.id}`);
                  router.push("/dashboard/projects");
                }}
                style={{ background: "#dc2626", color: "#fff", border: "none", borderRadius: 9, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "DM Sans, sans-serif" }}
              >
                {t.proj_danger_btn}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
