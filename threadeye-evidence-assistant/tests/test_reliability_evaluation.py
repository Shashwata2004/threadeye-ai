from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from threadeye_evidence.reliability.evaluation import load_reliability_dataset
from threadeye_evidence.retrieval.models import RetrievalValidationError


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = tuple(ROOT / "evaluation" / name for name in (
    "retrieval-v1.json", "answering-v1.json", "security-v1.json", "qa-holdout-v1.json",
))


class ReliabilityEvaluationTests(unittest.TestCase):
    def test_preregistered_dataset_is_balanced_separate_and_hashed(self) -> None:
        dataset = load_reliability_dataset(
            ROOT / "evaluation/answer-reliability-v1.json", historical_paths=HISTORICAL,
        )
        self.assertEqual(dataset.version, "threadeye-answer-reliability-v1")
        self.assertEqual(len(dataset.cases), 24)
        self.assertEqual(len(dataset.sha256), 64)
        for split in ("development", "fresh_holdout"):
            selected = [case for case in dataset.cases if case.split == split]
            self.assertEqual(len(selected), 12)
            self.assertEqual(sum(case.answerable for case in selected), 6)

    def test_mutable_labels_and_threshold_tuning_are_rejected(self) -> None:
        raw = json.loads((ROOT / "evaluation/answer-reliability-v1.json").read_text(encoding="utf-8"))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            raw["labels_created_before_execution"] = False
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RetrievalValidationError):
                load_reliability_dataset(path)
            raw["labels_created_before_execution"] = True
            raw["threshold_tuning_permitted"] = True
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RetrievalValidationError):
                load_reliability_dataset(path)

    def test_historical_question_reuse_is_rejected(self) -> None:
        raw = json.loads((ROOT / "evaluation/answer-reliability-v1.json").read_text(encoding="utf-8"))
        historical = json.loads((ROOT / "evaluation/qa-holdout-v1.json").read_text(encoding="utf-8"))
        raw["cases"][0]["question"] = historical["cases"][0]["question"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RetrievalValidationError):
                load_reliability_dataset(path, historical_paths=HISTORICAL)


if __name__ == "__main__":
    unittest.main()
