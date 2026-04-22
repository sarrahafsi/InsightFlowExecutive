"""
MCP Server — Jira
=================
Expose les tickets Jira depuis PostgreSQL via le protocole MCP officiel.

Tools exposés :
  - get_jira_tickets : tickets filtrables par status/priorité
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("jira-insightflow")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_jira_tickets",
            description="Get Jira tickets from the database, filterable by status or priority.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter: open | done | blocked"},
                    "days":   {"type": "integer", "description": "How many days back (default 30)"},
                    "limit":  {"type": "integer", "description": "Max results (default 10)"},
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
        if name == "get_jira_tickets":
            status = arguments.get("status")
            days   = arguments.get("days", 30)
            limit  = arguments.get("limit", 10)
            since  = datetime.utcnow() - timedelta(days=days)

            q = db.query(MessageRaw).filter(
                MessageRaw.source == "jira",
                MessageRaw.timestamp >= since,
            )
            if status == "blocked":
                q = q.filter(MessageRaw.business_label == "Blocked")
            elif status == "open":
                q = q.filter(MessageRaw.business_label != "Done")

            rows = q.order_by(MessageRaw.timestamp.desc()).limit(limit).all()
            result = {
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
