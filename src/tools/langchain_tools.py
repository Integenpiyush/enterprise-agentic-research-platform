"""Typed LangChain tool adapters; functions remain importable without LangChain."""
from __future__ import annotations

from src.database.sqlite import execute_sql
from src.retrieval.store import document_search
from src.tools.calculator import calculate
from src.tools.report import report_generator
from src.tools.sql_agent import query_business_data
from src.tools.web import company_research, web_search

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(*args, **kwargs):
        def decorate(func):
            return func
        return decorate


@tool
def search_business_documents(query: str) -> list[dict]:
    """Search internal policy, product, security, and company documents. Return cited passages."""
    return document_search(query)


@tool
def execute_business_sql(query: str) -> dict:
    """Execute a validated read-only SELECT against the synthetic business database."""
    return execute_sql(query)


@tool
def calculate_expression(expression: str) -> float | int:
    """Calculate basic arithmetic expressions such as (revenue_a - revenue_b) / revenue_b."""
    return calculate(expression)


@tool
def search_public_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search public web pages for current external context; always verify sources."""
    return web_search(query, max_results)


@tool
def research_company(company: str) -> list[dict[str, str]]:
    """Find public company overview, product, leadership, and news sources."""
    return company_research(company)


@tool
def create_research_report(title: str, answer: str, evidence: list[dict]) -> str:
    """Save an evidence-backed Markdown research report and return its local path."""
    return str(report_generator(title, answer, evidence))


ALL_TOOLS = [search_business_documents, execute_business_sql, calculate_expression, search_public_web, research_company, create_research_report]
