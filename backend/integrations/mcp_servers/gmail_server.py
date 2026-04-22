"""
MCP Server — Gmail
==================
Expose les emails Gmail depuis PostgreSQL via le protocole MCP officiel.

Tools exposés :
  - get_recent_emails  : emails récents, filtrables par urgence/label
  - get_risk_items     : emails flaggés Urgent/Blocked/Risk/Conflict
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

# Ajoute le dossier backend au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("gmail-insightflow")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_recent_emails",
            description="Get recent Gmail emails from the database, filterable by urgency or business label.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days":           {"type": "integer", "description": "How many days back (default 7)"},
                    "urgent_only":    {"type": "boolean", "description": "Return only urgent emails"},
                    "business_label": {"type": "string",  "description": "Filter: Urgent | Risk | Blocked | Conflict | Info"},
                    "limit":          {"type": "integer", "description": "Max results (default 10)"},
                },
            },
        ),
        Tool(
            name="get_risk_items",
            description="Get emails/messages flagged as risky: Blocked, Urgent, Risk, Conflict, Overload.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days":  {"type": "integer", "description": "How many days back (default 7)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    from core.database import SessionLocal
    from core.models import MessageRaw

    db = SessionLocal()
    try:
        if name == "get_recent_emails":
            days           = arguments.get("days", 7)
            urgent_only    = arguments.get("urgent_only", False)
            business_label = arguments.get("business_label")
            limit          = arguments.get("limit", 10)

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
            result = {
                "emails": [
                    {
                        "id":              r.id,
                        "title":           r.title or "(sans titre)",
                        "author":          r.author,
                        "timestamp":       r.timestamp.isoformat() if r.timestamp else "",
                        "sentiment":       r.sentiment_label,
                        "business_label":  r.business_label,
                        "business_reason": r.business_reason,
                        "emotion":         r.emotion_label,
                        "excerpt":         (r.content or "")[:200],
                    }
                    for r in rows
                ],
                "count":       len(rows),
                "period_days": days,
            }

        elif name == "get_risk_items":
            days  = arguments.get("days", 7)
            limit = arguments.get("limit", 10)
            since = datetime.utcnow() - timedelta(days=days)

            rows = db.query(MessageRaw).filter(
                MessageRaw.timestamp >= since,
                MessageRaw.business_label.in_(["Blocked", "Urgent", "Risk", "Conflict", "Overload"]),
            ).order_by(MessageRaw.timestamp.desc()).limit(limit).all()

            result = {
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
                "count": len(rows),
            }
        else:
            result = {"error": f"Unknown tool: {name}"}

    finally:
        db.close()

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
