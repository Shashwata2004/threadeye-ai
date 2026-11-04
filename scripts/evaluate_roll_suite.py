"""Replay the fixed simulated roll suite with a real ONNX detector, without DB writes."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from measure_impact import ROOT, measure, sha256

ROLLS = ["linescan_roll", "demo_basic_roll", "demo_mixed_roll", "demo_challenge_roll"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "data/model/threadeye_s.onnx")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for name in ROLLS:
        output = args.out / f"{name}.json"
        # Resume only a complete result with exactly the same model/card/video inputs.
        previous = json.loads(output.read_text()) if output.exists() else None
        paths = [args.model, args.model.with_name("model_info.json"),
                 *(ROOT / "data" / name / f for f in ["roll_meta.json", "frames.csv", "ground_truth.csv", "nuisance.csv", "roll_video.mp4"])]
        expected = {p.name: sha256(p) for p in paths}
        if previous and previous["sha256"] == expected and previous.get("inference_threads") == args.threads:
            result = previous
        else:
            result = measure(args.model, ROOT / "data" / name, threads=args.threads)
            result["inference_threads"] = args.threads
            output.write_text(json.dumps(result, indent=2))
        results.append(result)
        ev = result["evaluation"]
        print(f"{name}: TP {ev['tp']}, FP {ev['fp']}, FN {ev['fn']}, recall {ev['recall']:.3f}", flush=True)
    summary = {"measured_at_utc": datetime.now(UTC).isoformat(), "model_sha256": sha256(args.model),
               "limitation": "Simulated development/regression suite; source images may recur across scenarios. Not a factory pilot or independent overall test score.",
               "rolls": results}
    (args.out / "suite.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
