# Placement interview guide

## Project pitch

This is an evidence-first research assistant for business questions. A typed planner routes work to document retrieval, read-only SQL, public search, safe arithmetic, or MCP tools. LangGraph owns state and bounded retry behavior; each answer displays the sources and tool events and waits for a reviewer to approve it.

## Important design choices

- **Why a graph?** Nodes and transitions make retries, routing, streaming, and review visible and testable. A one-shot agent loop can be shorter but is harder to constrain and inspect.
- **Why separate checkpoints and memory?** Checkpoints preserve execution state for a thread; preference memory is durable user data. They have different retention and deletion needs.
- **Why Chroma and local embeddings?** They demonstrate semantic retrieval without a hosted embedding API. Local persistence is easy to run, but not an HA or multi-tenant production store.
- **How is SQL protected?** The query is restricted to a single SELECT, parsed when SQLGlot is installed, executed on a read-only SQLite connection, and capped. The prompt is not the security boundary.
- **What does “corrective RAG” mean here?** A simple relevance/coverage check can retry once with a broader internal evidence plan. It is not a full CRAG or Self-RAG reproduction.
- **How do you defend an answer?** Every factual draft is paired with source records, the verifier checks citation indices, and an approval action is required in the UI.

## Likely follow-up questions

1. How would you enforce tenant isolation in the vector store and memory tables?
2. How could you prevent prompt injection in retrieved documents and web pages?
3. What changes are needed for database schema drift and database-specific SQL dialects?
4. How would you measure retrieval quality beyond lexical precision/recall proxies?
5. How could a reviewer request a targeted re-retrieval rather than merely approve or reject?
6. Why is a local sentence-transformer model attractive, and what is its operational cost?
7. What would you replace SQLite and local Chroma with for a concurrent production service?
8. How should tool budgets, timeouts, and cancellation work for slow external tools?
9. Which LangSmith traces should be redacted before sending them to an observability service?
10. How would you evaluate answer faithfulness using a human-labeled dataset?

## Honest limitations

This is a placement/demo architecture, not a hardened multi-user product. The sample database and corpus are fabricated. Heuristic SQL supports common demo questions when no API key is configured. The citation verifier checks reference structure, not semantic entailment. Local filesystem persistence may disappear on Streamlit Community Cloud, and external web search depends on network/provider availability.
