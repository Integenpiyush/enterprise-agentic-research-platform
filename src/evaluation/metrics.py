"""Small deterministic evaluation helpers for retrieval and answer checks."""
from __future__ import annotations

import re
from typing import Iterable


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def retrieval_precision(retrieved: Iterable[str], relevant_terms: Iterable[str]) -> float:
    """Fraction of retrieved chunks that contain any expected relevance term."""
    docs = list(retrieved)
    if not docs:
        return 0.0
    terms = _terms(" ".join(relevant_terms))
    return sum(bool(_terms(doc) & terms) for doc in docs) / len(docs)


def retrieval_recall(retrieved: Iterable[str], relevant_terms: Iterable[str]) -> float:
    """Fraction of expected relevance terms present in the retrieved context."""
    expected = _terms(" ".join(relevant_terms))
    if not expected:
        return 1.0
    found = _terms(" ".join(retrieved))
    return len(expected & found) / len(expected)


def citation_coverage(answer: str, valid_citation_count: int) -> float:
    """Check that a draft includes numbered citations when evidence is available."""
    if valid_citation_count <= 0:
        return 0.0
    citations = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    return sum(1 <= citation <= valid_citation_count for citation in citations) / max(1, len(citations))


def answer_faithfulness(answer: str, evidence: Iterable[str]) -> float:
    """Lexical support proxy: fraction of answer content terms found in evidence."""
    stop_words = {"the", "and", "that", "this", "with", "from", "your", "about", "into", "have", "are", "was", "were", "will", "can", "for", "you", "not", "only", "when", "what", "which"}
    claims = {term for term in _terms(answer) if len(term) > 3 and term not in stop_words}
    if not claims:
        return 1.0
    supported = _terms(" ".join(evidence))
    return len(claims & supported) / len(claims)


def tool_selection_accuracy(actual: Iterable[str], expected: Iterable[str]) -> dict[str, float]:
    """Return exact match and set precision/recall for selected tools."""
    actual_set, expected_set = set(actual), set(expected)
    precision = len(actual_set & expected_set) / len(actual_set) if actual_set else 0.0
    recall = len(actual_set & expected_set) / len(expected_set) if expected_set else float(not actual_set)
    return {"precision": precision, "recall": recall, "exact_match": float(actual_set == expected_set)}


def task_success(answer: str, evidence_count: int, citation_count: int) -> bool:
    """A lightweight success check for offline runs, not a semantic quality judgment."""
    return bool(answer.strip()) and evidence_count > 0 and citation_count > 0
