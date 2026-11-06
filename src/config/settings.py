"""Environment-backed application settings with safe local defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional for lightweight unit tests
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Paths are resolved relative to the repository root."""

    root_dir: Path = Path(__file__).resolve().parents[2]
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    langsmith_api_key: str | None = os.getenv("LANGSMITH_API_KEY")
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "enterprise-agentic-research-platform")
    data_dir: Path = Path(os.getenv("APP_DATA_DIR", ".local_data"))
    sqlite_db_path: Path = Path(os.getenv("SQLITE_DB_PATH", ".local_data/business.sqlite3"))
    chroma_dir: Path = Path(os.getenv("CHROMA_DIR", ".local_data/chroma"))
    checkpoint_db_path: Path = Path(os.getenv("CHECKPOINT_DB_PATH", ".local_data/checkpoints.sqlite3"))
    memory_db_path: Path = Path(os.getenv("MEMORY_DB_PATH", ".local_data/memory.sqlite3"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    max_research_replans: int = int(os.getenv("MAX_RESEARCH_REPLANS", "1"))
    max_sql_rows: int = int(os.getenv("MAX_SQL_ROWS", "100"))
    web_search_provider: str = os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo")

    def resolve(self, path: Path) -> Path:
        """Resolve relative paths from the project root."""
        return path if path.is_absolute() else self.root_dir / path

    def prepare_runtime_dirs(self) -> None:
        """Create writable directories used by runtime state."""
        for path in (self.data_dir, self.chroma_dir):
            self.resolve(path).mkdir(parents=True, exist_ok=True)
        for path in (self.sqlite_db_path, self.checkpoint_db_path, self.memory_db_path):
            self.resolve(path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
