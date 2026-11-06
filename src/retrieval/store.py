"""Chroma-backed semantic retrieval with a small offline lexical fallback."""
from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.config.settings import settings
from src.ingestion.pipeline import TextDocument, chunk_documents, load_documents

logger = logging.getLogger(__name__)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class DocumentStore:
    """Local document index. Chroma/Hugging Face are used when installed."""

    def __init__(self, persist_directory: str | Path | None = None, collection_name: str = "business_docs") -> None:
        self.persist_directory = Path(persist_directory) if persist_directory else settings.resolve(settings.chroma_dir)
        self.collection_name = collection_name
        self._vectorstore: Any | None = None
        self._fallback: list[TextDocument] = self._load_fallback_index()
        self._seeded = False

    def _get_vectorstore(self) -> Any | None:
        if self._vectorstore is not None:
            return self._vectorstore
        try:
            from langchain_chroma import Chroma
            from src.embeddings.huggingface import build_embeddings
            embeddings = build_embeddings()
            self._vectorstore = Chroma(collection_name=self.collection_name, embedding_function=embeddings, persist_directory=str(self.persist_directory))
        except Exception as exc:
            logger.info("Chroma/Hugging Face unavailable; using lexical retrieval: %s", exc)
            return None
        self._seed_sample_docs()
        return self._vectorstore

    def _seed_sample_docs(self) -> None:
        """Add bundled synthetic documents once when a persistent collection is empty."""
        if self._seeded or self._vectorstore is None:
            return
        try:
            if self._vectorstore._collection.count() == 0:
                chunks = chunk_documents(self._load_seed_documents(), settings.chunk_size, settings.chunk_overlap)
                if chunks:
                    self._vectorstore.add_documents([self._as_langchain(doc) for doc in chunks])
        except Exception as exc:
            logger.warning("Could not preload sample document corpus: %s", exc)
        self._seeded = True

    def ingest(self, paths: list[str | Path], chunk_size: int | None = None, overlap: int | None = None) -> int:
        """Load and index files; return number of stored chunks."""
        documents = load_documents(paths)
        chunks = chunk_documents(documents, chunk_size or settings.chunk_size, overlap if overlap is not None else settings.chunk_overlap)
        if not chunks:
            return 0
        store = self._get_vectorstore()
        if store is None:
            if not self._fallback:
                self._fallback.extend(self._load_seed_corpus())
            known = {doc.metadata.get("content_hash") for doc in self._fallback}
            self._fallback.extend(doc for doc in chunks if doc.metadata.get("content_hash") not in known)
            self._save_fallback_index()
        else:
            store.add_documents([self._as_langchain(doc) for doc in chunks])
        return len(chunks)

    def search(self, query: str, k: int | None = None, metadata_filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return relevant chunks and normalized similarity scores."""
        limit = k or settings.retrieval_top_k
        store = self._get_vectorstore()
        if store is not None:
            try:
                results = store.similarity_search_with_relevance_scores(query, k=limit, filter=metadata_filter)
                if results:
                    return [{"content": doc.page_content, "metadata": dict(doc.metadata), "score": float(score)} for doc, score in results]
            except Exception:
                # An unavailable embedding model should not crash database-only workflows.
                pass
        candidates = self._fallback
        if not candidates:
            candidates = self._load_seed_corpus()
        qtokens = set(_tokens(query))
        ranked = []
        for doc in candidates:
            if metadata_filter and any(doc.metadata.get(key) != value for key, value in metadata_filter.items()):
                continue
            dtokens = _tokens(doc.page_content)
            counts = Counter(dtokens)
            score = sum(1 + math.log(counts[t]) for t in qtokens if counts[t]) / max(1, math.sqrt(len(dtokens)))
            if score > 0:
                ranked.append((score, doc))
        ranked.sort(key=lambda item: item[0], reverse=True)
        maximum = ranked[0][0] if ranked else 1.0
        return [{"content": doc.page_content, "metadata": dict(doc.metadata), "score": min(1.0, score / maximum)} for score, doc in ranked[:limit]]

    def _fallback_path(self) -> Path:
        return self.persist_directory.parent / f"{self.collection_name}.lexical.json"

    def _load_fallback_index(self) -> list[TextDocument]:
        """Load the persisted lexical fallback index used when embedding dependencies are absent."""
        path = self._fallback_path()
        try:
            return [TextDocument(item["page_content"], dict(item.get("metadata", {}))) for item in json.loads(path.read_text(encoding="utf-8"))]
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
            return []

    def _save_fallback_index(self) -> None:
        path = self._fallback_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in self._fallback]
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")

    @staticmethod
    def _as_langchain(doc: TextDocument) -> Any:
        from langchain_core.documents import Document
        return Document(page_content=doc.page_content, metadata=doc.metadata)

    @staticmethod
    def _load_seed_documents() -> list[TextDocument]:
        corpus = Path(__file__).resolve().parents[2] / "data/sample_documents"
        return load_documents([corpus])

    @classmethod
    def _load_seed_corpus(cls) -> list[TextDocument]:
        return chunk_documents(cls._load_seed_documents(), settings.chunk_size, settings.chunk_overlap)


def document_search(query: str, k: int = 5, metadata_filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Search the persisted index and bundled demo documents."""
    return DocumentStore().search(query, k=k, metadata_filter=metadata_filter)
