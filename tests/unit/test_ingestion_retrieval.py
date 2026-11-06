from src.ingestion.pipeline import TextDocument, chunk_documents, clean_text, load_documents
from src.retrieval.store import DocumentStore


def test_clean_and_chunk_text():
    text = clean_text("Hello  world\r\n\r\n\nagain")
    assert text == "Hello world\n\nagain"
    chunks = chunk_documents([TextDocument("abcdefghij")], chunk_size=6, overlap=2)
    assert [item.page_content for item in chunks] == ["abcdef", "efghij"]


def test_load_seed_and_lexical_search(tmp_path):
    docs = load_documents(["data/sample_documents"])
    assert len(docs) >= 5
    assert all("synthetic" in doc.page_content[:300].lower() or "fictional" in doc.page_content[:300].lower() for doc in docs)
    store = DocumentStore(persist_directory=tmp_path / "chroma")
    result = store.search("unused annual refund", k=3)
    assert result
    assert "refund" in result[0]["content"].lower()


def test_chunk_config_is_validated():
    import pytest
    with pytest.raises(ValueError):
        chunk_documents([TextDocument("x")], chunk_size=10, overlap=10)


def test_retrieval_metrics_are_available():
    from src.evaluation.metrics import citation_coverage, retrieval_precision, retrieval_recall
    docs = ["refund within 30 calendar days", "Atlas dashboard refreshes daily"]
    expected = ["refund", "30 days"]
    assert retrieval_precision(docs, expected) == 0.5
    assert retrieval_recall(docs, expected) == 1.0
    assert citation_coverage("Supported by [1]", 1) == 1.0


def test_ingestion_persists_lexical_fallback_for_new_store(tmp_path):
    source = tmp_path / "policy.md"
    source.write_text("Synthetic local note: returns are accepted within 14 days.", encoding="utf-8")
    persist = tmp_path / "chroma"
    first = DocumentStore(persist_directory=persist)
    first.ingest([source])
    second = DocumentStore(persist_directory=persist)
    results = second.search("returns accepted 14 days")
    assert any("14 days" in item["content"] for item in results)


def test_extended_evaluation_metrics():
    from src.evaluation.metrics import answer_faithfulness, task_success, tool_selection_accuracy
    assert answer_faithfulness("Refunds take 30 calendar days", ["Refunds may be requested within 30 calendar days"]) > 0.5
    assert tool_selection_accuracy(["sql", "documents"], ["sql", "documents"])["exact_match"] == 1.0
    assert task_success("Supported answer", 1, 1)


def test_csv_loader_ingests_rows(tmp_path):
    path = tmp_path / "accounts.csv"
    path.write_text("name,plan\nFictional Co,Enterprise\n", encoding="utf-8")
    docs = load_documents([path])
    assert len(docs) == 1
    assert "Fictional Co" in docs[0].page_content
    assert docs[0].metadata["filename"] == "accounts.csv"
