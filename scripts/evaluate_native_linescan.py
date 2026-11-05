"""Measure a frozen model on prepared native validation images without retuning thresholds.

This image comparison complements full production video replay. It does not include sampling,
tracking or factory measurements; saved reports explicitly identify that scope.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "ml")]

import cv2
from fabricdata.classes import DEFECT_CLASSES
from fabricdata.operating import Det, Truth, match, report
from threadeye.core.providers import ProviderContext
from threadeye.providers.local_model import LocalModelDetector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads((args.data / "annotations.json").read_text())
    categories = {c["id"]: c["name"] for c in data["categories"]}
    names = {im["id"]: im["file_name"] for im in data["images"]}
    truths = [
        Truth(
            names[a["image_id"]],
            categories[a["category_id"]],
            (
                a["bbox"][0],
                a["bbox"][1],
                a["bbox"][0] + a["bbox"][2],
                a["bbox"][1] + a["bbox"][3],
            ),
        )
        for a in data["annotations"]
    ]
    detector = LocalModelDetector(
        {
            "model_path": str(args.model),
            "threads": 2,
            "whole_strip": False,
            "pack": False,
        },
        ProviderContext(),
    )
    # Local preparation only loads/checks the model; no source data or answer key enters it.
    detector.prepare(None)
    started = time.perf_counter()
    detections = []
    try:
        for n, name in enumerate(names.values(), 1):
            image = cv2.imread(str(args.data / name))
            if image is None:
                raise ValueError("validation image missing: " + name)
            detections.extend(
                Det(name, cls, score, box)
                for box, cls, score in detector.detect_array(image)
            )
            if n % 100 == 0:
                print("NATIVE_VALIDATION", n, len(names), flush=True)
    finally:
        detector.close()
    metrics = report(
        detections,
        truths,
        {c: 0 for c in detector.classes},
        set(DEFECT_CLASSES),
        lambda _: "native-line-scan",
        names.values(),
    )
    bt = [t for t in truths if t.cls == "broken_yarn"]
    bd = [d for d in detections if d.cls == "broken_yarn"]
    found, _, _ = match(bd, bt, lambda a, b: a == b)
    metrics.update(
        {
            "broken_right_recall": len(found) / len(bt) if bt else 0,
            "seconds": time.perf_counter() - started,
            "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
            "scope": "native validation images; installed thresholds frozen; no sampling/tracking; no threshold selection",
            "validation_sha256": hashlib.sha256(
                (args.data / "annotations.json").read_bytes()
            ).hexdigest(),
        }
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2))
    print(
        "NATIVE_RESULT",
        {
            k: metrics[k]
            for k in [
                "found_any_class",
                "found_right_class",
                "precision",
                "broken_right_recall",
                "seconds",
            ]
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
