"""Optional LangSmith tracing setup."""
from __future__ import annotations

import os

from src.config.settings import settings


def configure_langsmith() -> bool:
    """Enable LangSmith only when the user configured credentials and tracing."""
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return False
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    return True


def trace_metadata(thread_id: str) -> dict[str, str]:
    """Return safe run metadata for a graph invocation."""
    return {"thread_id": thread_id, "project": settings.langsmith_project}
