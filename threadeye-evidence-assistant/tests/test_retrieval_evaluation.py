from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from threadeye_evidence.retrieval.evaluation import _mode_metrics, load_evaluation_dataset
from threadeye_evidence.retrieval.models import RetrievalValidationError


ROOT = Path(__file__).resolve().parents[1]


class RetrievalEvaluationTests(unittest.TestCase):
    def test_fixed_dataset_schema_and_coverage(self) -> None:
        dataset = load_evaluation_dataset(ROOT / "evaluation/retrieval-v1.json")
        self.assertEqual(len(dataset.queries), 35)
        self.assertEqual(len({query.query_id for query in dataset.queries}), 35)
        self.assertEqual(sum(query.expected_no_result for query in dataset.queries), 3)
        categories = {query.category for query in dataset.queries}
        self.assertTrue({"exact_terminology", "semantic_paraphrase", "technical_identifier", "out_of_corpus"} <= categories)

    def test_dataset_rejects_post_prediction_or_wrong_size_labels(self) -> None:
        raw = json.loads((ROOT / "evaluation/retrieval-v1.json").read_text())
        raw["created_before_prediction_review"] = False
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(raw))
            with self.assertRaises(RetrievalValidationError):
                load_evaluation_dataset(path)

    def test_metric_calculation_uses_relevant_query_denominator(self) -> None:
        records = [
            {"failure": None, "latency_ms": 10.0, "expected_sections": ["A"], "returned_sections": ["X", "A"]},
            {"failure": None, "latency_ms": 20.0, "expected_sections": ["B", "C"], "returned_sections": ["B"]},
            {"failure": None, "latency_ms": 30.0, "expected_sections": [], "returned_sections": []},
        ]
        metrics = _mode_metrics(records, relevant_query_count=2, no_result_count=1)
        self.assertEqual(metrics["hit_rate_at_1"], 0.5)
        self.assertEqual(metrics["hit_rate_at_3"], 1.0)
        self.assertEqual(metrics["recall_at_5"], 0.75)
        self.assertEqual(metrics["mrr"], 0.75)
        self.assertEqual(metrics["no_result_accuracy"], 1.0)
        self.assertEqual(metrics["average_query_latency_ms"], 20.0)

    def test_failures_are_counted_not_misreported_as_no_result(self) -> None:
        records = [{"failure": "BackendError", "latency_ms": 0.0, "expected_sections": [], "returned_sections": []}]
        metrics = _mode_metrics(records, relevant_query_count=0, no_result_count=1)
        self.assertEqual(metrics["per_query_failure_count"], 1)
        self.assertEqual(metrics["no_result_accuracy"], 0.0)


if __name__ == "__main__":
    unittest.main()
