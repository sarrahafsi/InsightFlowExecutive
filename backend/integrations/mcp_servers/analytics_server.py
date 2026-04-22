"""
MCP Server — Analytics
=======================
Expose les KPIs, métriques et signaux burnout via le protocole MCP officiel.

Tools exposés :
  - get_analytics_summary : KPIs globaux, sentiment, vélocité
  - get_burnout_signals   : scores burnout, messages hors horaires
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

app = Server("analytics-insightflow")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_analytics_summary",
            description=(
                "Get quantitative KPIs and analytics: overall sentiment breakdown (% positive/neutral/negative), "
                "emotional climate score, team morale, message volume trends, topic distribution. "
                "Use this when asked about: team sentiment, general mood, morale, overall climate, "
                "how the team is feeling, sentiment statistics, or performance metrics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Analysis period in days (default 30)"},
                },
            },
        ),
        Tool(
            name="get_burnout_signals",
            description="Get team burnout signals: after-hours messages, weekend activity, high burnout scores.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days":      {"type": "integer", "description": "How many days back (default 14)"},
                    "threshold": {"type": "number",  "description": "Min burnout score 0-1 (default 0.5)"},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_analytics_summary":
        days = arguments.get("days", 7)
        try:
            from application.deps import item_store
            from data.analytics.engine import compute_overview
            items    = item_store.get_recent(days=days)
            overview = compute_overview(items) if items else {}
            result   = {
                "analytics":   overview,
                "period_days": days,
                "total_items": len(items) if items else 0,
            }
        except Exception as e:
            result = {"error": str(e), "days": days}

    elif name == "get_burnout_signals":
        days      = arguments.get("days", 14)
        threshold = arguments.get("threshold", 0.5)
        from core.database import SessionLocal
        from core.models import MessageRaw
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows  = db.query(MessageRaw).filter(
                MessageRaw.timestamp >= since,
                MessageRaw.burnout_score >= threshold,
            ).order_by(MessageRaw.burnout_score.desc()).limit(15).all()

            result = {
                "burnout_signals": [
                    {
                        "id":             r.id,
                        "author":         r.author,
                        "source":         r.source,
                        "timestamp":      r.timestamp.isoformat() if r.timestamp else "",
                        "burnout_score":  round(r.burnout_score or 0, 2),
                        "is_after_hours": r.is_after_hours,
                        "is_weekend":     r.is_weekend,
                        "title":          r.title or "",
                    }
                    for r in rows
                ],
                "count":     len(rows),
                "threshold": threshold,
            }
        finally:
            db.close()

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
