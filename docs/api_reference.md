# API and module reference

## Main Python interfaces

| Module | Public interface | Purpose |
|---|---|---|
| `src.config.settings` | `settings`, `Settings` | Environment-backed runtime configuration and local path setup. |
| `src.ingestion.pipeline` | `load_documents`, `clean_text`, `chunk_documents` | Load PDF/TXT/Markdown/CSV, normalize, and split documents. |
| `src.retrieval.store` | `DocumentStore`, `document_search` | Add documents to Chroma and retrieve ranked passages with metadata. |
| `src.database.sqlite` | `validate_select_sql`, `execute_sql`, `schema_description` | Enforce the SELECT-only policy and run bounded read-only queries. |
| `src.tools.sql_agent` | `generate_sql`, `query_business_data` | Convert supported analytics questions to a validated query. |
| `src.graph.workflow` | `run_research`, `run_research_stream`, `resume_approval` | Run and inspect the workflow, stream graph values, and resume human approval. |
| `src.agents.tool_agent` | `build_research_agent`, `run_tool_agent` | Optional LangChain model-driven tool calling for interview exploration. |
| `src.memory.store` | `MemoryStore` | Store transcripts and explicit preferences separately from graph checkpoints. |
| `src.mcp_server.server` | `mcp`, `main` | Run the FastMCP server with three typed tools. |
| `src.mcp_server.client` | `discover_local_tools`, `call_local_tool` | Discover and call allow-listed local MCP tools. |

## Local commands

```bash
python data/seed_database.py
streamlit run app.py
pytest -q
```

Run the MCP server over stdio with `python -m src.mcp_server.server`. The optional API key is read from `OPENAI_API_KEY` or Streamlit secrets. Without it, the application uses deterministic routing, sample SQL mappings, and evidence display. Public search requires network access and the configured `ddgs` package.
