"""Resume renderer-matched data review, one video-gated pilot and conditional final training.

No production writes. A detached supervise phase can finish evaluation while the chat is interrupted.
Visual review must already be recorded before any GPU work starts. Final-test labels stay closed in
the pilot; final fine-tuning runs only after both GPU and laptop-CPU pilot improvement conditions pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

os.environ["THREADEYE_EXPERIMENT"] = "round4"
import run_linescan_round3 as base

ROOT, STAGE, DOC = base.ROOT, base.STAGE, base.DOC
sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "backend"), str(ROOT / "ml/kaggle")]
VIDEO_PREP = base.CONFIG["video_preparation_job"]
PILOT = "shashwatanandi2004/threadeye-linescan-round4-pilot"
original_download = base.download


def download(ref, destination, pattern):
    if ref == base.PREP and pattern.startswith("videos/"):
        ref = VIDEO_PREP
    return original_download(ref, destination, pattern)


base.download = download


def submit(mode):
    if (base.DEADLINE - datetime.now(UTC)).total_seconds() < (
        1200 if mode == "pilot" else 2400
    ):
        raise TimeoutError("insufficient continuation budget for a new training job")
    checked = json.loads((STAGE / "review/checks.json").read_text())
    approved = json.loads((STAGE / "review/approved.json").read_text())
    if approved["preparation_sha256"] != checked["preparation_sha256"]:
        raise ValueError("visual review belongs to another prepared dataset")
    report = json.loads((DOC / "preparation.json").read_text())
    if report.get("target_frame_pipeline") != "actual simulator raster and camera":
        raise ValueError("renderer-matched data contract is missing")
    for split in ["train", "val"]:
        rows = json.loads(
            (STAGE / "preview-data" / split / "provenance.json").read_text()
        )
        if any(
            not row.get("background_policy") for row in rows if row["kind"] != "replay"
        ):
            raise ValueError("coherent-background renderer policy is missing")
        kinds = {row["file"]: row["kind"] for row in rows}
        annotations = json.loads(
            (STAGE / "preview-data" / split / "annotations.json").read_text()
        )
        if any(
            im["height"] > 320 or im["width"] != 640
            for im in annotations["images"]
            if kinds[im["file_name"]] != "replay"
        ):
            raise ValueError(
                "target frame would be resized by rectangular training input"
            )
    job = STAGE / (mode + "-job")
    job.mkdir(exist_ok=True)
    frozen = json.loads((DOC / "frozen_videos.json").read_text())
    env = {
        "THREADEYE_ROUND3_DEADLINE": base.DEADLINE.isoformat(),
        "THREADEYE_ROUND3_BUDGET_SECONDS": str(
            max(60, int((base.DEADLINE - datetime.now(UTC)).total_seconds()) - 300)
        ),
        "THREADEYE_VIDEO_MANIFEST_SHA": hashlib.sha256(
            json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "THREADEYE_PREP_SOURCE_SLUG": "threadeye-linescan-round4-prepare",
        "THREADEYE_PREPARATION_SHA": hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "THREADEYE_METADATA_HASHES": json.dumps(checked["metadata_sha256"]),
        "THREADEYE_VIDEO_SOURCE_SLUG": "threadeye-linescan-round3-prepare",
        "THREADEYE_TRAIN_MODE": "rendered_pilot"
        if mode == "pilot"
        else "rendered_final",
        "THREADEYE_MODEL_VERSION": "linescan-round4-rendered-" + mode,
        "THREADEYE_TRAIN_HEIGHT": "320",
        "THREADEYE_EVAL_LAYOUTS": "whole,tiles",
        "THREADEYE_EVAL_SCALES": "1",
        "THREADEYE_ROUND_OUTPUT": "/kaggle/working/round4",
    }
    if mode == "final":
        proof = DOC / "pilot-selection.json"
        env["THREADEYE_REUSE_PILOTS_SHA"] = base.sha(proof)
        env["THREADEYE_REUSE_PILOTS_PATH"] = "docs/model/round4/pilot-selection.json"
    bootstrap = "import os,runpy\nfrom pathlib import Path\n"
    bootstrap += "os.environ.update(" + repr(env) + ")\n"
    bootstrap += (
        'script=Path("/kaggle/working/train_implementation.py")\nscript.write_text('
        + repr((ROOT / "ml/kaggle/train_linescan.py").read_text())
        + ')\nrunpy.run_path(str(script),run_name="__main__")\n'
    )
    (job / "run.py").write_text(bootstrap)
    old_meta = json.loads(
        (
            ROOT / "build/kaggle/existing/threadeye-train-2/kernel-metadata.json"
        ).read_text()
    )
    ref = PILOT if mode == "pilot" else base.TRAIN
    meta = {
        "id": ref,
        "title": ref.split("/")[1],
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "docker_image": old_meta["docker_image"],
        "dataset_sources": [
            base.CODE,
            "shashwatanandi2004/threadeye-roll-evaluation-20261104",
        ],
        "kernel_sources": [
            "shashwatanandi2004/threadeye-train-2",
            "shashwatanandi2004/threadeye-linescan-r2",
            base.PREP,
            VIDEO_PREP,
            "shashwatanandi2004/threadeye-pack-dataset",
        ],
    }
    (job / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))
    result = base.kaggle(
        [
            "kernels",
            "push",
            "-p",
            str(job),
            "--timeout",
            str(max(60, int((base.DEADLINE - datetime.now(UTC)).total_seconds()))),
        ]
    )
    (job / "submission.txt").write_text(result)
    if "not valid kernel sources" in result:
        raise ValueError("required frozen notebook source was rejected")
    base.state("renderer_" + mode + "_submitted", job=ref)


def collect_pilot():
    base.wait(PILOT, "renderer_pilot_running")
    dest = STAGE / "pilot-output"
    download(
        PILOT,
        dest,
        r"(status\.json|pilots\.json|selection\.json|renderer_pilot\.json|validation_modes\.json|final_test\.json|candidate/(threadeye_s\.onnx|model_info\.json))$",
    )
    status = json.loads(base.one(dest, "status.json").read_text())
    if status["phase"] != "renderer_pilot_evaluated":
        raise ValueError("GPU pilot did not complete its video evaluation")
    model = base.one(dest, "threadeye_s.onnx")
    if base.sha(model) != status["sha256"]:
        raise ValueError("pilot artifact identity differs")
    from evaluate_linescan import aggregate
    from linescan_release import rendered_pilot_reasons
    from measure_impact import measure

    summary = {}
    for kind, names in [
        (
            "regression",
            [
                "linescan_roll",
                "demo_basic_roll",
                "demo_mixed_roll",
                "demo_challenge_roll",
            ],
        ),
        ("validation", [f"val_{n}" for n in range(4)]),
    ]:
        rows = []
        for name in names:
            if datetime.now(UTC) >= base.DEADLINE:
                raise TimeoutError(
                    "pilot CPU verification reached continuation deadline"
                )
            directory = (
                ROOT / "data" / name
                if kind == "regression"
                else STAGE / "normalized-video-inputs" / name
            )
            base.state("renderer_pilot_cpu_verification", dataset=name)
            result = measure(model, directory, threads=2)
            (DOC / f"pilot-cpu-{name}.json").write_text(json.dumps(result, indent=2))
            e = result["evaluation"]
            rows.append(
                {
                    "dataset": name,
                    "tp": e["tp"],
                    "fp": e["fp"],
                    "fn": e["fn"],
                    "broken_truth": result["broken_yarn_truth"],
                    "broken_right": result["broken_yarn_right"],
                    "cpu_ratio": result["timing"][
                        "headless_seconds_including_model_setup"
                    ]
                    / result["timing"]["video_duration_seconds"],
                }
            )
        summary[kind] = {"metrics": aggregate(rows), "rolls": rows}
    selection = json.loads(base.one(dest, "selection.json").read_text())
    native = selection["selected"]["metrics"]
    reasons = rendered_pilot_reasons(
        summary["regression"]["rolls"],
        native,
        summary["validation"]["metrics"],
        base.CONFIG["pilot_gate"],
    )
    summary.update(
        native_validation=native,
        pilot_gate_passed=not reasons,
        reasons=reasons,
        model_sha256=base.sha(model),
        final_test_evaluated=False,
        model_deployed=False,
    )
    (DOC / "pilot-result.json").write_text(json.dumps(summary, indent=2))
    lines = [
        "# Renderer-matched two-epoch pilot",
        "",
        f"Improvement gate passed: {not reasons}",
        "",
        "| Dataset | TP | FP | FN | Correct broken yarn |",
        "|---|---:|---:|---:|---:|",
    ]
    for group in ["regression", "validation"]:
        for r in summary[group]["rolls"]:
            lines.append(
                f"| {r['dataset']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['broken_right']}/{r['broken_truth']} |"
            )
    lines += [
        "",
        "Native image validation: "
        + json.dumps(
            {k: native[k] for k in ["precision", "recall", "broken_right_recall"]}
        ),
        "",
        "## Improvement blockers",
        "",
        *["- " + reason for reason in reasons],
        "",
        "Final-test labels were not evaluated. The production model and historical inspections remain unchanged.",
    ]
    (DOC / "PILOT_REPORT.md").write_text("\n".join(lines) + "\n")
    if reasons:
        base.state("renderer_pilot_not_qualified", reasons=reasons)
        return False
    selected = selection["selected"]
    proof = {
        "source_job": PILOT,
        "pilot_model_sha256": base.sha(model),
        "pilot_cpu_result_sha256": base.sha(DOC / "pilot-result.json"),
        "pilots": [
            {
                "name": "renderer_pilot",
                "starting_source": "round2",
                "lr": selected["lr"],
                "metrics": native,
            }
        ],
    }
    (DOC / "pilot-selection.json").write_text(json.dumps(proof, indent=2))
    base.state("renderer_pilot_qualified", model_sha256=base.sha(model))
    return True


def supervise():
    if not collect_pilot():
        return
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/package_rendered_linescan.py")], check=True
    )
    base.kaggle(
        [
            "datasets",
            "version",
            "-p",
            str(STAGE / "code"),
            "-m",
            "CPU video-gated pilot passed; frozen final configuration",
            "--dir-mode",
            "zip",
        ]
    )
    while datetime.now(UTC) < base.DEADLINE:
        if "ready" in base.kaggle(["datasets", "status", base.CODE]).lower():
            break
        time.sleep(15)
    submit("final")
    base.collect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=[
            "review",
            "pilot",
            "supervise",
            "collect-pilot",
            "final",
            "collect-final",
        ],
    )
    args = parser.parse_args()
    try:
        {
            "review": base.preparation,
            "pilot": lambda: submit("pilot"),
            "supervise": supervise,
            "collect-pilot": collect_pilot,
            "final": lambda: submit("final"),
            "collect-final": base.collect,
        }[args.phase]()
    except Exception as exc:
        base.state(
            "needs_attention", error_type=type(exc).__name__, detail=str(exc)[:400]
        )
        raise
