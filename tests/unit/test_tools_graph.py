from src.graph.workflow import _heuristic_plan, approve_answer, run_research
from src.mcp_server.client import call_local_tool, discover_local_tools
from src.tools.calculator import calculate
from src.tools.sql_agent import generate_sql


def test_calculator_is_safe_and_correct():
    assert calculate("(20 - 10) / 10") == 1
    import pytest
    with pytest.raises(ValueError):
        calculate("__import__('os').system('echo unsafe')")
    with pytest.raises(ValueError):
        calculate("(-1) ** 0.5")


def test_plan_routes_tools():
    assert "documents" in _heuristic_plan("What is the refund policy?").tasks
    assert "sql" in _heuristic_plan("What was quarterly revenue?").tasks
    assert "web" in _heuristic_plan("Research latest competitor news").tasks


def test_sql_agent_maps_supported_question():
    assert "AVG" in generate_sql("What is the average order value?")


def test_graph_gathers_evidence_and_waits_for_approval():
    state = run_research("What does the refund policy say about annual subscriptions?", thread_id="test-thread")
    assert state["evidence"]
    assert state["approval_status"] == "pending"
    approved = approve_answer(state, True)
    assert approved["approval_status"] == "approved"
    assert approved["final_answer"] == state["draft"]


def test_mcp_tools_are_discoverable_and_allowlisted():
    names = {item["name"] for item in discover_local_tools()}
    assert {"search_documents", "query_business_database", "calculate_metrics"} <= names
    assert call_local_tool("calculate_metrics", {"expression": "2*3"}) == 6
    import pytest
    with pytest.raises(KeyError):
        call_local_tool("arbitrary", {})


def test_revenue_decline_and_churn_use_internal_evidence():
    decline = set(_heuristic_plan("Why did revenue decline?").tasks)
    churn = set(_heuristic_plan("Analyze customer churn using our database and documents").tasks)
    assert {"sql", "documents"} <= decline
    assert {"sql", "documents"} <= churn


def test_report_tool_preserves_sources(tmp_path):
    from src.tools.report import report_generator
    report = report_generator("Quarterly Review", "Revenue was lower.", [{"content": "Synthetic total: 10", "metadata": {"source": "sample.sqlite"}}], tmp_path)
    body = report.read_text(encoding="utf-8")
    assert "Revenue was lower." in body
    assert "sample.sqlite" in body


def test_web_search_adapter_uses_provider_without_network(monkeypatch):
    import sys
    from types import SimpleNamespace
    from src.tools import web
    class FakeDDGS:
        def text(self, query, max_results):
            return [{"title": "Example", "href": "https://example.invalid", "body": query}]
    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    result = web.web_search("demo", 1)
    assert result[0]["title"] == "Example"
    assert result[0]["snippet"] == "demo"


def test_verifier_allows_only_one_optimizer_pass():
    from src.graph.workflow import _verification_route, _verify_node
    state = {"citations": [], "evidence": [{"content": "evidence"}], "revision_attempts": 0}
    first = _verify_node(state)
    assert _verification_route({**state, **first}) == "revise"
    second = _verify_node({**state, **first})
    assert _verification_route({**state, **first, **second}) == "approval"
