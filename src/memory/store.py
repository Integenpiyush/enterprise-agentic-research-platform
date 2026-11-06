"""SQLite-backed conversation history and long-term user preference memory."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import settings


class MemoryStore:
    """Separate durable conversation/preferences storage from graph checkpoints."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else settings.resolve(settings.memory_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_thread ON conversations(user_id, thread_id, id);
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                    preference TEXT NOT NULL, value TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(user_id, preference)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def add_message(self, user_id: str, thread_id: str, role: str, content: str) -> None:
        """Persist one user/assistant message."""
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        with self._connect() as conn:
            conn.execute("INSERT INTO conversations(user_id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                         (user_id, thread_id, role, content, datetime.now(timezone.utc).isoformat()))

    def history(self, user_id: str, thread_id: str, limit: int = 20) -> list[dict[str, str]]:
        """Load recent short-term history for a conversation thread."""
        with self._connect() as conn:
            rows = conn.execute("SELECT role, content FROM conversations WHERE user_id=? AND thread_id=? ORDER BY id DESC LIMIT ?", (user_id, thread_id, limit)).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def save_preference(self, user_id: str, preference: str, value: Any) -> None:
        """Upsert one explicit preference as JSON."""
        with self._connect() as conn:
            conn.execute("INSERT INTO preferences(user_id, preference, value, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, preference) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                         (user_id, preference, json.dumps(value), datetime.now(timezone.utc).isoformat()))

    def preferences(self, user_id: str) -> dict[str, Any]:
        """Read persisted user preferences."""
        with self._connect() as conn:
            rows = conn.execute("SELECT preference, value FROM preferences WHERE user_id=?", (user_id,)).fetchall()
        return {key: json.loads(value) for key, value in rows}

    def relevant_memories(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Retrieve preference entries with lexical overlap against the current query."""
        words = {word.casefold() for word in query.split() if len(word) > 2}
        preferences = self.preferences(user_id)
        ranked = []
        for key, value in preferences.items():
            haystack = f"{key} {value}".casefold()
            score = sum(word in haystack for word in words)
            if score:
                ranked.append((score, {"preference": key, "value": str(value)}))
        return [item for _, item in sorted(ranked, key=lambda row: row[0], reverse=True)[:limit]]

    def clear_user(self, user_id: str) -> None:
        """Delete conversation and preference data for a user."""
        with self._connect() as conn:
            conn.execute("DELETE FROM conversations WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM preferences WHERE user_id=?", (user_id,))


def clear_checkpoint_thread(thread_id: str, path: str | Path | None = None) -> int:
    """Delete LangGraph checkpoint rows for one thread, when the checkpoint schema exists."""
    checkpoint_path = Path(path) if path else settings.resolve(settings.checkpoint_db_path)
    if not checkpoint_path.exists():
        return 0
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        with sqlite3.connect(checkpoint_path, timeout=5, check_same_thread=False) as conn:
            SqliteSaver(conn).delete_thread(thread_id)
        return 1
    except ImportError:
        pass
    deleted = 0
    with sqlite3.connect(checkpoint_path, timeout=5) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("writes", "checkpoints"):
            if table not in tables:
                continue
            deleted += max(0, conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,)).rowcount)
    return deleted
