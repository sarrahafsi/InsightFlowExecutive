"""
LLM Client — InsightFlow Executive
=====================================
Client unifié avec vrai protocole MCP (SDK officiel Anthropic).

Optimisation : chaque MCP server est démarré une seule fois (session stdio
persistante gardée ouverte pour toute la durée de vie du backend, cf.
start_mcp_sessions/close_mcp_sessions) — pas de sous-processus par tool call.

Modes :
  LLM_PROVIDER=ollama  → Ollama local, gratuit, sans MCP tools
  LLM_PROVIDER=openai  → OpenAI ChatGPT (gpt-4o, gpt-4-turbo, etc.)
  LLM_PROVIDER=azure   → Azure GPT-4o + vrais MCP Servers (JSON-RPC stdio)
"""
from __future__ import annotations

import asyncio
import contextlib
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

# Sessions MCP persistantes : un sous-processus par serveur, réutilisé pour
# tous les appels (au lieu d'en relancer un par tool call — c'était le
# principal goulot d'étranglement de "Ask Anything").
_sessions: dict[str, Any] = {}
_session_locks: dict[str, asyncio.Lock] = {}
_exit_stack: contextlib.AsyncExitStack | None = None


def reset_tool_cache() -> None:
    global _cached_tools, _tool_to_server
    _cached_tools   = None
    _tool_to_server = {}


def _get_lock(server_name: str) -> asyncio.Lock:
    if server_name not in _session_locks:
        _session_locks[server_name] = asyncio.Lock()
    return _session_locks[server_name]


async def _get_session(server_name: str):
    """Retourne la session MCP persistante pour ce serveur (la crée si besoin)."""
    global _exit_stack

    if server_name in _sessions:
        return _sessions[server_name]

    server_path = MCP_SERVERS.get(server_name)
    if not server_path or not server_path.exists():
        return None

    async with _get_lock(server_name):
        if server_name in _sessions:  # créée entre-temps par une autre requête
            return _sessions[server_name]

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if _exit_stack is None:
            _exit_stack = contextlib.AsyncExitStack()

        try:
            env = {**os.environ, "ASK_INTERNAL_SECRET": settings.secret_key}
            params = StdioServerParameters(command=PYTHON_EXE, args=[str(server_path)], env=env)
            read, write = await _exit_stack.enter_async_context(stdio_client(params))
            session = await _exit_stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=10.0)
            _sessions[server_name] = session
            logger.info("[MCP] Session démarrée pour %s", server_name)
            return session
        except BaseException as e:
            logger.error("[MCP] Échec démarrage serveur %s: %s", server_name, e)
            return None


def _drop_session(server_name: str) -> None:
    """Invalide une session cassée — sera recréée au prochain appel."""
    _sessions.pop(server_name, None)


async def start_mcp_sessions() -> None:
    """Démarre tous les serveurs MCP une fois, au boot du backend."""
    for server_name in MCP_SERVERS:
        await _get_session(server_name)
    await _get_tools()  # préchauffe aussi le cache des tool schemas
    logger.info("[MCP] %d serveur(s) MCP prêt(s), %d tool(s) disponibles", len(_sessions), len(_cached_tools or []))


async def close_mcp_sessions() -> None:
    """À appeler à l'arrêt du backend pour fermer proprement les sous-processus MCP."""
    global _exit_stack
    if _exit_stack is not None:
        await _exit_stack.aclose()
        _exit_stack = None
    _sessions.clear()


# ── Public interface ──────────────────────────────────────────────────────────

async def complete(
    system: str,
    user: str,
    use_tools: bool = True,
    db=None,
    temperature: float = 0.3,
    max_tokens: int = 600,
    provider: str | None = None,
    org_id: str | None = None,
    since_date: str | None = None,
) -> str:
    p = (provider or settings.llm_provider).lower()
    if p == "azure":
        return await _complete_azure_mcp(system, user, use_tools, temperature, max_tokens, org_id, since_date)
    if p in ("openai", "gpt"):
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
    """Discover tools from the persistent MCP sessions and cache them."""
    global _cached_tools, _tool_to_server

    if _cached_tools is not None:
        return _cached_tools, _tool_to_server

    all_tools: list[dict] = []
    tool_map: dict[str, str] = {}

    for server_name in MCP_SERVERS:
        session = await _get_session(server_name)
        if session is None:
            continue
        try:
            tools_response = await asyncio.wait_for(session.list_tools(), timeout=10.0)
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
            logger.error("[MCP] Failed to list tools from %s: %s", server_name, e)
            _drop_session(server_name)

    _cached_tools   = all_tools
    _tool_to_server = tool_map
    logger.info("[MCP] %d tools cached from %d servers", len(all_tools), len(MCP_SERVERS))
    return _cached_tools, _tool_to_server


async def _call_mcp_tool(
    server_name: str, tool_name: str, arguments: dict,
    org_id: str | None = None, since_date: str | None = None,
) -> str:
    """Execute a tool on its (persistent) MCP session.

    org_id/since_date sont injectés directement dans les arguments juste avant
    l'appel (jamais laissés au LLM à fournir) : chaque serveur MCP DOIT filtrer
    par org_id lui-même — sinon un CEO voit les données de toutes les
    organisations (cf. incident 03/09/2026, aucun des 4 serveurs ne filtrait
    par org). Passés en argument plutôt qu'en variable d'environnement du
    sous-processus, car la session est maintenant partagée entre requêtes et
    organisations — un env var figé au démarrage du process ne conviendrait
    plus."""
    call_args = {**arguments, "_org_id": org_id, "_since_date": since_date}

    async def _attempt() -> str | None:
        session = await _get_session(server_name)
        if session is None:
            return None
        result = await asyncio.wait_for(session.call_tool(tool_name, call_args), timeout=15.0)
        if result.content:
            return result.content[0].text
        return json.dumps({"result": "ok"})

    try:
        result = await _attempt()
        if result is not None:
            return result
        return json.dumps({"error": f"MCP server '{server_name}' unavailable"})
    except asyncio.TimeoutError:
        logger.warning("[MCP] Timeout calling %s.%s", server_name, tool_name)
        return json.dumps({"error": f"timeout calling {tool_name}"})
    except BaseException as e:
        logger.error("[MCP] Tool call failed %s.%s: %s — reconnecting", server_name, tool_name, e)
        _drop_session(server_name)
        try:
            result = await _attempt()
            return result if result is not None else json.dumps({"error": "mcp tool error"})
        except BaseException as e2:
            logger.error("[MCP] Retry failed %s.%s: %s", server_name, tool_name, e2)
            return json.dumps({"error": "mcp tool error"})


# ── Azure GPT-4o + MCP ────────────────────────────────────────────────────────

async def _complete_azure_mcp(
    system: str,
    user: str,
    use_tools: bool,
    temperature: float,
    max_tokens: int,
    org_id: str | None = None,
    since_date: str | None = None,
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
            result = await _call_mcp_tool(server_name, tool_name, tool_args, org_id, since_date)
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
    # Ollama sur CPU est lent — cap à 400 tokens et timeout généreux
    ollama_tokens = min(max_tokens, 400)
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url.rstrip('/v1')}/api/generate",
                json={
                    "model":   settings.ollama_model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": ollama_tokens,
                        "num_gpu":     0,   # CPU-only — prevents GPU VRAM crash on laptops
                    },
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except httpx.ConnectError:
        return "Ollama n'est pas démarré. Lance `ollama serve` dans un terminal puis réessaie."
    except httpx.TimeoutException:
        logger.error("[LLM/Ollama] Timeout — modèle trop lent sur CPU")
        return "Ollama a mis trop de temps à répondre. Réessaie dans quelques secondes."
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500]
        logger.error("[LLM/Ollama] HTTP %s — %s", e.response.status_code, body)
        return f"Erreur Ollama ({e.response.status_code}) : {body}"
    except Exception as e:
        logger.error("[LLM/Ollama] Erreur inattendue : %s", e)
        return f"Erreur Ollama : {e}"
