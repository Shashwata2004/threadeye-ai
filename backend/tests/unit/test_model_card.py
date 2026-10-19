"""The Benchmark screen's data: the model card files written by ml/kaggle/train.py."""

from __future__ import annotations

import json
from pathlib import Path

from threadeye.api.schemas.system import ModelEvaluationOut
from threadeye.services.model_card import load_evaluation


def test_no_model_card_means_no_evaluation(tmp_path: Path) -> None:
    assert load_evaluation(str(tmp_path)) is None
    (tmp_path / "model_info.json").write_text("{}")
    assert load_evaluation(str(tmp_path)) is None  # the report is missing


def test_model_card_is_served_as_measured(tmp_path: Path) -> None:
    (tmp_path / "model_info.json").write_text(
        json.dumps(
            {
                "framework": "YOLOX (Apache-2.0)",
                "size": "s",
                "epochs": 14,
                "minutes": 600.5,
                "classes": ["hole", "stain", "sticker"],
                "thresholds": {"hole": 0.35},
            }
        )
    )
    (tmp_path / "test_report.json").write_text(
        json.dumps(
            {
                "matching": "same class and IoU >= 0.3",
                "thresholds_from": "val split, best F1 per class",
                "tiles": 100,
                "defects": 40,
                "found_any_class": 0.8,
                "found_right_class": 0.6,
                "defect_boxes": 45,
                "false_alarms": 7,
                "false_alarms_per_100_tiles": 7.0,
                "nondefects": 10,
                "nondefects_called_defect": 0.2,
                "per_class": {
                    "hole": {"threshold": 0.35, "truth": 12, "recall": 0.75, "precision": 0.9},
                    "sticker": {"threshold": 0.3, "truth": 10, "recall": 0.7, "precision": 0.8},
                },
                "per_source": {
                    "aitex": {
                        "tiles": 50,
                        "defects": 20,
                        "found_any_class": 0.7,
                        "found_right_class": 0.5,
                        "false_alarms_per_100_tiles": 4.0,
                    }
                },
            }
        )
    )
    ev = ModelEvaluationOut.model_validate(load_evaluation(str(tmp_path)))
    assert ev.model == "YOLOX-S" and ev.epochs == 14 and ev.found_any_class == 0.8
    assert [(c.cls, c.nondefect) for c in ev.per_class] == [("hole", False), ("sticker", True)]
    assert ev.per_source[0].source == "aitex" and ev.per_source[0].false_alarms_per_100_tiles == 4.0
