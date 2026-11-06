"""Evidence-preserving Markdown report generation."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import settings


def report_generator(title: str, answer: str, evidence: list[dict[str, Any]], output_dir: str | Path | None = None) -> Path:
    """Write a Markdown report with explicit evidence references and timestamp."""
    target_dir = Path(output_dir) if output_dir else settings.resolve(settings.data_dir) / "reports"
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c.lower() if c.isalnum() else "-" for c in title).strip("-")[:60] or "research-report"
    target = target_dir / f"{safe_title}.md"
    lines = [f"# {title}", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", "", answer, "", "## Evidence"]
    for index, item in enumerate(evidence, 1):
        meta = item.get("metadata", {})
        source = meta.get("source") or item.get("url") or item.get("kind", "tool result")
        lines.extend([f"### [{index}] {source}", "", str(item.get("content", item.get("snippet", ""))), ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
