"""Local Hugging Face sentence embedding factory."""
from __future__ import annotations
from typing import Any

from src.config.settings import settings


def build_embeddings(model_name: str | None = None) -> Any:
    """Create a LangChain Hugging Face embedding adapter lazily."""
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=model_name or settings.embedding_model)
