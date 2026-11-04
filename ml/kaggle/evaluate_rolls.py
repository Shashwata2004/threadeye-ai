"""CPU follow-up notebook: compare the completed candidate on the four fixed videos.

Inputs: previous model notebook, candidate notebook, and private frozen-video bundle.
No GPU, database, app credentials or retraining. Can run while the laptop is asleep.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path


def find(name: str) -> list[Path]:
    return [p for depth in range(6) for p in sorted(Path("/kaggle/input").glob("*/" * depth + name))]


bundle = find("roll_evaluation_bundle.tar.gz")
if bundle:
    assert len(bundle) == 1, "attach exactly one frozen video bundle"
    work = Path("/kaggle/tmp/roll_evaluation")
    work.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle[0]) as archive:
        archive.extractall(work, filter="data")
else:
    # Some Kaggle upload routes expand an archive while processing the dataset.
    configs = find("evaluation-config.json")
    assert len(configs) == 1, "frozen evaluation bundle missing"
    work = configs[0].parent
config = json.loads((work / "evaluation-config.json").read_text())
config["candidate_slug"] = os.environ.get("THREADEYE_CANDIDATE_SLUG", config["candidate_slug"])
models = find("model/threadeye_s.onnx")
baseline = next(p for p in models if p.parent.parent.name == "threadeye-train-2")
candidate = next(p for p in models if p.parent.parent.name == config["candidate_slug"])
assert hashlib.sha256(baseline.read_bytes()).hexdigest() == config["baseline_model_sha256"]
card = json.loads(candidate.with_name("model_info.json").read_text())
assert "training: finished all epochs" in card["run_status"]
assert not any(s.startswith("FAILED") for s in card["run_status"])
assert card["train_parameters"]["frozen_manifest_sha256"] == config["frozen_manifest_sha256"]
subprocess.run([sys.executable, "-m", "pip", "-q", "install", "numpy", "pillow", "onnxruntime",
                "opencv-python-headless", "pydantic>=2.10,<3", "pydantic-settings", "pyyaml"], check=True)
output = Path("/kaggle/working/comparison")
output.mkdir(parents=True, exist_ok=True)
for label, model in [("baseline", baseline), ("candidate", candidate)]:
    subprocess.run([sys.executable, str(work / "scripts/evaluate_roll_suite.py"), "--model", str(model),
                    "--out", str(output / label), "--threads", "2"], cwd=work, check=True)
subprocess.run([sys.executable, str(work / "scripts/compare_model_candidates.py"),
                "--baseline-suite", str(output / "baseline/suite.json"), "--candidate-suite", str(output / "candidate/suite.json"),
                "--baseline-tiles", str(baseline.with_name("test_report.json")), "--candidate-tiles", str(candidate.with_name("test_report.json")),
                "--out", str(output / "candidate-comparison.json"), "--report", str(output / "REPORT.md")], check=True)
print("Comparison complete. Open comparison/REPORT.md for the Bangla report.", flush=True)
