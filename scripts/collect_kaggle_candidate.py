"""Wait for the authorized Kaggle run, download it, and compare with the existing model.

This process writes a status file and stages artifacts. It does not overwrite the
running model or upload business data. Safe to resume: roll evaluations are hashed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = "shashwatanandi2004/threadeye-line-scan-fine-tune-from-epoch-44"
EVALUATION_REF = "shashwatanandi2004/threadeye-roll-comparison"
CLI = ["uv", "tool", "run", "--from", "kaggle==2.2.4", "--with", "six", "kaggle"]
DEST = ROOT / "build/kaggle/candidate-output"
STATUS = ROOT / "docs/model/training-state.json"
REPORT_DIR = ROOT / "docs/model"
RUN_DIR = ROOT / "build/kaggle/remote-evaluation-run"
CONFIG_PATH = ROOT / "build/kaggle/targeted-code/targeted_params.json"


def state(phase: str, **extra: object) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {"phase": phase, "at_utc": datetime.now(UTC).isoformat(), "kaggle_run": REF, "running_model_changed": False, **extra}
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(STATUS)
    print(json.dumps(payload), flush=True)


def run(args: list[str], **kwargs: object) -> None:
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def main(cloud_evaluation: bool = False, submit_cloud_evaluation: bool = False) -> None:
    if submit_cloud_evaluation and STATUS.exists():
        previous = json.loads(STATUS.read_text())
        if previous.get("evaluation_run") == EVALUATION_REF and previous["phase"] in {"cloud_evaluation_submitted", "cloud_evaluation_waiting_or_running", "comparison_ready"}:
            cloud_evaluation = True
        if previous["phase"] == "comparison_ready" and (REPORT_DIR / "COMPARISON.md").exists():
            print("Comparison is already complete; no work repeated.", flush=True)
            return
    observed = EVALUATION_REF if cloud_evaluation else REF
    stop = time.monotonic() + 7 * 3600
    while time.monotonic() < stop:
        try:
            result = subprocess.run([*CLI, "kernels", "status", observed], cwd=ROOT, capture_output=True, text=True, timeout=90, check=False)
        except subprocess.TimeoutExpired:
            state("status_check_retry")
            time.sleep(45)
            continue
        if result.returncode:
            state("status_check_retry")
        elif "KernelWorkerStatus.COMPLETE" in result.stdout:
            break
        elif any(word in result.stdout for word in ("KernelWorkerStatus.ERROR", "CANCEL_ACKNOWLEDGED")):
            if cloud_evaluation:
                state("cloud_evaluation_failed_local_fallback", evaluation_run=EVALUATION_REF)
                return main(False)
            raise RuntimeError("Kaggle run failed or was cancelled; inspect its private log")
        else:
            state("cloud_evaluation_waiting_or_running" if cloud_evaluation else "training_or_evaluation_running",
                  evaluation_run=EVALUATION_REF if cloud_evaluation else None)
        time.sleep(45)
    else:
        raise RuntimeError("monitor time budget reached; model remains unchanged")
    if submit_cloud_evaluation and not cloud_evaluation:
        # A first-ever notebook has no attachable output until it completes.
        # Submitting its dependent notebook earlier silently drops that input.
        state("submitting_cloud_evaluation", evaluation_run=EVALUATION_REF)
        pushed = subprocess.run([*CLI, "kernels", "push", "-p", str(RUN_DIR),
                                 "--timeout", "21600"], cwd=ROOT, capture_output=True, text=True, timeout=180, check=False)
        if pushed.returncode == 0 and "not valid kernel sources" not in pushed.stdout + pushed.stderr:
            state("cloud_evaluation_submitted", evaluation_run=EVALUATION_REF)
            return main(True)
        state("cloud_submission_failed_local_fallback")
    state("downloading_candidate")
    run([*CLI, "kernels", "output", REF, "-p", str(DEST), "--file-pattern",
         r"(threadeye_s\.onnx|model_info\.json|test_report\.json|linescan_augmentation\.json|linescan_domain\.json|RUN_STATUS\.txt)$", "--quiet"])
    model = DEST / "model/threadeye_s.onnx"
    card = json.loads(model.with_name("model_info.json").read_text())
    if "training: finished all epochs" not in card["run_status"] or any(s.startswith("FAILED") for s in card["run_status"]):
        raise RuntimeError("candidate training/export/evaluation incomplete; refusing promotion review")
    config = json.loads(CONFIG_PATH.read_text())
    if card["train_parameters"]["frozen_manifest_sha256"] != config["train"]["frozen_manifest_sha256"]:
        raise RuntimeError("candidate manifest identity differs")
    if cloud_evaluation:
        destination = DEST / "remote-evaluation"
        run([*CLI, "kernels", "output", EVALUATION_REF, "-p", str(destination), "--file-pattern", r"\.(json|md)$", "--quiet"])
        comparison_dir = destination / "comparison"
        compared = json.loads((comparison_dir / "candidate-comparison.json").read_text())
        if compared["candidate_model_sha256"] != hashlib.sha256(model.read_bytes()).hexdigest():
            raise RuntimeError("downloaded model differs from the cloud comparison")
        shutil.copytree(comparison_dir, REPORT_DIR / "cloud-comparison", dirs_exist_ok=True)
        shutil.copy(comparison_dir / "REPORT.md", REPORT_DIR / "COMPARISON.md")
        shutil.copy(comparison_dir / "candidate-comparison.json", REPORT_DIR / "candidate-comparison.json")
        state("comparison_ready", qualified_for_review=compared["qualified_for_review"], reasons=compared["reasons"], evaluation_run=EVALUATION_REF)
        return
    state("evaluating_rolls")
    baseline_model = ROOT / "build/kaggle/baseline-model/threadeye_s.onnx"
    baseline_dir = REPORT_DIR / "linescan-baseline"
    candidate_dir = REPORT_DIR / "linescan-candidate"
    run([sys.executable, "scripts/evaluate_roll_suite.py", "--model", str(baseline_model), "--out", str(baseline_dir)])
    run([sys.executable, "scripts/evaluate_roll_suite.py", "--model", str(model), "--out", str(candidate_dir)])
    state("comparing")
    output = REPORT_DIR / "candidate-comparison.json"
    run([sys.executable, "scripts/compare_model_candidates.py", "--baseline-suite", str(baseline_dir / "suite.json"),
         "--candidate-suite", str(candidate_dir / "suite.json"), "--baseline-tiles", str(baseline_model.with_name("test_report.json")),
         "--candidate-tiles", str(model.with_name("test_report.json")), "--out", str(output),
         "--report", str(REPORT_DIR / "COMPARISON.md")])
    compared = json.loads(output.read_text())
    state("comparison_ready", qualified_for_review=compared["qualified_for_review"], reasons=compared["reasons"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-evaluation", action="store_true")
    parser.add_argument("--submit-cloud-evaluation", action="store_true")
    parser.add_argument("--run-config", type=Path)
    args = parser.parse_args()
    if args.run_config:
        cfg = json.loads(args.run_config.read_text())
        REF, EVALUATION_REF = cfg["training_ref"], cfg["evaluation_ref"]
        REPORT_DIR, DEST = ROOT / cfg["report_dir"], ROOT / cfg["artifact_dir"]
        STATUS = REPORT_DIR / "training-state.json"
        RUN_DIR, CONFIG_PATH = ROOT / cfg["evaluation_run_dir"], ROOT / cfg["train_config_path"]
    try:
        main(args.cloud_evaluation, args.submit_cloud_evaluation)
    except Exception as exc:
        state("needs_attention", error_type=type(exc).__name__, detail=str(exc)[:300])
        report = REPORT_DIR / "COMPARISON.md"
        if not (REPORT_DIR / "candidate-comparison.json").exists():
            report.write_text("# মডেলের তুলনা এখনও শেষ হয়নি\n\n"
                              "Training, export বা পরীক্ষার কোনো ধাপে সমস্যা হয়েছে। বর্তমান অ্যাপের মডেল বদলানো হয়নি।\n\n"
                              f"সমস্যা: `{type(exc).__name__}: {str(exc)[:300]}`\n\n"
                              "বিস্তারিত অবস্থা: training-state.json; লগ: build/kaggle/candidate-collector.log\n")
        raise
