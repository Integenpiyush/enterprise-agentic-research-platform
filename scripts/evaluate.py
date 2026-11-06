"""Run a small offline workflow evaluation against the synthetic prompt set."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.metrics import answer_faithfulness, retrieval_precision, retrieval_recall, task_success, tool_selection_accuracy
from src.graph.workflow import run_research


def main() -> None:
    dataset = json.loads((ROOT / "data/evaluation_dataset.json").read_text(encoding="utf-8"))
    rows = []
    for index, item in enumerate(dataset):
        state = run_research(item["question"], thread_id=f"evaluation-{index}")
        evidence = state.get("evidence", [])
        contexts = [entry.get("content", "") for entry in evidence]
        tools = [entry.get("tool", "") for entry in state.get("tool_events", []) if entry.get("status") == "ok"]
        selection = tool_selection_accuracy(tools, item.get("expected_tools", []))
        rows.append({
            "question": item["question"],
            "selected_tools": tools,
            "tool_selection": selection,
            "retrieval_precision": retrieval_precision(contexts, item.get("expected_terms", [])),
            "retrieval_recall": retrieval_recall(contexts, item.get("expected_terms", [])),
            "answer_faithfulness_proxy": answer_faithfulness(state.get("draft", ""), contexts),
            "task_success": task_success(state.get("draft", ""), len(evidence), len(state.get("citations", []))),
        })
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
