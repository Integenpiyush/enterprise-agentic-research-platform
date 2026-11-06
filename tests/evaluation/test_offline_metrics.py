from src.evaluation.metrics import answer_faithfulness, citation_coverage, retrieval_precision, retrieval_recall, task_success, tool_selection_accuracy


def test_evaluation_metrics_cover_retrieval_tools_faithfulness_and_success():
    evidence = ["Refunds are available within 30 calendar days for unused annual plans."]
    assert retrieval_precision(evidence, ["refund", "30 days"]) == 1.0
    assert retrieval_recall(evidence, ["refund", "30 days"]) == 2 / 3
    assert answer_faithfulness("Refunds are available within 30 days", evidence) > 0.5
    assert tool_selection_accuracy(["documents"], ["documents"])["exact_match"] == 1.0
    assert citation_coverage("According to [1]", 1) == 1.0
    assert task_success("Supported answer", evidence_count=1, citation_count=1)
