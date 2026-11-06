"""Read-only SQLite access and conservative SELECT validation."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from src.config.settings import settings

BLOCKED = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|VACUUM|PRAGMA|REINDEX|ANALYZE|TRIGGER)\b", re.IGNORECASE)


class SQLValidationError(ValueError):
    """Raised when a query is outside the read-only SELECT policy."""


def validate_select_sql(sql: str) -> str:
    """Validate one read-only SELECT statement; reject comments and multiple statements."""
    query = sql.strip()
    if not query:
        raise SQLValidationError("SQL query is empty.")
    if "--" in query or "/*" in query or "*/" in query:
        raise SQLValidationError("SQL comments are not permitted.")
    if query.endswith(";"):
        query = query[:-1].rstrip()
    if ";" in query:
        raise SQLValidationError("Only one SQL statement is allowed.")
    if BLOCKED.search(query):
        raise SQLValidationError("Only read-only SELECT statements are permitted.")
    if not re.match(r"^(SELECT|WITH)\b", query, re.IGNORECASE):
        raise SQLValidationError("Only SELECT queries are permitted.")
    try:
        import sqlglot
        statements = sqlglot.parse(query, read="sqlite")
        if len(statements) != 1 or statements[0] is None:
            raise SQLValidationError("Only one SQL statement is allowed.")
        node = statements[0]
        # Expression.key is lowercase in current sqlglot releases. Normalize it
        # so read-only SELECT validation behaves consistently across versions.
        node_kind = str(node.key).upper()
        if not (node_kind == "SELECT" or node_kind == "UNION" or (node_kind == "WITH" and node.find(sqlglot.exp.Select))):
            raise SQLValidationError("Only SELECT queries are permitted.")
    except ImportError:
        if re.match(r"^WITH\b", query, re.IGNORECASE) and not re.search(r"\bSELECT\b", query, re.IGNORECASE):
            raise SQLValidationError("WITH queries must contain a SELECT statement.")
    except SQLValidationError:
        raise
    except Exception as exc:
        raise SQLValidationError(f"SQL could not be parsed: {exc}") from exc
    return query


def connect_readonly(path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite database in URI read-only mode."""
    db_path = Path(path) if path else settings.resolve(settings.sqlite_db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Business database not found at {db_path}. Run python data/seed_database.py.")
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def execute_sql(sql: str, path: str | Path | None = None, max_rows: int | None = None) -> dict[str, Any]:
    """Validate and run a SELECT, returning columns, rows, count, and safe explanation."""
    query = validate_select_sql(sql)
    row_cap = max_rows if max_rows is not None else settings.max_sql_rows
    if row_cap < 1:
        raise ValueError("max_rows must be positive")
    wrapped = f"SELECT * FROM ({query}) AS limited_result LIMIT {int(row_cap)}"
    with connect_readonly(path) as conn:
        progress = {"steps": 0}
        def limit_query_steps() -> int:
            progress["steps"] += 1
            return int(progress["steps"] > 50_000)
        conn.set_progress_handler(limit_query_steps, 1_000)
        cursor = conn.execute(wrapped)
        rows = [dict(row) for row in cursor.fetchall()]
        columns = [item[0] for item in cursor.description or []]
    return {"sql": query, "columns": columns, "rows": rows, "row_count": len(rows), "row_limit": row_cap}


def schema_description(path: str | Path | None = None) -> str:
    """Return table/column names without exposing database credentials."""
    with connect_readonly(path) as conn:
        tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return "\n".join(row["sql"] or row["name"] for row in tables)
