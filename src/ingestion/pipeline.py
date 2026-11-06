"""Load, clean, split, and index supported business documents."""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv"}


@dataclass
class TextDocument:
    """Minimal document representation independent of optional integrations."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _native_load(path: Path) -> list[TextDocument]:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF ingestion requires pypdf. Install project requirements.") from exc
        return [TextDocument(page.extract_text() or "", {"source": str(path), "page": i + 1}) for i, page in enumerate(PdfReader(path).pages)]
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        text = "\n".join(" | ".join(f"{k}: {v}" for k, v in row.items()) for row in rows)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return [TextDocument(text, {"source": str(path)})]


def load_documents(paths: list[str | Path]) -> list[TextDocument]:
    """Read supported files using LangChain loaders when available, with native fallback."""
    documents: list[TextDocument] = []
    for value in paths:
        path = Path(value)
        if path.is_dir():
            candidates = sorted(p for p in path.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS)
        else:
            candidates = [path]
        for candidate in candidates:
            if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS or not candidate.is_file():
                continue
            loaded: list[TextDocument]
            try:
                if candidate.suffix.lower() == ".pdf":
                    from langchain_community.document_loaders import PyPDFLoader
                    raw = PyPDFLoader(str(candidate)).load()
                elif candidate.suffix.lower() == ".csv":
                    from langchain_community.document_loaders import CSVLoader
                    raw = CSVLoader(str(candidate), encoding="utf-8-sig").load()
                else:
                    from langchain_community.document_loaders import TextLoader
                    raw = TextLoader(str(candidate), encoding="utf-8").load()
                loaded = [TextDocument(d.page_content, dict(d.metadata)) for d in raw]
            except ImportError:
                loaded = _native_load(candidate)
            except Exception as exc:
                raise ValueError(f"Could not load document {candidate.name}: {exc}") from exc
            for doc in loaded:
                doc.page_content = clean_text(doc.page_content)
                doc.metadata.setdefault("source", str(candidate))
                doc.metadata.setdefault("filename", candidate.name)
                doc.metadata["synthetic"] = "synthetic" in doc.page_content[:300].lower() or "fictional" in doc.page_content[:300].lower()
                documents.append(doc)
    return documents


def clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph boundaries."""
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_documents(documents: list[TextDocument], chunk_size: int = 900, overlap: int = 150) -> list[TextDocument]:
    """Split loaded documents, using LangChain's recursive splitter when installed."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Require chunk_size > overlap >= 0.")
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        raw = splitter.split_documents([_to_lc(d) for d in documents])
        output = [TextDocument(d.page_content, dict(d.metadata)) for d in raw]
        for index, document in enumerate(output):
            document.metadata.setdefault("chunk", index)
            document.metadata["content_hash"] = hashlib.sha256(document.page_content.encode()).hexdigest()[:16]
        return output
    except ImportError:
        chunks: list[TextDocument] = []
        step = chunk_size - overlap
        for doc in documents:
            text = doc.page_content
            for start in range(0, len(text), step):
                piece = text[start:start + chunk_size].strip()
                if piece:
                    metadata = dict(doc.metadata)
                    metadata["chunk"] = len(chunks)
                    metadata["content_hash"] = hashlib.sha256(piece.encode()).hexdigest()[:16]
                    chunks.append(TextDocument(piece, metadata))
                if start + chunk_size >= len(text):
                    break
        return chunks


def _to_lc(document: TextDocument) -> Any:
    from langchain_core.documents import Document
    return Document(page_content=document.page_content, metadata=document.metadata)
