"""Natural-language SQL helper with strict validation before database execution."""
from __future__ import annotations

from typing import Any

from src.config.settings import settings
from src.database.sqlite import execute_sql, schema_description


def _heuristic_sql(question: str) -> str:
    """Map common demo analytics questions to safe parameter-free SELECT queries."""
    q = question.lower()
    if "average order value" in q or "avg order" in q:
        return "SELECT AVG(total_amount) AS average_order_value FROM orders WHERE status = 'completed'"
    if "revenue" in q and any(term in q for term in ("last quarter", "previous quarter", "q3", "third quarter")):
        return "SELECT SUM(total_amount) AS revenue FROM orders WHERE status = 'completed' AND order_date >= '2026-07-01' AND order_date < '2026-10-01'"
    if "revenue" in q and any(term in q for term in ("q4", "fourth quarter")):
        return "SELECT SUM(total_amount) AS revenue FROM orders WHERE status = 'completed' AND order_date >= '2026-10-01' AND order_date < '2027-01-01'"
    if "revenue" in q or "sales" in q:
        return "SELECT strftime('%Y-%m', order_date) AS month, SUM(total_amount) AS revenue FROM orders WHERE status = 'completed' GROUP BY month ORDER BY month"
    if "churn" in q or "active customer" in q:
        return "SELECT is_active, COUNT(*) AS customers FROM customers GROUP BY is_active"
    if "ticket" in q or "support" in q:
        return "SELECT category, status, COUNT(*) AS ticket_count FROM support_tickets GROUP BY category, status ORDER BY ticket_count DESC"
    if "customer" in q:
        return "SELECT segment, region, COUNT(*) AS customer_count FROM customers GROUP BY segment, region"
    raise ValueError("I couldn't map this question to a safe sample query. Try asking about revenue, order value, customers, or support tickets.")


def generate_sql(question: str) -> str:
    """Generate SQL with an optional structured LangChain model, then fall back to rules."""
    if not question.strip():
        raise ValueError("Question is required")
    if settings.openai_api_key:
        try:
            from src.chains.research import build_sql_chain
            generated = build_sql_chain().invoke({"schema": schema_description(), "question": question}).strip()
            generated = generated.removeprefix("```sql").removesuffix("```").strip()
            return generated
        except Exception:
            # Keep the no-key/synthetic workflow operational if the provider is unavailable.
            pass
    return _heuristic_sql(question)


def query_business_data(question: str) -> dict[str, Any]:
    """Generate and execute a bounded SELECT. Return both query and result."""
    sql = generate_sql(question)
    result = execute_sql(sql)
    result["explanation"] = f"Read-only query generated for: {question}"
    return result
