"""
RAG Ask Route
=============
POST /api/ask          → question CEO → MCP tools + LLM → réponse + sources
POST /api/ask/reindex  → (ré)indexer tous les messages dans ChromaDB
GET  /api/ask/status   → état de l'index ChromaDB

LLM Provider (config .env) :
  LLM_PROVIDER=ollama  → Ollama local (défaut, gratuit)
  LLM_PROVIDER=azure   → Azure GPT-4o + MCP tools (premium)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.database import SessionLocal
from intelligence.llm.client import complete, get_provider_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["rag"])


# ── Schemas ───────────────────────────────────────────────────

class AskRequest(BaseModel):
    query:         str
    top_k:         int = 5
    source_filter: str | None = None
    provider:      str | None = None  # "ollama" | "gpt" | "azure" — overrides .env


class SourceDoc(BaseModel):
    id:        str
    title:     str
    author:    str
    timestamp: str
    source:    str
    sentiment: str
    business:  str
    excerpt:   str
    url:       str


class AskResponse(BaseModel):
    answer:        str
    sources:       list[SourceDoc]
    query:         str
    indexed_count: int
    provider:      str


# ── Chitchat detection ────────────────────────────────────────

_CHITCHAT_PATTERNS = [
    "salut", "bonjour", "hello", "hi ", "hey", "coucou", "bonsoir",
    "ça va", "ca va", "comment vas", "comment tu vas", "quoi de neuf",
    "merci", "au revoir", "bye", "ok", "oui", "non", "super", "bien",
]

def _is_chitchat(query: str) -> bool:
    q = query.lower().strip()
    if len(q.split()) > 5:
        return False
    return any(q.startswith(p) or q == p for p in _CHITCHAT_PATTERNS)


# ── Temporal filter detection ─────────────────────────────────

def _parse_temporal_filter(query: str) -> str | None:
    """
    Detect temporal expressions in query and return an ISO date lower-bound.
    Used to filter ChromaDB results to the relevant time window.
    """
    q = query.lower()
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if any(w in q for w in ["aujourd'hui", "ce jour", "today"]):
        return today.isoformat()
    if "hier" in q:
        return (today - timedelta(days=1)).isoformat()
    if any(w in q for w in ["cette semaine", "semaine en cours", "semaine actuelle", "cette sem."]):
        monday = today - timedelta(days=today.weekday())
        return monday.isoformat()
    if any(w in q for w in ["semaine dernière", "semaine passée", "la semaine d'avant"]):
        monday_last = today - timedelta(days=today.weekday() + 7)
        return monday_last.isoformat()
    if any(w in q for w in ["ce mois", "ce mois-ci", "mois en cours", "mois actuel"]):
        return today.replace(day=1).isoformat()
    if any(w in q for w in ["7 derniers jours", "7 jours", "last 7"]):
        return (today - timedelta(days=7)).isoformat()
    if any(w in q for w in ["30 derniers jours", "30 jours", "dernier mois"]):
        return (today - timedelta(days=30)).isoformat()
    if any(w in q for w in ["récent", "récents", "dernières 24h", "24h", "recent"]):
        return (today - timedelta(days=2)).isoformat()
    return None


def _build_date_context() -> str:
    """Return a date context string injected into the system prompt."""
    now = datetime.utcnow()
    monday = now - timedelta(days=now.weekday())
    return (
        f"\n\nDate actuelle : {now.strftime('%A %d %B %Y')} (UTC). "
        f"'Cette semaine' = depuis le lundi {monday.strftime('%d/%m/%Y')}. "
        f"Ne présente comme urgences de 'cette semaine' QUE les messages datés depuis cette date."
    )


# ── System prompts ────────────────────────────────────────────

SYSTEM_ANALYST = """Tu es l'assistant IA personnel d'un CEO d'entreprise.
Ton rôle est d'ANALYSER les données de l'entreprise et de répondre aux questions du CEO.

RÈGLE CRITIQUE — SOURCES : Tu DOIS appeler ces tools dans cet ordre :
1. search_knowledge_base(query=<question>) — TOUJOURS en premier, cherche dans emails+Slack+Jira
2. get_risk_items — TOUJOURS pour détecter les blocages et urgences
3. get_recent_emails — si la question concerne des emails
4. get_jira_tickets — si la question concerne des tickets/projets
5. get_analytics_summary — si la question concerne des KPIs/statistiques
N'omets JAMAIS search_knowledge_base — c'est ta source la plus complète.

RÈGLE CRITIQUE — FORMAT : Structure TOUJOURS ta réponse ainsi :

**Analyse des messages**
Voici les informations clés extraites des messages :
* [point clé 1] (Messages [N])
* [point clé 2] (Messages [N])
...

**Projections et recommandations**
* [recommandation 1]
* [recommandation 2]
...

**Prochaines étapes**
* [action concrète 1]
* [action concrète 2]
...

Puis liste les sources utilisées avec leur numéro [1], [2]...

Si aucune donnée trouvée après recherche complète, dis-le clairement sans inventer."""

SYSTEM_CHITCHAT = """Tu es l'assistant IA personnel d'un CEO d'entreprise.
Réponds de façon naturelle et brève à ce message de salutation ou conversation générale."""


# ── Routes ────────────────────────────────────────────────────

@router.post("", response_model=AskResponse)
async def ask(body: AskRequest):
    """
    Pipeline Ask Anything :
    - Ollama  : RAG ChromaDB → prompt → réponse
    - Azure   : MCP tools (GPT-4o choisit quoi appeler) → réponse
    """
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="La question ne peut pas être vide.")

    from intelligence.rag.embedder import get_collection
    col = get_collection()
    indexed_count = col.count() if col else 0

    # Effective provider : request override > .env default
    req_provider = (body.provider or "").lower() or None
    provider_info = get_provider_info()
    effective_provider = req_provider or provider_info["provider"]
    provider_name = effective_provider

    # Detect temporal filter and build date-aware system prompt
    since_date = _parse_temporal_filter(query)
    system_prompt = SYSTEM_ANALYST + _build_date_context()

    # ── Chitchat : réponse directe sans contexte ──────────────
    if _is_chitchat(query):
        answer = await complete(
            system=SYSTEM_CHITCHAT,
            user=query,
            use_tools=False,
            provider=req_provider,
        )
        return AskResponse(
            answer=answer, sources=[], query=query,
            indexed_count=indexed_count, provider=provider_name,
        )

    # ── Azure : MCP tools ─────────────────────────────────────
    if effective_provider == "azure":
        import asyncio
        from intelligence.rag.retriever import retrieve as _retrieve

        db = SessionLocal()
        try:
            answer = await asyncio.wait_for(
                complete(
                    system=system_prompt,
                    user=query,
                    use_tools=True,
                    db=db,
                    provider=req_provider,
                ),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[Ask/Azure] MCP timeout — fallback RAG seul")
            rag_docs = _retrieve(query, top_k=body.top_k, source_filter=body.source_filter, since_date=since_date)
            rag_relevant = [d for d in rag_docs if d.score <= 0.75]
            ctx = "\n\n---\n\n".join(
                f"[{i+1}] {d.author} ({d.source}) — {d.timestamp[:10]}\n{d.text[:400]}"
                for i, d in enumerate(rag_relevant)
            )
            answer = await complete(
                system=system_prompt,
                user=f"MESSAGES :\n{ctx}\n\nQUESTION : {query}",
                use_tools=False,
                provider=req_provider,
            )
        finally:
            db.close()

        rag_docs = _retrieve(query, top_k=body.top_k, source_filter=body.source_filter, since_date=since_date)
        rag_relevant = [d for d in rag_docs if d.score <= 0.55]
        sources = [
            SourceDoc(
                id=d.id, title=d.title or "(sans titre)",
                author=d.author, timestamp=d.timestamp,
                source=d.source, sentiment=d.sentiment_label,
                business=d.business_label,
                excerpt=d.text[:200] + ("…" if len(d.text) > 200 else ""),
                url=d.url or "",
            )
            for d in rag_relevant
        ]
        return AskResponse(
            answer=answer, sources=sources, query=query,
            indexed_count=indexed_count, provider=provider_name,
        )

    # ── Ollama / GPT : RAG ChromaDB ───────────────────────────
    from intelligence.rag.retriever import retrieve

    if indexed_count == 0:
        return AskResponse(
            answer="Aucun message n'est encore indexé. Cliquez sur ↻ pour initialiser la base de connaissances.",
            sources=[], query=query, indexed_count=0, provider=provider_name,
        )

    docs = retrieve(query, top_k=body.top_k, source_filter=body.source_filter, since_date=since_date)

    if not docs and since_date:
        docs = retrieve(query, top_k=body.top_k, source_filter=body.source_filter)
        if docs:
            system_prompt += "\n\nATTENTION : Aucun message trouvé pour la période demandée. Les résultats ci-dessous sont les plus récents disponibles — précise leurs dates dans ta réponse."

    relevant = [d for d in docs if d.score <= 0.75]

    if not relevant:
        period = " pour la période demandée" if since_date else ""
        return AskResponse(
            answer=f"Je n'ai pas trouvé d'informations pertinentes{period} dans vos données.",
            sources=[], query=query, indexed_count=indexed_count, provider=provider_name,
        )

    context = "\n\n---\n\n".join(
        f"[{i+1}] {d.author} ({d.source}) — {d.timestamp[:10]}\n"
        f"Sujet : {d.title}\nExtrait : {d.text[:400]}\n"
        f"Sentiment : {d.sentiment_label} | Priorité : {d.business_label}"
        for i, d in enumerate(relevant)
    )

    answer = await complete(
        system=system_prompt,
        user=f"MESSAGES :\n{context}\n\nQUESTION : {query}",
        use_tools=False,
        provider=req_provider,
    )

    sources = [
        SourceDoc(
            id=d.id, title=d.title or "(sans titre)",
            author=d.author, timestamp=d.timestamp,
            source=d.source, sentiment=d.sentiment_label,
            business=d.business_label,
            excerpt=d.text[:200] + ("…" if len(d.text) > 200 else ""),
            url=d.url or "",
        )
        for d in relevant
    ]

    return AskResponse(
        answer=answer, sources=sources, query=query,
        indexed_count=indexed_count, provider=provider_name,
    )


@router.post("/reindex")
async def reindex():
    from intelligence.rag.embedder import index_from_db
    db = SessionLocal()
    try:
        n = index_from_db(db, limit=2000)
        return {"indexed": n, "message": f"{n} messages indexés dans ChromaDB."}
    finally:
        db.close()


@router.get("/status")
async def index_status():
    try:
        from intelligence.rag.embedder import get_collection
        col = get_collection()
        return {
            "indexed_count": col.count(),
            "collection":    col.name,
            "ready":         col.count() > 0,
            "llm":           get_provider_info(),
        }
    except Exception as e:
        return {"indexed_count": 0, "ready": False, "error": str(e)}
