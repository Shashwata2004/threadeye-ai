from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from threadeye_evidence.qa.evaluation import load_qa_holdout
from threadeye_evidence.retrieval.models import RetrievalValidationError


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = tuple(ROOT / "evaluation" / name for name in (
    "retrieval-v1.json", "answering-v1.json", "security-v1.json",
))


class QAHoldoutTests(unittest.TestCase):
    def test_fixed_balanced_holdout_has_human_review_markers(self) -> None:
        dataset = load_qa_holdout(ROOT / "evaluation/qa-holdout-v1.json", historical_paths=HISTORICAL)
        self.assertEqual(dataset.version, "threadeye-prompt11-qa-holdout-v1")
        self.assertEqual(len(dataset.cases), 10)
        self.assertEqual(sum(case.answerable for case in dataset.cases), 5)
        self.assertEqual(sum(not case.answerable for case in dataset.cases), 5)
        self.assertTrue(all(case.human_semantic_review_required for case in dataset.cases))

    def test_post_execution_labels_or_threshold_tuning_are_rejected(self) -> None:
        raw = json.loads((ROOT / "evaluation/qa-holdout-v1.json").read_text(encoding="utf-8"))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "holdout.json"
            raw["labels_created_before_execution"] = False
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RetrievalValidationError):
                load_qa_holdout(path)
            raw["labels_created_before_execution"] = True
            raw["threshold_tuning_permitted"] = True
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RetrievalValidationError):
                load_qa_holdout(path)

    def test_exact_historical_question_reuse_is_rejected(self) -> None:
        raw = json.loads((ROOT / "evaluation/qa-holdout-v1.json").read_text(encoding="utf-8"))
        historical = json.loads((ROOT / "evaluation/answering-v1.json").read_text(encoding="utf-8"))
        raw["cases"][0]["question"] = historical["cases"][0]["question"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "holdout.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RetrievalValidationError):
                load_qa_holdout(path, historical_paths=HISTORICAL)


if __name__ == "__main__":
    unittest.main()
