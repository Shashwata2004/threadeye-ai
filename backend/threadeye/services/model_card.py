"""The trained detector's model card: what ml/kaggle/train.py wrote next to the ONNX model.

model_info.json   framework, size, epochs, classes, per-class thresholds, training minutes
test_report.json  the test split counted at those thresholds (ml/fabricdata/operating.py)

Both are small JSON files shipped with the backend (threadeye/data/model/) or read from ``model_dir``.
No files: no evaluation yet (the Benchmark screen says so instead of showing numbers).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGED = Path(__file__).resolve().parent.parent / "data" / "model"
NONDEFECTS = frozenset({"sticker", "loose_thread", "wrinkle", "hand"})


def load_evaluation(model_dir: str = "") -> dict[str, Any] | None:
    root = Path(model_dir) if model_dir else PACKAGED
    info_path, report_path = root / "model_info.json", root / "test_report.json"
    if not (info_path.exists() and report_path.exists()):
        return None
    info = json.loads(info_path.read_text())
    rep = json.loads(report_path.read_text())
    return {
        "model": f"YOLOX-{str(info.get('size', '?')).upper()}",
        "framework": info.get("framework", ""),
        "epochs": int(info.get("epochs", 0)),
        "train_minutes": info.get("minutes"),
        "classes": list(info.get("classes", [])),
        "matching": rep.get("matching", ""),
        "thresholds_from": rep.get("thresholds_from", ""),
        "precision": rep.get("precision"),
        **{
            k: rep[k]
            for k in (
                "tiles",
                "defects",
                "found_any_class",
                "found_right_class",
                "defect_boxes",
                "false_alarms",
                "false_alarms_per_100_tiles",
                "nondefects",
                "nondefects_called_defect",
            )
        },
        "per_class": [
            {
                "cls": c,
                "nondefect": c in NONDEFECTS,
                **{k: v.get(k) for k in ("threshold", "truth", "recall", "precision")},
            }
            for c, v in rep.get("per_class", {}).items()
        ],
        "per_source": [{"source": s, **v} for s, v in rep.get("per_source", {}).items()],
    }
