from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from threadeye_evidence.answering.evaluation import _metrics, load_answer_evaluation_dataset
from threadeye_evidence.retrieval.models import RetrievalValidationError


ROOT = Path(__file__).resolve().parents[1]


class AnswerEvaluationTests(unittest.TestCase):
    def test_schema_has_independent_balanced_splits(self) -> None:
        dataset = load_answer_evaluation_dataset(ROOT / "evaluation/answering-v1.json")
        self.assertEqual(len(dataset.cases), 44)
        self.assertEqual(sum(case.answerable for case in dataset.cases), 22)
        self.assertEqual(sum(not case.answerable for case in dataset.cases), 22)
        self.assertEqual({case.split for case in dataset.cases}, {"development", "held_out"})
        self.assertEqual(len({case.case_id for case in dataset.cases}), 44)

    def test_post_prediction_or_unbalanced_labels_are_rejected(self) -> None:
        raw = json.loads((ROOT / "evaluation/answering-v1.json").read_text())
        raw["labels_created_before_prediction_review"] = False
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(raw))
            with self.assertRaises(RetrievalValidationError):
                load_answer_evaluation_dataset(path)

    def test_metric_denominators_and_false_answer_rate(self) -> None:
        base = {
            "status": "answered", "expected_status": "answered", "reason": None, "expected_reason": None,
            "citation_count": 1, "valid_citation_count": 1, "relevant_citation_count": 1,
            "evidence_source_correct": True, "unsupported_claim": False, "structured_valid": True,
            "latency_ms": 10.0, "runtime_failure": False,
        }
        records = [
            {**base, "answerable": True, "predicted_answered": True},
            {**base, "answerable": False, "predicted_answered": True, "expected_status": "insufficient_evidence", "expected_reason": "insufficient_relevance", "evidence_source_correct": False, "relevant_citation_count": 0},
        ]
        metrics = _metrics(records)
        self.assertEqual(metrics["false_answer_rate"], 1.0)
        self.assertEqual(metrics["false_abstention_rate"], 0.0)
        self.assertEqual(metrics["answerability_accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
