"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import API from "@/lib/api";
import { getUser } from "@/lib/auth";

/* ── Types ─────────────────────────────────────────────────────────────────── */
interface OrgRow { id:string; name:string; plan:string; created_at:string; ceo_email:string|null; ceo_name:string|null; user_count:number; source_count:number; message_count:number; }
interface Stats   { total_orgs:number; total_users:number; total_messages:number; total_sources:number; }
interface Connector { key:string; name:string; icon:string; color:string; category:string; auth_type:string; description:string; enabled:boolean; coming_soon:boolean; }
interface UserRow { id:number; email:string; full_name:string; role:string; org_id:string|null; org_name:string; is_active:boolean; created_at:string; }
interface MLStatus { corrections:any; last_training:any; training_in_progress:boolean; training_task?:string; models:any; script_available:boolean; }

/* ── Helpers ────────────────────────────────────────────────────────────────── */
const PLAN_META: Record<string,{label:string;color:string;bg:string}> = {
  free:       {label:"Free",       color:"#748cab", bg:"rgba(116,140,171,0.12)"},
  pro:        {label:"Pro",        color:"#2563eb", bg:"rgba(37,99,235,0.1)"},
  enterprise: {label:"Enterprise", color:"#9333ea", bg:"rgba(147,51,234,0.1)"},
};
const ROLE_COLOR: Record<string,string> = { superadmin:"#ef4444", ceo:"#f59e0b", pm:"#3b82f6" };

function timeAgo(iso:string) {
  const d = Math.floor((Date.now()-new Date(iso).getTime())/86400000);
  if(d===0) return "Aujourd'hui"; if(d===1) return "Hier"; if(d<30) return `${d}j`; return `${Math.floor(d/30)} mois`;
}

const card: React.CSSProperties = {
  background:"#fff", borderRadius:16, border:"1px solid rgba(62,92,118,0.1)",
  boxShadow:"0 2px 8px rgba(13,19,33,0.05)", overflow:"hidden",
};
const th: React.CSSProperties = {
  padding:"11px 16px", textAlign:"left", fontSize:11, fontWeight:700,
  color:"#748cab", textTransform:"uppercase", letterSpacing:"0.1em",
  background:"rgba(62,92,118,0.04)", borderBottom:"1px solid rgba(62,92,118,0.08)",
};
const td: React.CSSProperties = { padding:"13px 16px", borderBottom:"1px solid rgba(62,92,118,0.05)" };

const TABS = [
  {id:"orgs",       label:"🏢 Organisations"},
  {id:"users",      label:"👤 Utilisateurs"},
  {id:"connectors", label:"🔌 Connecteurs"},
  {id:"ai",         label:"🤖 IA & Modèles"},
] as const;
type TabId = typeof TABS[number]["id"];

/* ── Component ──────────────────────────────────────────────────────────────── */
function AdminInner() {
  const router  = useRouter();
  const params  = useSearchParams();
  const [tab, setTab]         = useState<TabId>("orgs");
  const [stats, setStats]     = useState<Stats|null>(null);
  const [orgs, setOrgs]       = useState<OrgRow[]>([]);
  const [users, setUsers]     = useState<UserRow[]>([]);
  const [connectors, setConn] = useState<Connector[]>([]);
  const [ml, setMl]           = useState<MLStatus|null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string|null>(null);
  const [planEdit, setPlanEdit] = useState<{id:string;plan:string}|null>(null);
  const [retraining, setRetraining] = useState(false);
  const [retMsg, setRetMsg] = useState<string|null>(null);

  useEffect(() => {
    const user = getUser();
    if (!user || user.role !== "superadmin") { router.replace("/dashboard"); return; }
    loadBase();
  }, [router]);

  useEffect(() => {
    const t = params.get("tab") as TabId|null;
    if (t && TABS.find(x=>x.id===t)) setTab(t);
  }, [params]);

  useEffect(() => {
    if (tab === "users"      && users.length === 0)      loadUsers();
    if (tab === "connectors" && connectors.length === 0) loadConnectors();
    if (tab === "ai"         && !ml)                     loadML();
  }, [tab]);

  async function loadBase() {
    setLoading(true);
    try {
      const [s,o] = await Promise.all([API.get("/api/admin/stats"), API.get("/api/admin/orgs")]);
      setStats(s.data); setOrgs(o.data);
    } catch {}
    setLoading(false);
  }
  async function loadUsers()      { try { setUsers((await API.get("/api/admin/users")).data); } catch {} }
  async function loadConnectors() { try { setConn((await API.get("/api/admin/connectors")).data); } catch {} }
  async function loadML()         { try { setMl((await API.get("/api/admin/ai/status")).data); } catch {} }

  async function deleteOrg(id:string, name:string) {
    if (!confirm(`Supprimer "${name}" et TOUTES ses données ? Irréversible.`)) return;
    setDeleting(id);
    try { await API.delete(`/api/admin/orgs/${id}`); setOrgs(p=>p.filter(o=>o.id!==id)); loadBase(); }
    catch(e:any) { alert("Erreur : "+(e.message??"impossible")); }
    finally { setDeleting(null); }
  }

  async function changePlan(id:string, plan:string) {
    try { await API.patch(`/api/admin/orgs/${id}`,{plan}); setOrgs(p=>p.map(o=>o.id===id?{...o,plan}:o)); setPlanEdit(null); }
    catch {}
  }

  async function toggleConnector(key:string, field:"enabled"|"coming_soon", val:boolean) {
    try {
      await API.patch(`/api/admin/connectors/${key}`,{[field]:val});
      setConn(p=>p.map(c=>c.key===key?{...c,[field]:val}:c));
    } catch {}
  }

  async function retrain(task:string) {
    setRetraining(true); setRetMsg(null);
    try {
      const r = await API.post("/api/admin/ai/retrain",{task, min_samples:1});
      setRetMsg(`✅ Fine-tuning lancé : ${r.data.message ?? "en cours…"}`);
      setTimeout(loadML, 3000);
    } catch(e:any) { setRetMsg(`❌ ${e.response?.data?.detail ?? e.message}`); }
    finally { setRetraining(false); }
  }

  if (loading) return (
    <div style={{display:"flex",alignItems:"center",justifyContent:"center",height:"60vh",flexDirection:"column",gap:12}}>
      <div style={{width:32,height:32,border:"2px solid rgba(147,51,234,0.2)",borderTop:"2px solid #9333ea",borderRadius:"50%",animation:"spin 0.8s linear infinite"}} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <span style={{fontSize:13,color:"#748cab"}}>Chargement…</span>
    </div>
  );

  return (
    <div style={{maxWidth:1100,margin:"0 auto"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        tr.row:hover td{background:rgba(147,51,234,0.02)!important}
        .tog{cursor:pointer;transition:all 0.2s}
      `}</style>

      {/* Header */}
      <div style={{marginBottom:"2rem",animation:"fadeUp 0.3s ease"}}>
        <div style={{fontSize:11,letterSpacing:"0.18em",textTransform:"uppercase",color:"#9333ea",fontWeight:600,marginBottom:6}}>Super Admin</div>
        <h1 style={{fontFamily:"DM Serif Display, serif",fontSize:30,color:"#0d1321",margin:0}}>Platform Console</h1>
        <p style={{color:"#748cab",fontSize:13,marginTop:6}}>Gérez les organisations, connecteurs, utilisateurs et l'IA de la plateforme.</p>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:"1rem",marginBottom:"2rem"}}>
          {[
            {label:"Organisations", value:stats.total_orgs,     icon:"🏢", color:"#9333ea"},
            {label:"Utilisateurs",  value:stats.total_users,    icon:"👤", color:"#2563eb"},
            {label:"Messages",      value:stats.total_messages, icon:"✉️",  color:"#ea580c"},
            {label:"Sources conn.", value:stats.total_sources,  icon:"🔗", color:"#16a34a"},
          ].map(s=>(
            <div key={s.label} style={{...card,display:"flex",alignItems:"center",gap:14,padding:"1.25rem 1.5rem"}}>
              <div style={{width:44,height:44,borderRadius:12,background:`${s.color}14`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:20,flexShrink:0}}>{s.icon}</div>
              <div>
                <div style={{fontSize:24,fontWeight:700,color:s.color,fontFamily:"DM Serif Display, serif"}}>{s.value.toLocaleString()}</div>
                <div style={{fontSize:12,color:"#748cab",fontWeight:500}}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{display:"flex",gap:2,borderBottom:"2px solid rgba(62,92,118,0.1)",marginBottom:"1.5rem"}}>
        {TABS.map(t=>(
          <button key={t.id} onClick={()=>setTab(t.id)} style={{
            padding:"9px 20px",border:"none",background:"none",cursor:"pointer",
            fontSize:13,fontWeight:tab===t.id?700:400,
            color:tab===t.id?"#9333ea":"#748cab",
            borderBottom:tab===t.id?"2px solid #9333ea":"2px solid transparent",
            marginBottom:-2,transition:"all 0.15s",
          }}>{t.label}</button>
        ))}
      </div>

      {/* ── ORGANISATIONS ─────────────────────────────────────────────────────── */}
      {tab==="orgs" && (
        <div style={{...card,animation:"fadeUp 0.3s ease"}}>
          {orgs.length===0 ? (
            <div style={{textAlign:"center",padding:"3rem",color:"#748cab"}}>
              <div style={{fontSize:32,marginBottom:8}}>🏢</div>
              <div style={{fontWeight:600}}>Aucune organisation enregistrée</div>
              <div style={{fontSize:12,marginTop:4}}>Les CEOs s'inscrivent depuis /login → Créer un compte</div>
            </div>
          ) : (
            <table style={{width:"100%",borderCollapse:"collapse"}}>
              <thead><tr>{["Organisation","CEO","Plan","Users","Sources","Messages","Créée","Actions"].map(h=><th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {orgs.map((org,i)=>{
                  const pm=PLAN_META[org.plan]??PLAN_META.free;
                  return (
                    <tr key={org.id} className="row">
                      <td style={td}>
                        <div style={{fontSize:14,fontWeight:700,color:"#0d1321"}}>{org.name}</div>
                        <div style={{fontSize:10,color:"#94a3b8",fontFamily:"monospace"}}>{org.id.slice(0,8)}…</div>
                      </td>
                      <td style={td}>
                        {org.ceo_email
                          ? <><div style={{fontSize:13,fontWeight:600,color:"#0d1321"}}>{org.ceo_name}</div><div style={{fontSize:11,color:"#748cab"}}>{org.ceo_email}</div></>
                          : <span style={{fontSize:12,color:"#94a3b8",fontStyle:"italic"}}>—</span>}
                      </td>
                      <td style={td}>
                        {planEdit?.id===org.id
                          ? <select defaultValue={org.plan} onChange={e=>changePlan(org.id,e.target.value)} style={{fontSize:12,padding:"4px 8px",borderRadius:8,border:"1px solid #9333ea",background:"#fff",cursor:"pointer"}}>
                              {["free","pro","enterprise"].map(p=><option key={p} value={p}>{p}</option>)}
                            </select>
                          : <button onClick={()=>setPlanEdit({id:org.id,plan:org.plan})} style={{padding:"3px 10px",borderRadius:20,border:"none",cursor:"pointer",background:pm.bg,color:pm.color,fontSize:11,fontWeight:700}}>{pm.label}</button>
                        }
                      </td>
                      <td style={{...td,textAlign:"center",fontWeight:700,color:"#0d1321"}}>{org.user_count}</td>
                      <td style={{...td,textAlign:"center",fontWeight:700,color:"#0d1321"}}>{org.source_count}</td>
                      <td style={{...td,textAlign:"center",fontWeight:700,color:"#0d1321"}}>{org.message_count.toLocaleString()}</td>
                      <td style={{...td,fontSize:12,color:"#748cab"}}>{org.created_at?timeAgo(org.created_at):"—"}</td>
                      <td style={td}>
                        <button onClick={()=>deleteOrg(org.id,org.name)} disabled={deleting===org.id} style={{padding:"5px 12px",borderRadius:8,border:"none",background:"rgba(239,68,68,0.08)",color:"#ef4444",fontSize:12,fontWeight:600,cursor:"pointer"}}>
                          {deleting===org.id?"…":"Supprimer"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── USERS ─────────────────────────────────────────────────────────────── */}
      {tab==="users" && (
        <div style={{...card,animation:"fadeUp 0.3s ease"}}>
          {users.length===0
            ? <div style={{textAlign:"center",padding:"3rem",color:"#748cab"}}><div style={{width:24,height:24,border:"2px solid rgba(147,51,234,0.15)",borderTop:"2px solid #9333ea",borderRadius:"50%",animation:"spin 0.8s linear infinite",margin:"0 auto 8px"}}/>Chargement…</div>
            : <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead><tr>{["Nom","Email","Rôle","Organisation","Statut","Créé"].map(h=><th key={h} style={th}>{h}</th>)}</tr></thead>
                <tbody>
                  {users.map((u,i)=>(
                    <tr key={u.id} className="row">
                      <td style={td}><span style={{fontSize:13,fontWeight:600,color:"#0d1321"}}>{u.full_name}</span></td>
                      <td style={{...td,fontSize:12,color:"#748cab"}}>{u.email}</td>
                      <td style={td}>
                        <span style={{padding:"2px 8px",borderRadius:20,fontSize:11,fontWeight:700,background:`${ROLE_COLOR[u.role]??'#748cab'}15`,color:ROLE_COLOR[u.role]??'#748cab',textTransform:"uppercase",letterSpacing:"0.05em"}}>
                          {u.role}
                        </span>
                      </td>
                      <td style={{...td,fontSize:13,color:"#0d1321"}}>{u.org_name}</td>
                      <td style={td}>
                        <span style={{padding:"2px 8px",borderRadius:20,fontSize:11,fontWeight:600,background:u.is_active?"#f0fdf4":"#fef2f2",color:u.is_active?"#16a34a":"#ef4444"}}>
                          {u.is_active?"Actif":"Désactivé"}
                        </span>
                      </td>
                      <td style={{...td,fontSize:12,color:"#748cab"}}>{u.created_at?timeAgo(u.created_at):"—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
          }
        </div>
      )}

      {/* ── CONNECTEURS ───────────────────────────────────────────────────────── */}
      {tab==="connectors" && (
        <div style={{animation:"fadeUp 0.3s ease"}}>
          <div style={{marginBottom:"1rem",padding:"12px 16px",background:"rgba(37,99,235,0.06)",borderRadius:12,border:"1px solid rgba(37,99,235,0.15)",fontSize:12,color:"#1e40af"}}>
            💡 <strong>Catalogue de connecteurs</strong> — Activez ou désactivez les sources disponibles pour vos clients CEO. Un connecteur désactivé disparaît de leur interface.
          </div>
          {Object.entries(
            connectors.reduce((acc,c)=>{ if(!acc[c.category]) acc[c.category]=[]; acc[c.category].push(c); return acc; },{} as Record<string,Connector[]>)
          ).map(([cat,list])=>(
            <div key={cat} style={{marginBottom:"1.5rem"}}>
              <div style={{fontSize:11,color:"#748cab",textTransform:"uppercase",letterSpacing:"0.12em",fontWeight:700,marginBottom:8}}>{cat}</div>
              <div style={{...card,padding:0}}>
                {list.map((c,i)=>(
                  <div key={c.key} style={{display:"flex",alignItems:"center",gap:14,padding:"14px 20px",borderBottom:i<list.length-1?"1px solid rgba(62,92,118,0.06)":"none"}}>
                    <span style={{fontSize:22,width:32,textAlign:"center",flexShrink:0}}>{c.icon}</span>
                    <div style={{flex:1}}>
                      <div style={{fontSize:14,fontWeight:700,color:"#0d1321"}}>{c.name}</div>
                      <div style={{fontSize:11,color:"#748cab"}}>{c.description} · <code style={{fontSize:10,background:"rgba(62,92,118,0.08)",padding:"1px 5px",borderRadius:4}}>{c.auth_type}</code></div>
                    </div>
                    {/* Enabled toggle */}
                    <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:4}}>
                      <div style={{fontSize:10,color:"#748cab",fontWeight:600}}>ACTIVÉ</div>
                      <div className="tog" onClick={()=>toggleConnector(c.key,"enabled",!c.enabled)}
                        style={{width:42,height:24,borderRadius:12,background:c.enabled?"#22c55e":"rgba(62,92,118,0.2)",position:"relative",transition:"background 0.2s"}}>
                        <div style={{position:"absolute",top:3,left:c.enabled?20:3,width:18,height:18,borderRadius:"50%",background:"#fff",boxShadow:"0 1px 4px rgba(0,0,0,0.2)",transition:"left 0.2s"}}/>
                      </div>
                    </div>
                    {/* Coming soon toggle */}
                    <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:4}}>
                      <div style={{fontSize:10,color:"#748cab",fontWeight:600}}>BIENTÔT</div>
                      <div className="tog" onClick={()=>toggleConnector(c.key,"coming_soon",!c.coming_soon)}
                        style={{width:42,height:24,borderRadius:12,background:c.coming_soon?"#f59e0b":"rgba(62,92,118,0.2)",position:"relative",transition:"background 0.2s"}}>
                        <div style={{position:"absolute",top:3,left:c.coming_soon?20:3,width:18,height:18,borderRadius:"50%",background:"#fff",boxShadow:"0 1px 4px rgba(0,0,0,0.2)",transition:"left 0.2s"}}/>
                      </div>
                    </div>
                    {/* Status badge */}
                    <span style={{minWidth:72,textAlign:"center",padding:"4px 10px",borderRadius:20,fontSize:11,fontWeight:700,
                      background:c.enabled&&!c.coming_soon?"#f0fdf4":c.coming_soon?"#fffbeb":"#fef2f2",
                      color:c.enabled&&!c.coming_soon?"#16a34a":c.coming_soon?"#d97706":"#ef4444"}}>
                      {c.enabled&&!c.coming_soon?"Disponible":c.coming_soon?"Bientôt":"Désactivé"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── IA & MODÈLES ──────────────────────────────────────────────────────── */}
      {tab==="ai" && (
        <div style={{display:"flex",flexDirection:"column",gap:"1.5rem",animation:"fadeUp 0.3s ease"}}>
          <div style={{padding:"12px 16px",background:"rgba(147,51,234,0.06)",borderRadius:12,border:"1px solid rgba(147,51,234,0.15)",fontSize:12,color:"#6d28d9"}}>
            🤖 <strong>Supervision IA</strong> — Vous gérez les modèles NLP de la plateforme (sentiment, émotion, burnout). Le continuous learning s'améliore avec les corrections des utilisateurs.
          </div>

          {!ml ? (
            <div style={{textAlign:"center",padding:"3rem",color:"#748cab"}}>
              <div style={{width:28,height:28,border:"2px solid rgba(147,51,234,0.2)",borderTop:"2px solid #9333ea",borderRadius:"50%",animation:"spin 0.8s linear infinite",margin:"0 auto 8px"}}/>Chargement des modèles…
            </div>
          ) : (
            <>
              {/* Training status */}
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"1rem"}}>
                {/* Corrections en attente */}
                <div style={{...card,padding:"1.5rem"}}>
                  <div style={{fontSize:12,color:"#748cab",textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:"1rem"}}>Corrections en attente</div>
                  {[
                    {label:"Sentiment", value:ml.corrections?.pending_sentiment??0, color:"#3b82f6"},
                    {label:"Émotion",   value:ml.corrections?.pending_emotion??0,   color:"#9333ea"},
                    {label:"Métier",    value:ml.corrections?.pending_business??0,  color:"#ea580c"},
                  ].map(row=>(
                    <div key={row.label} style={{display:"flex",alignItems:"center",gap:10,marginBottom:10}}>
                      <div style={{flex:1,fontSize:13,fontWeight:600,color:"#0d1321"}}>{row.label}</div>
                      <div style={{fontSize:20,fontWeight:700,color:row.color}}>{row.value}</div>
                      <div style={{width:60,height:6,borderRadius:4,background:"rgba(62,92,118,0.1)",overflow:"hidden"}}>
                        <div style={{height:"100%",width:`${Math.min(100,(row.value/20)*100)}%`,background:row.color,borderRadius:4}}/>
                      </div>
                    </div>
                  ))}
                  <div style={{fontSize:11,color:"#748cab",marginTop:8}}>
                    Total all-time : <strong>{ml.corrections?.total_all_time??0}</strong> corrections
                  </div>
                </div>

                {/* État du training */}
                <div style={{...card,padding:"1.5rem"}}>
                  <div style={{fontSize:12,color:"#748cab",textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:"1rem"}}>État du training</div>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:"1rem"}}>
                    <div style={{width:10,height:10,borderRadius:"50%",background:ml.training_in_progress?"#f59e0b":"#22c55e",boxShadow:ml.training_in_progress?"0 0 8px #f59e0b88":"none",animation:ml.training_in_progress?"spin 1s linear infinite":"none"}}/>
                    <span style={{fontSize:14,fontWeight:700,color:"#0d1321"}}>
                      {ml.training_in_progress?`Fine-tuning en cours (${ml.training_task??""})…`:"Aucun training actif"}
                    </span>
                  </div>
                  {ml.last_training && (
                    <div style={{fontSize:12,color:"#748cab",marginBottom:4}}>
                      Dernier run : <strong style={{color:"#0d1321"}}>{ml.last_training.task ?? "—"}</strong>
                      {ml.last_training.final_f1 && <span> — F1 : <strong style={{color:"#22c55e"}}>{(ml.last_training.final_f1*100).toFixed(1)}%</strong></span>}
                    </div>
                  )}
                  <div style={{fontSize:12,color:ml.script_available?"#22c55e":"#ef4444"}}>
                    Script CL : {ml.script_available?"✅ disponible":"❌ introuvable"}
                  </div>
                </div>
              </div>

              {/* Models */}
              <div style={{...card,padding:"1.5rem"}}>
                <div style={{fontSize:12,color:"#748cab",textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:"1rem"}}>Modèles NLP</div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"1rem"}}>
                  {Object.entries(ml.models??{}).map(([name,info]:any)=>(
                    <div key={name} style={{padding:"14px 16px",borderRadius:12,background:"rgba(62,92,118,0.04)",border:"1px solid rgba(62,92,118,0.08)"}}>
                      <div style={{fontSize:13,fontWeight:700,color:"#0d1321",marginBottom:6,textTransform:"capitalize"}}>{name}</div>
                      <div style={{fontSize:12,color:"#748cab",marginBottom:2}}>Modèle base : <span style={{color:info.base_model_exists?"#22c55e":"#ef4444"}}>{info.base_model_exists?"✅ chargé":"❌ absent"}</span></div>
                      <div style={{fontSize:12,color:"#748cab",marginBottom:2}}>Versions fine-tunées : <strong style={{color:"#0d1321"}}>{info.versions_count}</strong></div>
                      {info.latest_finetuned && <div style={{fontSize:11,color:"#9333ea"}}>Dernière : {info.latest_finetuned}</div>}
                    </div>
                  ))}
                </div>
              </div>

              {/* Retrain actions */}
              <div style={{...card,padding:"1.5rem"}}>
                <div style={{fontSize:12,color:"#748cab",textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:700,marginBottom:"1rem"}}>Lancer un re-entraînement</div>
                <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
                  {["sentiment","emotion","all"].map(task=>(
                    <button key={task} onClick={()=>retrain(task)} disabled={retraining||ml.training_in_progress}
                      style={{padding:"9px 20px",borderRadius:10,border:"none",cursor:retraining||ml.training_in_progress?"not-allowed":"pointer",
                        background:retraining||ml.training_in_progress?"rgba(62,92,118,0.1)":"rgba(147,51,234,0.1)",
                        color:retraining||ml.training_in_progress?"#748cab":"#9333ea",
                        fontSize:13,fontWeight:600,transition:"all 0.15s"}}>
                      {task==="all"?"🚀 Tout re-entraîner":`▶ ${task}`}
                    </button>
                  ))}
                  <button onClick={loadML} style={{padding:"9px 16px",borderRadius:10,border:"1px solid rgba(62,92,118,0.2)",background:"transparent",color:"#748cab",fontSize:12,cursor:"pointer"}}>
                    ↻ Actualiser
                  </button>
                </div>
                {retMsg && <div style={{marginTop:12,fontSize:13,padding:"10px 14px",borderRadius:10,background:retMsg.startsWith("✅")?"#f0fdf4":"#fef2f2",color:retMsg.startsWith("✅")?"#16a34a":"#ef4444"}}>{retMsg}</div>}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminPage() {
  return (
    <Suspense fallback={
      <div style={{display:"flex",alignItems:"center",justifyContent:"center",height:"60vh",flexDirection:"column",gap:12}}>
        <div style={{width:32,height:32,border:"2px solid rgba(147,51,234,0.2)",borderTop:"2px solid #9333ea",borderRadius:"50%",animation:"spin 0.8s linear infinite"}} />
        <span style={{fontSize:13,color:"#748cab"}}>Chargement…</span>
      </div>
    }>
      <AdminInner />
    </Suspense>
  );
}
