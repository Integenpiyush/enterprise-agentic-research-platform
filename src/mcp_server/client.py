"""MCP client discovery and local tool adapters."""
from __future__ import annotations

import asyncio
from typing import Any

from src.database.sqlite import execute_sql
from src.retrieval.store import document_search
from src.tools.calculator import calculate
from src.tools.sql_agent import query_business_data

LOCAL_TOOLS = {
    "search_documents": document_search,
    "query_business_database": query_business_data,
    "calculate_metrics": calculate,
}


def discover_local_tools() -> list[dict[str, str]]:
    """Discover server tools through FastMCP's in-process MCP client."""
    try:
        from fastmcp import Client
        from src.mcp_server.server import mcp
        async def list_names() -> list[Any]:
            async with Client(mcp) as client:
                return await client.list_tools()
        tools = asyncio.run(list_names())
        return [{"name": item.name, "description": item.description or ""} for item in tools]
    except (ImportError, RuntimeError, AttributeError):
        # Minimal test environments can still inspect and invoke the allow-listed adapters.
        return [{"name": name, "description": function.__doc__ or ""} for name, function in LOCAL_TOOLS.items()]


def call_local_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Invoke an allow-listed tool through FastMCP's in-process client when available."""
    if name not in LOCAL_TOOLS:
        raise KeyError(f"MCP tool is not allow-listed: {name}")
    try:
        from fastmcp import Client
        from src.mcp_server.server import mcp
        async def invoke() -> Any:
            async with Client(mcp) as client:
                discovered = {item.name for item in await client.list_tools()}
                if name not in discovered:
                    raise KeyError(f"MCP server did not expose {name}")
                result = await client.call_tool(name, arguments)
                if getattr(result, "is_error", False):
                    raise RuntimeError(f"MCP tool {name} reported an error")
                if hasattr(result, "data"):
                    return result.data
                structured = getattr(result, "structured_content", None)
                if structured is not None:
                    return structured
                return result
        return asyncio.run(invoke())
    except ImportError:
        # Import-free adapter fallback keeps local tests usable before dependencies are installed.
        if name == "search_documents":
            return document_search(arguments["query"], k=int(arguments.get("limit", 5)))
        if name == "query_business_database":
            return query_business_data(arguments["question"])
        if name == "calculate_metrics":
            return calculate(arguments["expression"])
        raise KeyError(name)
