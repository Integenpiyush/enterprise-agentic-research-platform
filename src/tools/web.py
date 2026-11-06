"""Optional public web search using the DuckDuckGo Search package."""
from __future__ import annotations

from typing import Any


def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search public web results. Returns a clear setup error if provider is unavailable."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("Web search requires the optional ddgs package; install project requirements.") from exc
    try:
        results = DDGS().text(query, max_results=max_results)
        return [{"title": str(item.get("title", "")), "url": str(item.get("href", "")), "snippet": str(item.get("body", ""))} for item in results]
    except Exception as exc:
        raise RuntimeError(f"Web search failed: {exc}") from exc


def company_research(company: str, max_results: int = 5) -> list[dict[str, str]]:
    """Research a company using public search results; results remain unverified evidence."""
    if not company.strip():
        raise ValueError("Company name is required")
    return web_search(f"{company.strip()} company products leadership latest news", max_results)
