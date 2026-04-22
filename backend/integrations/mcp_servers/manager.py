"""
MCP Server Manager — couche d'intégration unifiée.

Registre central de tous les outils MCP exposés par InsightFlow.
Appelle les handlers directement en Python (pas de subprocess stdio).

Servers enregistrés :
  analytics  → get_analytics_summary, get_burnout_signals
  gmail      → get_recent_emails, get_risk_items
  jira       → get_jira_tickets
  knowledge  → search_knowledge_base
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    name: str
    server: str
    description: str
    input_schema: dict
    handler: Callable[..., Awaitable[dict]]


class MCPServerManager:
    """
    Singleton qui orchestre tous les serveurs MCP.
    Les handlers sont de simples coroutines Python — aucun overhead stdio.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}   # tool_name → MCPTool
        self._register_all()

    # ── Registration ────────────────────────────────────────────────────

    def _reg(self, server: str, name: str, description: str, schema: dict, handler):
        self._tools[name] = MCPTool(
            name=name, server=server,
            description=description, input_schema=schema,
            handler=handler,
        )

    def _register_all(self):
        self._register_analytics()
        self._register_gmail()
        self._register_jira()
        self._register_knowledge()

    # ── Analytics ───────────────────────────────────────────────────────

    def _register_analytics(self):
        self._reg(
            "analytics", "get_analytics_summary",
            "KPIs globaux : sentiment, burnout, vélocité, distribution des topics.",
            {
                "type": "object",
                "properties": {"days": {"type": "integer", "description": "Période en jours (défaut 30)"}},
            },
            self._analytics_summary,
        )
        self._reg(
            "analytics", "get_burnout_signals",
            "Signaux burnout : messages hors horaires, weekends, scores élevés.",
            {
                "type": "object",
                "properties": {
                    "days":      {"type": "integer", "description": "Jours en arrière (défaut 14)"},
                    "threshold": {"type": "number",  "description": "Score minimum 0-1 (défaut 0.5)"},
                },
            },
            self._burnout_signals,
        )

    async def _analytics_summary(self, days: int = 30, **_) -> dict:
        from datetime import datetime, timedelta
        from core.database import SessionLocal
        from core.models import MessageRaw
        from collections import Counter

        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows  = db.query(MessageRaw).filter(MessageRaw.timestamp >= since).all()
            total = len(rows)
            if total == 0:
                return {"total": 0, "period_days": days}

            sentiments = Counter(r.sentiment_label or "UNKNOWN" for r in rows)
            emotions   = Counter(r.emotion_label for r in rows if r.emotion_label)
            topics     = Counter(r.topic for r in rows if r.topic)
            burnouts   = [r.burnout_score for r in rows if r.burnout_score is not None]

            return {
                "total":           total,
                "period_days":     days,
                "sentiment": {
                    "positive": round(sentiments["POSITIVE"] / total * 100, 1),
                    "neutral":  round(sentiments["NEUTRAL"]  / total * 100, 1),
                    "negative": round(sentiments["NEGATIVE"] / total * 100, 1),
                },
                "top_emotion":     emotions.most_common(1)[0][0] if emotions else None,
                "top_topic":       topics.most_common(1)[0][0]   if topics   else None,
                "avg_burnout":     round(sum(burnouts) / len(burnouts), 3) if burnouts else 0,
                "urgent_count":    sum(1 for r in rows if r.business_label in ("Urgent", "Risk", "Blocked")),
            }
        finally:
            db.close()

    async def _burnout_signals(self, days: int = 14, threshold: float = 0.5, **_) -> dict:
        from datetime import datetime, timedelta
        from core.database import SessionLocal
        from core.models import MessageRaw

        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows  = db.query(MessageRaw).filter(
                MessageRaw.timestamp >= since,
                MessageRaw.burnout_score >= threshold,
            ).order_by(MessageRaw.burnout_score.desc()).limit(20).all()

            return {
                "count": len(rows),
                "threshold": threshold,
                "signals": [
                    {
                        "id":             r.id,
                        "author":         r.author,
                        "source":         r.source,
                        "burnout_score":  round(r.burnout_score or 0, 3),
                        "is_after_hours": r.is_after_hours,
                        "is_weekend":     r.is_weekend,
                        "timestamp":      r.timestamp.isoformat() if r.timestamp else "",
                    }
                    for r in rows
                ],
            }
        finally:
            db.close()

    # ── Gmail ───────────────────────────────────────────────────────────

    def _register_gmail(self):
        self._reg(
            "gmail", "get_recent_emails",
            "Emails Gmail récents, filtrables par urgence ou label business.",
            {
                "type": "object",
                "properties": {
                    "days":           {"type": "integer", "description": "Jours en arrière (défaut 7)"},
                    "urgent_only":    {"type": "boolean", "description": "Seulement les urgents"},
                    "business_label": {"type": "string",  "description": "Urgent | Risk | Blocked | Conflict | Info"},
                    "limit":          {"type": "integer", "description": "Nombre max (défaut 10)"},
                },
            },
            self._recent_emails,
        )
        self._reg(
            "gmail", "get_risk_items",
            "Emails/messages flaggés à risque : Blocked, Urgent, Risk, Conflict.",
            {
                "type": "object",
                "properties": {
                    "days":  {"type": "integer", "description": "Jours en arrière (défaut 7)"},
                    "limit": {"type": "integer", "description": "Nombre max (défaut 10)"},
                },
            },
            self._risk_items,
        )

    async def _recent_emails(self, days: int = 7, urgent_only: bool = False,
                              business_label: str = None, limit: int = 10, **_) -> dict:
        from datetime import datetime, timedelta
        from core.database import SessionLocal
        from core.models import MessageRaw

        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            q = db.query(MessageRaw).filter(
                MessageRaw.source == "gmail",
                MessageRaw.timestamp >= since,
            )
            if urgent_only:
                q = q.filter(MessageRaw.business_label == "Urgent")
            if business_label:
                q = q.filter(MessageRaw.business_label == business_label)

            rows = q.order_by(MessageRaw.timestamp.desc()).limit(limit).all()
            return {
                "count":       len(rows),
                "period_days": days,
                "emails": [
                    {
                        "id":              r.id,
                        "title":           r.title or "(sans titre)",
                        "author":          r.author,
                        "timestamp":       r.timestamp.isoformat() if r.timestamp else "",
                        "sentiment":       r.sentiment_label,
                        "emotion":         r.emotion_label,
                        "business_label":  r.business_label,
                        "business_reason": r.business_reason,
                        "excerpt":         (r.content or "")[:200],
                    }
                    for r in rows
                ],
            }
        finally:
            db.close()

    async def _risk_items(self, days: int = 7, limit: int = 10, **_) -> dict:
        from datetime import datetime, timedelta
        from core.database import SessionLocal
        from core.models import MessageRaw

        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows  = db.query(MessageRaw).filter(
                MessageRaw.timestamp >= since,
                MessageRaw.business_label.in_(["Blocked", "Urgent", "Risk", "Conflict", "Overload"]),
            ).order_by(MessageRaw.timestamp.desc()).limit(limit).all()

            return {
                "count": len(rows),
                "risks": [
                    {
                        "id":              r.id,
                        "title":           r.title or "(sans titre)",
                        "author":          r.author,
                        "source":          r.source,
                        "timestamp":       r.timestamp.isoformat() if r.timestamp else "",
                        "business_label":  r.business_label,
                        "business_reason": r.business_reason,
                        "emotion":         r.emotion_label,
                    }
                    for r in rows
                ],
            }
        finally:
            db.close()

    # ── Jira ────────────────────────────────────────────────────────────

    def _register_jira(self):
        self._reg(
            "jira", "get_jira_tickets",
            "Tickets Jira depuis la base, filtrables par statut ou priorité.",
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string",  "description": "open | done | blocked"},
                    "days":   {"type": "integer", "description": "Jours en arrière (défaut 30)"},
                    "limit":  {"type": "integer", "description": "Nombre max (défaut 10)"},
                },
            },
            self._jira_tickets,
        )

    async def _jira_tickets(self, status: str = None, days: int = 30, limit: int = 10, **_) -> dict:
        from datetime import datetime, timedelta
        from core.database import SessionLocal
        from core.models import MessageRaw

        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            q = db.query(MessageRaw).filter(
                MessageRaw.source == "jira",
                MessageRaw.timestamp >= since,
            )
            if status == "blocked":
                q = q.filter(MessageRaw.business_label == "Blocked")
            elif status == "open":
                q = q.filter(MessageRaw.business_label != "Done")

            rows = q.order_by(MessageRaw.timestamp.desc()).limit(limit).all()
            return {
                "count": len(rows),
                "tickets": [
                    {
                        "id":              r.id,
                        "title":           r.title or "(sans titre)",
                        "author":          r.author,
                        "timestamp":       r.timestamp.isoformat() if r.timestamp else "",
                        "business_label":  r.business_label,
                        "business_reason": r.business_reason,
                        "url":             r.url,
                    }
                    for r in rows
                ],
            }
        finally:
            db.close()

    # ── Knowledge (RAG) ─────────────────────────────────────────────────

    def _register_knowledge(self):
        self._reg(
            "knowledge", "search_knowledge_base",
            "Recherche sémantique vectorielle dans tous les messages (Gmail, Slack, Jira).",
            {
                "type": "object",
                "properties": {
                    "query":         {"type": "string",  "description": "Question en langage naturel"},
                    "top_k":         {"type": "integer", "description": "Nombre de résultats (défaut 5)"},
                    "source_filter": {"type": "string",  "description": "gmail | slack | jira"},
                },
                "required": ["query"],
            },
            self._search_knowledge,
        )

    async def _search_knowledge(self, query: str, top_k: int = 5,
                                 source_filter: str = None, **_) -> dict:
        try:
            from intelligence.rag.retriever import retrieve
            from intelligence.rag.embedder import get_collection

            col = get_collection()
            if not col or col.count() == 0:
                return {"results": [], "count": 0, "indexed": 0, "note": "ChromaDB vide — sync d'abord"}

            docs = retrieve(query, top_k=top_k, source_filter=source_filter)
            return {
                "query":   query,
                "count":   len(docs),
                "indexed": col.count(),
                "results": [
                    {
                        "id":        d.id,
                        "source":    d.source,
                        "title":     d.title,
                        "author":    d.author,
                        "timestamp": d.timestamp,
                        "excerpt":   d.text[:300],
                        "sentiment": d.sentiment_label,
                        "score":     round(d.score, 3),
                    }
                    for d in docs
                ],
            }
        except Exception as e:
            return {"error": str(e), "results": [], "count": 0}

    # ── Public API ──────────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        """Retourne tous les outils disponibles (sans le handler)."""
        return [
            {
                "name":         t.name,
                "server":       t.server,
                "description":  t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def list_servers(self) -> dict[str, list[str]]:
        """Retourne {server: [tool_names]} pour l'aperçu rapide."""
        servers: dict[str, list[str]] = {}
        for t in self._tools.values():
            servers.setdefault(t.server, []).append(t.name)
        return servers

    async def call_tool(self, tool: str, args: dict) -> dict:
        """
        Appelle un outil par son nom.
        Recherche dans tous les serveurs enregistrés.
        """
        entry = self._tools.get(tool)
        if not entry:
            available = list(self._tools.keys())
            logger.warning("[MCPManager] Tool '%s' not found. Available: %s", tool, available)
            return {"error": f"Tool '{tool}' not found", "available_tools": available}

        logger.info("[MCPManager] %s.%s(%s)", entry.server, tool, list(args.keys()))
        try:
            result = await entry.handler(**args)
            return result
        except Exception as e:
            logger.error("[MCPManager] Error calling %s: %s", tool, e)
            return {"error": str(e), "tool": tool}


# Singleton
_manager: MCPServerManager | None = None


def get_manager() -> MCPServerManager:
    global _manager
    if _manager is None:
        _manager = MCPServerManager()
    return _manager
