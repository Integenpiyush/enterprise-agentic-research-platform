"""Streamlit UI for the Enterprise Agentic Research & Decision Platform."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Northstar Research", page_icon="🔎", layout="wide")

# Streamlit secrets are copied to environment before configuration modules load.
try:
    for secret_name in ("OPENAI_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT"):
        secret_value = st.secrets.get(secret_name)
        if secret_value is not None:
            os.environ.setdefault(secret_name, str(secret_value))
except Exception:
    pass

from src.config.settings import settings
from src.database.sqlite import execute_sql, schema_description
from data.seed_database import create_database
from src.graph.workflow import approve_answer, resume_approval, run_research_stream
from src.memory.store import MemoryStore, clear_checkpoint_thread
from src.observability.langsmith import configure_langsmith
from src.retrieval.store import DocumentStore
from src.tools.report import report_generator
from src.tools.sql_agent import query_business_data

if not settings.resolve(settings.sqlite_db_path).exists():
    try:
        create_database()
    except Exception as exc:
        st.warning(f"Sample database could not be initialized: {exc}")

configure_langsmith()

st.markdown("""
<style>
.block-container {max-width: 1220px; padding-top: 1.8rem;}
[data-testid="stMetric"] {background: #fff; border: 1px solid #e2e8f0; padding: 1rem; border-radius: 12px;}
[data-testid="stChatMessage"] {border: 1px solid #e2e8f0; border-radius: 12px; padding: .7rem 1rem;}
</style>
""", unsafe_allow_html=True)

store = MemoryStore()
if "user_id" not in st.session_state:
    st.session_state.user_id = "demo-user"
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = store.history(st.session_state.user_id, st.session_state.thread_id)
if "pending_review" not in st.session_state:
    st.session_state.pending_review = None

with st.sidebar:
    st.title("🔎 Northstar")
    st.caption("Agentic Research & Decision Platform")
    page = st.radio("Workspace", ["Research chat", "Documents", "Database analytics", "Memory & settings"], label_visibility="collapsed")
    st.divider()
    st.markdown("**System status**")
    st.success("Business database ready" if settings.resolve(settings.sqlite_db_path).exists() else "Database needs setup")
    try:
        from src.graph.workflow import get_graph
        st.success("LangGraph active" if get_graph() is not None else "Deterministic workflow mode")
    except Exception:
        st.info("Deterministic workflow mode")
    st.caption("LLM: configured" if settings.openai_api_key else "LLM: local evidence mode")
    if st.button("＋ New conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_review = None
        st.rerun()


def render_evidence(evidence: list[dict]) -> None:
    for index, item in enumerate(evidence, 1):
        metadata = item.get("metadata", {})
        source = metadata.get("source") or item.get("url") or item.get("kind", "Evidence")
        with st.expander(f"[{index}] {Path(str(source)).name if str(source).startswith('/') else source} · {item.get('kind', 'source')}"):
            if metadata.get("page") is not None:
                st.caption(f"Page: {metadata.get('page')}")
            if item.get("score") is not None:
                st.caption(f"Retrieval relevance: {float(item['score']):.3f}")
            if item.get("url"):
                st.markdown(f"Source: [{item['url']}]({item['url']})")
            st.write(item.get("content", ""))
            if item.get("sql"):
                st.code(item["sql"], language="sql")


def render_result(state: dict) -> None:
    draft = state.get("draft", "")
    if draft:
        st.markdown(draft)
    if state.get("limitations"):
        for item in state["limitations"]:
            st.warning(item)
    st.caption(f"Confidence estimate: {state.get('confidence', 0):.0%} · Approval: {state.get('approval_status', 'pending')}")
    st.markdown("**Sources and retrieved passages**")
    render_evidence(state.get("evidence", []))
    with st.expander("Tool activity and verification"):
        st.markdown("**Tool activity**")
        if state.get("tool_events"):
            st.json(state["tool_events"])
        else:
            st.caption("No tools ran.")
        if state.get("verification"):
            st.markdown("**Verification findings**")
            for finding in state["verification"]:
                st.warning(finding)
    if state.get("approval_status") == "pending":
        col1, col2 = st.columns(2)
        if col1.button("Approve answer", type="primary", key="approve_answer"):
            approved = resume_approval(state, st.session_state.thread_id, True)
            st.session_state.pending_review = None
            st.session_state.last_approved = approved
            st.session_state.messages.append({"role": "assistant", "content": approved["final_answer"]})
            store.add_message(st.session_state.user_id, st.session_state.thread_id, "assistant", approved["final_answer"])
            st.success("Answer approved and saved to this conversation.")
            st.rerun()
        with col2.form("review_feedback"):
            feedback = st.text_input("Request a revision", placeholder="What should the agent revisit?")
            revise = st.form_submit_button("Return for revision")
            if revise:
                if not feedback.strip():
                    st.warning("Add reviewer feedback so the agent knows what to revisit.")
                else:
                    resume_approval(state, st.session_state.thread_id, False, feedback)
                    with st.spinner("Revising the research with reviewer feedback…"):
                        revised = run_research_stream(
                            state.get("query", "") + "\nReviewer feedback: " + feedback.strip(),
                            thread_id=st.session_state.thread_id,
                            history=st.session_state.messages,
                            memories=store.relevant_memories(st.session_state.user_id, feedback),
                        )
                    st.session_state.pending_review = revised
                    st.rerun()


if page == "Research chat":
    st.title("Business research, grounded in evidence")
    st.write("Ask about company policies, sample business performance, customer signals, or external research. Review every source before approving a response.")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input("Ask a business question…")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        store.add_message(st.session_state.user_id, st.session_state.thread_id, "user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            status = st.status("Researching your question…", expanded=True)
            progress = status.empty()
            try:
                def update_progress(snapshot: dict) -> None:
                    stage = snapshot.get("plan") or []
                    event_rows = snapshot.get("tool_events") or []
                    if stage:
                        progress.write(f"Planned tools: {', '.join(stage)}")
                    if event_rows:
                        progress.write("Latest activity: " + ", ".join(f"{row.get('tool')}: {row.get('status')}" for row in event_rows[-5:]))
                state = run_research_stream(prompt, thread_id=st.session_state.thread_id, history=st.session_state.messages[:-1], on_step=update_progress, memories=store.relevant_memories(st.session_state.user_id, prompt))
                status.update(label="Evidence gathered; answer ready for review", state="complete", expanded=False)
                st.session_state.pending_review = state
            except Exception as exc:
                status.update(label="Research run failed", state="error")
                st.error(f"The research workflow encountered an error: {exc}")
    if st.session_state.pending_review and not st.session_state.pending_review.get("final_answer"):
        st.divider()
        st.subheader("Pending review")
        render_result(st.session_state.pending_review)
    if st.session_state.get("last_approved"):
        with st.expander("Create an evidence-backed report"):
            report_title = st.text_input("Report title", value="Business Research Report")
            if st.button("Save Markdown report", key="save_report"):
                report_path = report_generator(report_title, st.session_state.last_approved["final_answer"], st.session_state.last_approved.get("evidence", []))
                st.success(f"Report saved to {report_path}")

elif page == "Documents":
    st.title("Document library")
    st.write("Upload PDF, TXT, Markdown, or CSV documents. Uploaded files stay in this local app's ignored runtime data directory.")
    uploads = st.file_uploader("Add documents", type=["pdf", "txt", "md", "csv"], accept_multiple_files=True)
    if st.button("Ingest uploaded documents", type="primary", disabled=not uploads):
        upload_dir = settings.resolve(settings.data_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for upload in uploads:
            destination = upload_dir / f"{uuid.uuid4().hex[:8]}_{Path(upload.name).name}"
            destination.write_bytes(upload.getvalue())
            paths.append(destination)
        try:
            count = DocumentStore().ingest(paths)
            st.success(f"Indexed {count} chunks from {len(paths)} file(s).")
        except Exception as exc:
            st.error(f"Document ingestion failed: {exc}")
    st.subheader("Search documents")
    query = st.text_input("Search query", key="document_query")
    if query:
        results = DocumentStore().search(query)
        st.caption(f"Retrieved {len(results)} passages")
        render_evidence([{"kind": "document", **item} for item in results])
    st.divider()
    st.subheader("Bundled synthetic corpus")
    for path in sorted((settings.root_dir / "data/sample_documents").glob("*")):
        if path.is_file():
            st.markdown(f"- `{path.name}`")

elif page == "Database analytics":
    st.title("Business database")
    st.caption("All records are synthetic and generated for this demonstration.")
    if not settings.resolve(settings.sqlite_db_path).exists():
        st.warning("Sample database is missing. Run `python data/seed_database.py` from the repository root.")
    else:
        try:
            stats = execute_sql("SELECT COUNT(*) AS customers FROM customers")["rows"][0]
            orders = execute_sql("SELECT COUNT(*) AS orders, ROUND(SUM(total_amount), 2) AS gross_booked FROM orders WHERE status='completed'")["rows"][0]
            a, b, c = st.columns(3)
            a.metric("Customers", stats["customers"])
            b.metric("Orders", orders["orders"])
            c.metric("Completed order value", f"${orders['gross_booked']:,.2f}")
            st.subheader("Ask the sample database")
            question = st.text_input("Business question", placeholder="What was monthly revenue?")
            if question:
                try:
                    result = query_business_data(question)
                    st.code(result["sql"], language="sql")
                    st.dataframe(result["rows"], use_container_width=True)
                    st.caption(result["explanation"])
                except Exception as exc:
                    st.info(str(exc))
            with st.expander("Schema"):
                st.code(schema_description(), language="sql")
        except Exception as exc:
            st.error(f"Database query failed: {exc}")

else:
    st.title("Memory and settings")
    st.write("Conversation checkpoints hold graph execution state. This separate SQLite memory store holds conversation transcripts and user preferences.")
    user_id = st.text_input("Local user identifier", value=st.session_state.user_id)
    if user_id != st.session_state.user_id:
        st.session_state.user_id = user_id
    with st.form("preference_form"):
        preference_key = st.text_input("Preference name", placeholder="report_style")
        preference_value = st.text_input("Preference value", placeholder="Concise, with a summary table")
        save = st.form_submit_button("Save preference")
        if save and preference_key.strip():
            store.save_preference(st.session_state.user_id, preference_key.strip(), preference_value)
            st.success("Preference saved.")
    preferences = store.preferences(st.session_state.user_id)
    st.subheader("Saved preferences")
    st.json(preferences)
    if st.button("Clear my local memory", type="secondary"):
        store.clear_user(st.session_state.user_id)
        removed_checkpoints = clear_checkpoint_thread(st.session_state.thread_id)
        st.session_state.messages = []
        st.success(f"Conversation, preferences, and {removed_checkpoints} checkpoint record(s) removed for this thread.")
    st.divider()
    st.subheader("Service configuration")
    st.write({"OpenAI": bool(settings.openai_api_key), "LangSmith tracing": configure_langsmith(), "Embedding model": settings.embedding_model, "Database": str(settings.resolve(settings.sqlite_db_path)), "Vector store": str(settings.resolve(settings.chroma_dir))})
    st.caption("For Streamlit Community Cloud, configure secrets in the app settings. Persistent local files may be ephemeral on cloud hosts.")
