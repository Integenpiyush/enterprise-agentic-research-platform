"""FastMCP server exposing document, business SQL, and calculation tools."""
from __future__ import annotations

from fastmcp import FastMCP

from src.database.sqlite import execute_sql
from src.retrieval.store import document_search
from src.tools.calculator import calculate
from src.tools.sql_agent import query_business_data

mcp = FastMCP("Enterprise Research Platform")


@mcp.tool
async def search_documents(query: str, limit: int = 5) -> list[dict]:
    """Search indexed and bundled business documents, returning passages and source metadata."""
    return document_search(query, k=limit)


@mcp.tool
async def query_business_database(question: str) -> dict:
    """Answer a business analytics question with a validated read-only SQLite query."""
    return query_business_data(question)


@mcp.tool
async def calculate_metrics(expression: str) -> float | int:
    """Evaluate a basic arithmetic expression over previously obtained business metrics."""
    return calculate(expression)


def main() -> None:
    """Run the MCP server over stdio for local MCP-compatible clients."""
    mcp.run()


if __name__ == "__main__":
    main()
