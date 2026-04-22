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

    provider_info = get_provider_info()
    provider_name = provider_info["provider"]

    # ── Chitchat : réponse directe sans contexte ──────────────
    if _is_chitchat(query):
        answer = await complete(
            system=SYSTEM_CHITCHAT,
            user=query,
            use_tools=False,
        )
        return AskResponse(
            answer=answer, sources=[], query=query,
            indexed_count=indexed_count, provider=provider_name,
        )

    # ── Azure GPT-4o : MCP tools ──────────────────────────────
    if provider_name == "azure":
        import asyncio
        from intelligence.rag.retriever import retrieve as _retrieve

        db = SessionLocal()
        try:
            answer = await asyncio.wait_for(
                complete(
                    system=SYSTEM_ANALYST,
                    user=query,
                    use_tools=True,
                    db=db,
                ),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[Ask/Azure] MCP timeout — fallback RAG seul")
            rag_docs = _retrieve(query, top_k=body.top_k, source_filter=body.source_filter)
            rag_relevant = [d for d in rag_docs if d.score <= 0.75]
            ctx = "\n\n---\n\n".join(
                f"[{i+1}] {d.author} ({d.source}) — {d.timestamp[:10]}\n{d.text[:400]}"
                for i, d in enumerate(rag_relevant)
            )
            answer = await complete(
                system=SYSTEM_ANALYST,
                user=f"MESSAGES :\n{ctx}\n\nQUESTION : {query}",
                use_tools=False,
            )
        finally:
            db.close()

        # RAG lookup pour afficher les sources dans le UI — seuil strict pour éviter le bruit
        rag_docs = _retrieve(query, top_k=body.top_k, source_filter=body.source_filter)
        rag_relevant = [d for d in rag_docs if d.score <= 0.55]
        sources = [
            SourceDoc(
                id=d.id,
                title=d.title or "(sans titre)",
                author=d.author,
                timestamp=d.timestamp,
                source=d.source,
                sentiment=d.sentiment_label,
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

    # ── Ollama / OpenAI : RAG ChromaDB ───────────────────────
    from intelligence.rag.retriever import retrieve

    if indexed_count == 0:
        return AskResponse(
            answer="Aucun message n'est encore indexé. Cliquez sur 🔄 pour initialiser la base de connaissances.",
            sources=[], query=query, indexed_count=0, provider=provider_name,
        )

    docs = retrieve(query, top_k=body.top_k, source_filter=body.source_filter)
    relevant = [d for d in docs if d.score <= 0.75]

    if not relevant:
        return AskResponse(
            answer="Je n'ai pas trouvé d'informations pertinentes dans vos données pour répondre à cette question.",
            sources=[], query=query, indexed_count=indexed_count, provider=provider_name,
        )

    context = "\n\n---\n\n".join(
        f"[{i+1}] {d.author} ({d.source}) — {d.timestamp[:10]}\n"
        f"Sujet : {d.title}\nExtrait : {d.text[:400]}\n"
        f"Sentiment : {d.sentiment_label} | Priorité : {d.business_label}"
        for i, d in enumerate(relevant)
    )

    answer = await complete(
        system=SYSTEM_ANALYST,
        user=f"MESSAGES :\n{context}\n\nQUESTION : {query}",
        use_tools=False,
    )

    sources = [
        SourceDoc(
            id=d.id,
            title=d.title or "(sans titre)",
            author=d.author,
            timestamp=d.timestamp,
            source=d.source,
            sentiment=d.sentiment_label,
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
