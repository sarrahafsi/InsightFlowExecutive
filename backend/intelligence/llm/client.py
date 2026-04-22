"""
LLM Client — InsightFlow Executive
=====================================
Client unifié avec vrai protocole MCP (SDK officiel Anthropic).

Optimisation : les MCP servers sont démarrés une seule fois au premier appel
et les tool schemas sont mis en cache — pas de subprocess par requête.

Modes :
  LLM_PROVIDER=ollama  → Ollama local, gratuit, sans MCP tools
  LLM_PROVIDER=openai  → OpenAI ChatGPT (gpt-4o, gpt-4-turbo, etc.)
  LLM_PROVIDER=azure   → Azure GPT-4o + vrais MCP Servers (JSON-RPC stdio)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from core.config import settings

logger = logging.getLogger(__name__)

SERVERS_DIR = Path(__file__).resolve().parent.parent.parent / "integrations" / "mcp_servers"
PYTHON_EXE  = sys.executable
MAX_TOOL_ITERATIONS = 5

MCP_SERVERS = {
    "gmail":      SERVERS_DIR / "gmail_server.py",
    "jira":       SERVERS_DIR / "jira_server.py",
    "analytics":  SERVERS_DIR / "analytics_server.py",
    "knowledge":  SERVERS_DIR / "knowledge_server.py",
}

# Cache : tool schemas découverts une seule fois par process
_cached_tools: list[dict] | None = None
_tool_to_server: dict[str, str] = {}


def reset_tool_cache() -> None:
    global _cached_tools, _tool_to_server
    _cached_tools   = None
    _tool_to_server = {}


# ── Public interface ──────────────────────────────────────────────────────────

async def complete(
    system: str,
    user: str,
    use_tools: bool = True,
    db=None,
    temperature: float = 0.3,
    max_tokens: int = 600,
) -> str:
    provider = settings.llm_provider.lower()
    if provider == "azure":
        return await _complete_azure_mcp(system, user, use_tools, temperature, max_tokens)
    if provider == "openai":
        return await _complete_openai(system, user, temperature, max_tokens)
    return await _complete_ollama(system, user, temperature, max_tokens)


def get_provider_info() -> dict:
    provider = settings.llm_provider.lower()
    if provider == "azure":
        return {
            "provider": "azure",
            "model":    settings.azure_openai_deployment,
            "mode":     "premium",
            "tools":    True,
            "mcp":      True,
        }
    if provider == "openai":
        return {
            "provider": "openai",
            "model":    settings.openai_model,
            "mode":     "cloud",
            "tools":    False,
            "mcp":      False,
        }
    return {
        "provider": "ollama",
        "model":    settings.ollama_model,
        "mode":     "local",
        "tools":    False,
        "mcp":      False,
    }


# ── Tool discovery (cached) ───────────────────────────────────────────────────

async def _get_tools() -> tuple[list[dict], dict[str, str]]:
    """Discover tools from MCP servers once and cache them."""
    global _cached_tools, _tool_to_server

    if _cached_tools is not None:
        return _cached_tools, _tool_to_server

    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    all_tools: list[dict] = []
    tool_map: dict[str, str] = {}

    for server_name, server_path in MCP_SERVERS.items():
        if not server_path.exists():
            continue
        try:
            params = StdioServerParameters(
                command=PYTHON_EXE,
                args=[str(server_path)],
                env={**os.environ},
            )
            async def _discover(params=params, server_name=server_name):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.list_tools()

            tools_response = await asyncio.wait_for(_discover(), timeout=10.0)
            for tool in tools_response.tools:
                all_tools.append({
                    "type": "function",
                    "function": {
                        "name":        tool.name,
                        "description": tool.description or "",
                        "parameters":  tool.inputSchema,
                    },
                })
                tool_map[tool.name] = server_name
                logger.info("[MCP] Tool cached: %s (from %s)", tool.name, server_name)
        except BaseException as e:
            if isinstance(e, BaseExceptionGroup):
                for sub in e.exceptions:
                    logger.error("[MCP] Failed to load tools from %s: %s", server_name, sub)
            else:
                logger.error("[MCP] Failed to load tools from %s: %s", server_name, e)

    _cached_tools   = all_tools
    _tool_to_server = tool_map
    logger.info("[MCP] %d tools cached from %d servers", len(all_tools), len(MCP_SERVERS))
    return _cached_tools, _tool_to_server


async def _call_mcp_tool(server_name: str, tool_name: str, arguments: dict) -> str:
    """Execute a tool on its MCP server via JSON-RPC stdio."""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_path = MCP_SERVERS.get(server_name)
    if not server_path or not server_path.exists():
        return json.dumps({"error": f"MCP server '{server_name}' not found"})

    async def _run():
        params = StdioServerParameters(
            command=PYTHON_EXE,
            args=[str(server_path)],
            env={**os.environ},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.content:
                    return result.content[0].text
                return json.dumps({"result": "ok"})

    try:
        return await asyncio.wait_for(_run(), timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning("[MCP] Timeout calling %s.%s", server_name, tool_name)
        return json.dumps({"error": f"timeout calling {tool_name}"})
    except BaseException as e:
        if isinstance(e, BaseExceptionGroup):
            for sub in e.exceptions:
                logger.error("[MCP] Tool call failed %s.%s: %s", server_name, tool_name, sub)
        else:
            logger.error("[MCP] Tool call failed %s.%s: %s", server_name, tool_name, e)
        return json.dumps({"error": "mcp tool error"})


# ── Azure GPT-4o + MCP ────────────────────────────────────────────────────────

async def _complete_azure_mcp(
    system: str,
    user: str,
    use_tools: bool,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        from openai import AsyncAzureOpenAI
    except ImportError:
        return "Erreur : package openai manquant."

    if not settings.azure_openai_key or not settings.azure_openai_endpoint:
        return "Erreur : credentials Azure OpenAI manquants dans le .env."

    azure = AsyncAzureOpenAI(
        api_key=settings.azure_openai_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        timeout=60.0,
    )

    if not use_tools:
        response = await azure.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    # Récupère les tools (depuis le cache si disponible)
    all_tools, tool_to_server = await _get_tools()

    if not all_tools:
        logger.warning("[MCP] No tools available — falling back to no-tool mode")
        response = await azure.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await azure.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=messages,
            tools=all_tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append({
            "role":       "assistant",
            "content":    msg.content,
            "tool_calls": [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Exécute tous les tool calls en parallèle
        import asyncio
        async def run_tool(tc):
            tool_name   = tc.function.name
            server_name = tool_to_server.get(tool_name, "")
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}
            logger.info("[MCP] GPT-4o calls: %s(%s)", tool_name, tool_args)
            result = await _call_mcp_tool(server_name, tool_name, tool_args)
            return tc.id, result

        results = await asyncio.gather(*[run_tool(tc) for tc in msg.tool_calls])

        for tool_call_id, result in results:
            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call_id,
                "content":      result,
            })

    final = await azure.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return final.choices[0].message.content or ""


# ── OpenAI ChatGPT ───────────────────────────────────────────────────────────

async def _complete_openai(
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return "Erreur : package openai manquant. Lance : pip install openai"

    if not settings.openai_api_key:
        return "Erreur : OPENAI_API_KEY manquant dans le .env."

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=60.0)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("[LLM/OpenAI] Erreur : %s", e)
        return f"Erreur OpenAI : {e}"


# ── Ollama local ──────────────────────────────────────────────────────────────

async def _complete_ollama(
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    prompt = f"{system}\n\n{user}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url.rstrip('/v1')}/api/generate",
                json={
                    "model":   settings.ollama_model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except httpx.ConnectError:
        return "Ollama n'est pas démarré. Lance `ollama serve` dans un terminal puis réessaie."
    except Exception as e:
        logger.error("[LLM/Ollama] Erreur : %s", e)
        return f"Erreur Ollama : {e}"
