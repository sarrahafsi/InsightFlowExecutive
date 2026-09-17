"""
MCP Server — Knowledge Base (ChromaDB RAG)
==========================================
Appelle le backend FastAPI via HTTP pour la recherche sémantique.
Évite de charger sentence-transformers dans le subprocess (trop lent).

Tools exposés :
  - search_knowledge_base : recherche vectorielle dans tous les messages
"""
import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("knowledge-insightflow")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_knowledge_base",
            description=(
                "Search semantically across all messages (Gmail, Slack, Jira) "
                "using vector similarity. Best for broad or vague questions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query":         {"type": "string",  "description": "Search query in natural language"},
                    "top_k":         {"type": "integer", "description": "Number of results (default 5)"},
                    "source_filter": {"type": "string",  "description": "Filter: gmail | slack | jira"},
                },
                "required": ["query"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search_knowledge_base":
        query         = arguments.get("query", "")
        top_k         = int(arguments.get("top_k", 5))
        source_filter = arguments.get("source_filter")

        # org_id/since_date injectés par le backend juste avant l'appel —
        # jamais laissés au LLM à fournir (cf. gmail_server.py, même incident).
        org_id     = arguments.get("_org_id")
        since_date = arguments.get("_since_date")
        if not org_id:
            result = {"error": "org_id manquant", "results": [], "count": 0}
        else:
            try:
                payload: dict = {"query": query, "top_k": top_k, "org_id": org_id}
                if source_filter:
                    payload["source_filter"] = source_filter
                if since_date:
                    payload["since_date"] = since_date

                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(
                        f"{BACKEND_URL}/api/search/rag",
                        json=payload,
                        headers={"X-Internal-Secret": os.environ.get("ASK_INTERNAL_SECRET", "")},
                    )
                    resp.raise_for_status()
                    result = resp.json()
            except Exception as e:
                result = {"error": str(e), "results": [], "count": 0}
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
