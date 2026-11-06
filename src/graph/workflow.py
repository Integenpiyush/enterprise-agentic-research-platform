"""Evidence-first LangGraph workflow with bounded retries and approval pause."""
from __future__ import annotations

import operator
import os
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated, Any, TypedDict

from src.agents.schemas import ResearchAnswer, ResearchPlan
from src.config.settings import settings
from src.chains.research import build_answer_chain, build_planning_chain
from src.database.sqlite import schema_description
from src.mcp_server.client import call_local_tool
from src.retrieval.store import document_search
from src.tools.calculator import calculate
from src.tools.sql_agent import generate_sql
from src.tools.web import web_search

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args: Any, **kwargs: Any):
        def decorate(function: Any) -> Any:
            return function
        return decorate


class ResearchState(TypedDict, total=False):
    """Graph state. Append-only event lists use reducers; decision fields overwrite."""
    query: str
    thread_id: str
    history: list[dict[str, str]]
    memories: list[dict[str, str]]
    plan: list[str]
    plan_rationale: str
    retrieval_query: str
    evidence: Annotated[list[dict[str, Any]], operator.add]
    tool_events: Annotated[list[dict[str, Any]], operator.add]
    retry_count: int
    sufficient_evidence: bool
    needs_retry: bool
    draft: str
    citations: list[int]
    limitations: list[str]
    confidence: float
    verification: list[str]
    verification_feedback: str
    revision_attempts: int
    approval_status: str
    approved: bool
    review_feedback: str
    final_answer: str
    errors: Annotated[list[str], operator.add]


_ALLOWED_TASKS = {"documents", "sql", "web", "calculator", "mcp"}


def _heuristic_plan(query: str) -> ResearchPlan:
    q = query.lower()
    tasks: list[str] = []
    if any(word in q for word in ("revenue", "sales", "order", "churn", "customer", "ticket", "database", "sql", "quarter")):
        tasks.append("sql")
    if any(word in q for word in ("policy", "refund", "document", "guide", "security", "support", "risk", "report", "company", "compare", "churn", "decline", "why", "cause")) or not tasks:
        tasks.append("documents")
    if any(word in q for word in ("research", "market", "competitor", "latest", "web", "external", "compare")):
        tasks.append("web")
    if any(word in q for word in ("calculate", "percentage", "percent", "growth", "difference", "average")):
        tasks.append("calculator")
    # MCP is selected when the user explicitly requests the protocol-backed tool path.
    if "mcp" in q:
        tasks.append("mcp")
    return ResearchPlan(tasks=list(dict.fromkeys(tasks)), rationale="Selected tools from the information needs in the question.")


def _plan_node(state: ResearchState) -> dict[str, Any]:
    query = state.get("query", "")
    plan = _heuristic_plan(query)
    if settings.openai_api_key:
        try:
            candidate = build_planning_chain().invoke({"query": query, "schema": schema_description()})
            safe_tasks = [task for task in candidate.tasks if task in _ALLOWED_TASKS]
            if safe_tasks:
                plan = ResearchPlan(tasks=list(dict.fromkeys(safe_tasks)), rationale=candidate.rationale)
        except Exception:
            # The deterministic plan keeps non-LLM workflows available during provider issues.
            pass
    return {"plan": plan.tasks, "plan_rationale": plan.rationale, "retry_count": state.get("retry_count", 0)}


def _query_analyzer_node(state: ResearchState) -> dict[str, Any]:
    """Normalize whitespace and retain the original query for audit/history."""
    query = " ".join(state.get("query", "").split())
    if not query:
        return {"query": "", "errors": ["Please enter a research question."]}
    return {"query": query}


@traceable(name="research_tool", run_type="tool")
def _run_task(task: str, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one independent tool and normalize its output into evidence records."""
    if task == "documents":
        found = document_search(query)
        evidence = [{"kind": "document", "content": item["content"], "metadata": item["metadata"], "score": item["score"]} for item in found if item.get("score") is None or item["score"] >= 0.05]
        return evidence, {"tool": task, "status": "ok", "count": len(evidence)}
    if task == "sql":
        sql = generate_sql(query)
        from src.database.sqlite import execute_sql
        result = execute_sql(sql)
        content = f"SQL: {result['sql']}\nRows: {result['rows']}"
        return [{"kind": "sql", "content": content, "sql": result["sql"], "metadata": {"source": "synthetic SQLite business database"}, "score": 1.0}], {"tool": task, "status": "ok", "sql": result["sql"], "row_count": result["row_count"]}
    if task == "web":
        results = web_search(query, max_results=5)
        return [{"kind": "web", "content": item["snippet"], "url": item["url"], "metadata": {"source": item["title"], "url": item["url"]}, "score": None} for item in results], {"tool": task, "status": "ok", "count": len(results)}
    if task == "calculator":
        # Extract a numeric arithmetic expression only when clear; never use generated code.
        match = re.search(r"[\d.]+\s*[+*/%-]\s*[\d.]+(?:\s*[+*/%-]\s*[\d.]+)*", query)
        if match:
            result = calculate(match.group(0))
            return [{"kind": "calculation", "content": f"{match.group(0)} = {result}", "metadata": {"source": "safe calculator"}, "score": 1.0}], {"tool": task, "status": "ok"}
        return [], {"tool": task, "status": "skipped", "reason": "No explicit arithmetic expression found."}
    if task == "mcp":
        items = call_local_tool("search_documents", {"query": query, "limit": 5})
        records = [{"kind": "mcp", "content": item["content"], "metadata": item["metadata"], "score": item["score"]} for item in items]
        return records, {"tool": task, "status": "ok", "discovered_tool": "search_documents", "count": len(records)}
    raise ValueError(f"Unknown task: {task}")


def _gather_node(state: ResearchState) -> dict[str, Any]:
    tasks = [task for task in state.get("plan", []) if task in _ALLOWED_TASKS]
    evidence: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    # Independent read tools run concurrently. Ordering is normalized to plan order below.
    results: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(len(tasks), 5))) as executor:
        submitted_at = {executor.submit(_run_task, task, state.get("retrieval_query", state.get("query", "")) if task == "documents" else state.get("query", "")): (task, time.perf_counter()) for task in tasks}
        for future in as_completed(submitted_at):
            task, start_time = submitted_at[future]
            try:
                records, event = future.result()
                event["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
                results[task] = (records, event)
            except Exception as exc:
                results[task] = ([], {"tool": task, "status": "error", "error": str(exc), "duration_ms": round((time.perf_counter() - start_time) * 1000, 2)})
    for task in tasks:
        records, event = results[task]
        start = len(evidence) + 1
        for record in records:
            record["evidence_id"] = start
            evidence.append(record)
            start += 1
        events.append(event)
    return {"evidence": evidence, "tool_events": events}


def _evaluate_node(state: ResearchState) -> dict[str, Any]:
    evidence = state.get("evidence", [])
    usable = [item for item in evidence if item.get("content") and (item.get("kind") != "document" or item.get("score", 0) >= 0.05)]
    # For weak coverage, one corrective pass broadens document wording and adds internal tools.
    needs_retry = not usable and state.get("retry_count", 0) < settings.max_research_replans
    return {"sufficient_evidence": bool(usable), "retry_count": state.get("retry_count", 0) + int(needs_retry), "needs_retry": needs_retry}


def _retry_route(state: ResearchState) -> str:
    if state.get("needs_retry", False):
        return "retry"
    return "answer"


def _retry_node(state: ResearchState) -> dict[str, Any]:
    expanded = list(dict.fromkeys(state.get("plan", []) + ["documents", "sql"]))
    query = state.get("query", "")
    retrieval_query = " ".join(dict.fromkeys((query + " refund policy subscription revenue customer support annual report").split()))
    return {"plan": expanded, "retrieval_query": retrieval_query}


def _answer_node(state: ResearchState) -> dict[str, Any]:
    evidence = state.get("evidence", [])
    if not evidence:
        answer = "I could not find usable evidence for this question. Check that the sample database is seeded and that relevant documents are indexed, then try a narrower question."
        return {"draft": answer, "citations": [], "limitations": ["No usable evidence was retrieved."], "confidence": 0.1}
    lines = []
    for idx, item in enumerate(evidence, 1):
        content = str(item.get("content", "")).replace("\n", " ")
        lines.append(f"[{idx}] {content[:1200]}")
    prompt_data = "\n\n".join(lines)
    answer = "Evidence gathered for your question:\n\n" + "\n\n".join(lines)
    citations = list(range(1, len(evidence) + 1))
    limitations: list[str] = []
    confidence = min(0.95, 0.45 + 0.1 * len(evidence))
    if settings.openai_api_key:
        try:
            chain = build_answer_chain()
            response: ResearchAnswer = chain.invoke({"history": state.get("history", [])[-6:], "memories": state.get("memories", []), "verification": state.get("verification_feedback", state.get("verification", [])), "query": state.get("query", ""), "evidence": prompt_data})
            answer, citations, limitations, confidence = response.answer, response.citations, response.limitations, response.confidence
        except Exception as exc:
            limitations.append(f"LLM answer generation unavailable; showing retrieved evidence. ({type(exc).__name__})")
    return {"draft": answer, "citations": citations, "limitations": limitations, "confidence": confidence}


def _verify_node(state: ResearchState) -> dict[str, Any]:
    citations = state.get("citations", [])
    evidence_count = len(state.get("evidence", []))
    findings = []
    if not citations:
        findings.append("Draft contains no evidence citations.")
    if any(index < 1 or index > evidence_count for index in citations):
        findings.append("Draft refers to an evidence item that does not exist.")
    if evidence_count == 0:
        findings.append("No evidence was available to verify claims.")
    attempts = state.get("revision_attempts", 0) + int(bool(findings))
    return {"verification": findings, "verification_feedback": "; ".join(findings), "revision_attempts": attempts, "approval_status": "pending", "final_answer": ""}


def _verification_route(state: ResearchState) -> str:
    """Allow one answer revision after citation validation findings."""
    if state.get("verification") and state.get("revision_attempts", 0) <= 1:
        return "revise"
    return "approval"


def _revision_node(state: ResearchState) -> dict[str, Any]:
    """Carry verifier feedback into one bounded optimizer pass."""
    return {"verification_feedback": "; ".join(state.get("verification", []))}


def _approval_node(state: ResearchState) -> dict[str, Any]:
    if state.get("approved"):
        return {"approval_status": "approved", "final_answer": state.get("draft", "")}
    try:
        from langgraph.types import interrupt
        decision = interrupt({"type": "human_approval", "draft": state.get("draft", ""), "evidence_count": len(state.get("evidence", []))})
        if isinstance(decision, dict) and decision.get("approved"):
            return {"approved": True, "approval_status": "approved", "final_answer": state.get("draft", "")}
        feedback = str(decision.get("feedback", "")) if isinstance(decision, dict) else ""
        return {"approved": False, "approval_status": "pending", "review_feedback": feedback, "final_answer": ""}
    except ImportError:
        # The deterministic fallback exposes the same pending-review state without LangGraph.
        return {"approval_status": "pending", "final_answer": ""}


def _build_langgraph(checkpoint_path: str | None = None) -> Any:
    # Checkpoints can contain user-provided text; use the strict serializer mode.
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    from langgraph.graph import END, START, StateGraph
    builder = StateGraph(ResearchState)
    builder.add_node("analyze", _query_analyzer_node)
    builder.add_node("plan", _plan_node)

    # Keep worker execution, coverage evaluation, and bounded correction reusable as a subgraph.
    evidence_builder = StateGraph(ResearchState)
    evidence_builder.add_node("gather", _gather_node)
    evidence_builder.add_node("evaluate", _evaluate_node)
    evidence_builder.add_node("retry", _retry_node)
    evidence_builder.add_edge(START, "gather")
    evidence_builder.add_edge("gather", "evaluate")
    evidence_builder.add_conditional_edges("evaluate", _retry_route, {"retry": "retry", "answer": END})
    evidence_builder.add_edge("retry", "gather")
    builder.add_node("evidence_subgraph", evidence_builder.compile())
    builder.add_node("answer", _answer_node)
    builder.add_node("verify", _verify_node)
    builder.add_node("revise", _revision_node)
    builder.add_node("approval", _approval_node)
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "plan")
    builder.add_edge("plan", "evidence_subgraph")
    builder.add_edge("evidence_subgraph", "answer")
    builder.add_edge("answer", "verify")
    builder.add_conditional_edges("verify", _verification_route, {"revise": "revise", "approval": "approval"})
    builder.add_edge("revise", "answer")
    builder.add_edge("approval", END)
    if checkpoint_path:
        from langgraph.checkpoint.sqlite import SqliteSaver
        conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
        return builder.compile(checkpointer=SqliteSaver(conn))
    return builder.compile()


_GRAPH_LOCK = threading.Lock()
_GRAPH: Any | None = None


def get_graph() -> Any | None:
    """Return a compiled graph when LangGraph is installed; else None."""
    global _GRAPH
    with _GRAPH_LOCK:
        if _GRAPH is not None:
            return _GRAPH
        try:
            checkpoint = settings.resolve(settings.checkpoint_db_path)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            _GRAPH = _build_langgraph(str(checkpoint))
        except ImportError:
            return None
        return _GRAPH


def _initial_state(query: str, thread: str, history: list[dict[str, str]] | None, memories: list[dict[str, str]] | None, use_langgraph: bool) -> ResearchState:
    """Build a clean per-run input while preserving the thread's checkpoint history."""
    initial: ResearchState = {"query": query, "thread_id": thread, "history": history or [], "memories": memories or [], "retry_count": 0, "approved": False, "evidence": [], "tool_events": [], "errors": []}
    if use_langgraph:
        try:
            from langgraph.types import Overwrite
            initial["evidence"] = Overwrite([])
            initial["tool_events"] = Overwrite([])
            initial["errors"] = Overwrite([])
        except ImportError:
            pass
    return initial


def run_research(query: str, thread_id: str | None = None, history: list[dict[str, str]] | None = None, approved: bool = False, memories: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run the graph or its deterministic fallback and return an inspectable state."""
    thread = thread_id or str(uuid.uuid4())
    graph = get_graph()
    initial = _initial_state(query, thread, history, memories, use_langgraph=graph is not None)
    initial["approved"] = approved
    if graph is not None:
        result = graph.invoke(initial, config={"configurable": {"thread_id": thread}})
        return dict(result)
    # Graceful no-LangGraph local path, preserving each stage's same semantics.
    state = dict(initial)
    state.update(_query_analyzer_node(state))
    state.update(_plan_node(state))
    state.update(_gather_node(state))
    evaluation = _evaluate_node(state)
    state.update(evaluation)
    if state.get("needs_retry", False):
        state.update(_retry_node(state))
        state.update(_gather_node(state))
        state.update(_evaluate_node(state))
    state.update(_answer_node(state))
    state.update(_verify_node(state))
    if state.get("verification") and state.get("revision_attempts", 0) <= 1:
        state.update(_revision_node(state))
        state.update(_answer_node(state))
        state.update(_verify_node(state))
    state.update(_approval_node(state))
    return state


def resume_approval(state: dict[str, Any], thread_id: str, approved: bool, feedback: str = "") -> dict[str, Any]:
    """Resume a checkpointed LangGraph approval interrupt, with a local fallback."""
    graph = get_graph()
    if graph is not None and state.get("__interrupt__"):
        from langgraph.types import Command
        result = graph.invoke(Command(resume={"approved": approved, "feedback": feedback}), config={"configurable": {"thread_id": thread_id}})
        return dict(result)
    return approve_answer(state, approved, feedback)


def approve_answer(state: dict[str, Any], approved: bool, feedback: str = "") -> dict[str, Any]:
    """Finalize or request a revised answer from an already reviewed state."""
    updated = dict(state)
    if feedback.strip():
        updated["draft"] = f"{state.get('draft', '')}\n\nReviewer feedback: {feedback.strip()}"
    updated["approved"] = approved
    if approved:
        updated["approval_status"] = "approved"
        updated["final_answer"] = updated.get("draft", "")
    else:
        updated["approval_status"] = "pending"
        updated["final_answer"] = ""
    return updated


def run_research_stream(query: str, thread_id: str | None = None, history: list[dict[str, str]] | None = None, on_step: Any | None = None, memories: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Stream LangGraph state updates to a callback and return the final graph state."""
    thread = thread_id or str(uuid.uuid4())
    graph = get_graph()
    if graph is None or not hasattr(graph, "stream"):
        return run_research(query, thread_id=thread, history=history, memories=memories)
    initial = _initial_state(query, thread, history, memories, use_langgraph=True)
    config = {"configurable": {"thread_id": thread}}
    latest: dict[str, Any] = dict(initial)
    for snapshot in graph.stream(initial, config=config, stream_mode="values"):
        latest = dict(snapshot)
        if on_step:
            on_step(snapshot)
    if hasattr(graph, "get_state"):
        checkpoint = graph.get_state(config)
        latest = dict(checkpoint.values)
        interrupts = [item for task in checkpoint.tasks for item in getattr(task, "interrupts", ())]
        if interrupts:
            latest["__interrupt__"] = interrupts
    return latest
