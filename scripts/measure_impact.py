"""Reproduce detection/decision evidence and optionally summarize a paired human pilot.

Run with backend/.venv/bin/python scripts/measure_impact.py --out docs/impact.
No database, cloud credentials, training or dataset mutation is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from threadeye.core.evaluation import Prediction, evaluate  # noqa: E402
from threadeye.core.providers import ProviderContext  # noqa: E402
from threadeye.core.runner import RollSpec, Runner  # noqa: E402
from threadeye.core.scoring.four_point import RollGeometry  # noqa: E402
from threadeye.core.scoring.profile import simulator_parity_profile  # noqa: E402
from threadeye.datasets.answer_key import load_answer_key  # noqa: E402
from threadeye.providers.local_model import LocalModelDetector  # noqa: E402
from threadeye.services.benchmark import score_answer_key, truth_from_key  # noqa: E402
from threadeye.services.impact import read_pilot, summarize_pilot  # noqa: E402
from threadeye.sources.simulated_roll import VideoFileSource  # noqa: E402


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def measure(model: Path, roll: Path) -> dict:
    key = load_answer_key(roll, require_media=True)
    source = VideoFileSource(roll)
    meta = source.parsed.meta
    profile = simulator_parity_profile()
    started = perf_counter()
    detector = LocalModelDetector({"model_path": str(model)}, ProviderContext())
    runner = Runner(
        source,
        detector,
        profile,
        RollSpec(width_in=meta.fabric_width_in, declared_length_yd=meta.roll_length_yd),
        inspection_id="impact-evaluation",
    )
    runner.run_to_end()
    elapsed = perf_counter() - started
    truths, nuisances = truth_from_key(key, meta.px_per_cm)
    predictions = []
    for track in runner.deduper.tracks:
        view = runner.defect_view(track)
        predictions.append(
            Prediction(
                track.defect_no,
                view["current_cls"],
                track.box,
                view["kind"] == "defect",
                view["nondefect_category"],
            )
        )
    evaluation = evaluate(
        predictions,
        truths,
        nuisances,
        fabric_width_cm=meta.fabric_width_cm,
        selvage_band_cm=meta.selvage_band_px / meta.px_per_cm,
    )
    runner.confirm_all()  # Explicit replay assumption, NOT a recorded inspector session.
    score = runner.score(final=True)
    if score is None:
        raise ValueError("roll has no scorable length")
    oracle = score_answer_key(
        key,
        meta.px_per_cm,
        RollGeometry(meta.roll_length_yd, meta.fabric_width_in, meta.fabric_width_cm),
        profile,
    )
    hashes = {
        p.name: sha256(p)
        for p in [
            model,
            model.with_name("model_info.json"),
            roll / "roll_meta.json",
            roll / "frames.csv",
            roll / "ground_truth.csv",
            roll / "nuisance.csv",
            roll / meta.video,
        ]
    }
    return {
        "dataset": roll.name,
        "source": json.loads((roll / "roll_meta.json").read_text())["source"],
        "simulated_video": True,
        "real_model_inference": True,
        "profile": profile.name,
        "sha256": hashes,
        "evaluation": evaluation.as_dict(),
        "matches": evaluation.matches,
        "missed_defects": [
            {"id": t.defect_id, "class": t.cls, "yard": round(t.box.center_yd, 3)}
            for t in truths
            if t.defect_id in evaluation.missed
        ],
        "timing": {
            "headless_seconds_including_model_setup": round(elapsed, 3),
            "video_duration_seconds": round(len(runner.track) / meta.fps, 3),
            "sampled_frames": len(runner.plan.samples),
        },
        "decision_replay": {
            "assumption": "Auto-confirm detections without human corrections. A replay, not a production decision.",
            "model_points": score.total_points,
            "model_per_100": round(score.per_100, 2),
            "model_verdict": score.verdict,
            "oracle_points": oracle.total_points,
            "oracle_per_100": round(oracle.per_100, 2),
            "oracle_verdict": oracle.verdict,
            "verdict_agrees": score.verdict == oracle.verdict,
        },
    }


def markdown(report: dict) -> str:
    demo = report["demo"]
    ev, decision, timing = demo["evaluation"], demo["decision_replay"], demo["timing"]
    lines = [
        "# ThreadEye impact evidence",
        "",
        "**SIMULATED VIDEO / REAL MODEL INFERENCE. Laboratory replay; factory impact has not been measured.**",
        "",
        f"Measured at (UTC): {report['measured_at_utc']}. Code revision: `{report['code_revision']}`.",
        "Local changes may exist; implementation hashes in evidence.json identify the code used for this run.",
        f"Dataset: `{demo['dataset']}` ({demo['source']}). Profile: `{demo['profile']}`.",
        "",
        "## Measured detection results",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| True defects found | {ev['tp']} / {ev['tp'] + ev['fn']} |",
        f"| False alarms after pipeline filtering | {ev['fp']} |",
        f"| Recall | {ev['recall'] * 100:.2f}% |",
        f"| Precision | {ev['precision'] * 100:.2f}% |",
        f"| Headless processing, including model setup | {timing['headless_seconds_including_model_setup']} s |",
        f"| Source video duration | {timing['video_duration_seconds']} s |",
        "",
        "Processing time excludes browser, network, database writes, human review and reporting. "
        "It is not inspection time saved or a production throughput measurement.",
        "Matching uses the existing roll evaluator: IoU > 0.3 OR centres within 3 cm, "
        "greedy one-to-one. Class accuracy is separate. The tile benchmark uses a different matching rule.",
        "",
        "## Decision risk: model detections versus answer-key oracle",
        "",
        decision["assumption"],
        "",
        "| Replay | Points | Points / 100 sq yd | Verdict |",
        "|---|---:|---:|---|",
        f"| Model detections | {decision['model_points']} | {decision['model_per_100']} "
        f"| {decision['model_verdict']} |",
        f"| Answer-key oracle | {decision['oracle_points']} | {decision['oracle_per_100']} "
        f"| {decision['oracle_verdict']} |",
        "",
        "The oracle is an evaluation reference, not a measured manual-inspection baseline. "
        "The model-only verdict cannot serve as an autonomous release decision; inspector review remains necessary.",
        "",
        "Missed defects: " + "; ".join(f"#{d['id']} {d['class']} at {d['yard']} yd" for d in demo["missed_defects"]),
        "",
        "## Human and business impact",
        "",
    ]
    pilot = report["paired_pilot"]
    if pilot is None:
        lines += [
            "**Not measured:** manual versus assisted inspection time, reduction in human misses, "
            "usable-fabric gain and financial loss reduction. No savings claim is supported yet."
        ]
    else:
        lines += [
            "User-supplied paired observations; collection quality must be reviewed against PILOT_PROTOCOL.md. "
            "Negative reductions mean the assisted result was worse. These are descriptive totals, not causal proof.",
            "",
            "| Paired pilot metric | Result |",
            "|---|---:|",
        ]
        lines += [f"| {k} | {'Not measured / undefined' if v is None else v} |" for k, v in pilot.items()]
    lines += [
        "",
        "## Limits and reproduction",
        "",
        "One short, simulated roll is a regression fixture; it has been used repeatedly during development. "
        "Its source fabric is held out of training. This is not a fresh blind test or evidence of factory-wide impact.",
        "Bounding boxes do not prove cutting/yield improvement. No monetary value is assigned to a missed defect.",
        "",
        "Run `make impact` from the repository root. See `PILOT_PROTOCOL.md` for paired human measurements. "
        "Hashes, machine details, evaluation output and optional pilot-input hash are in `evidence.json`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "data/model/threadeye_s.onnx")
    parser.add_argument("--roll", type=Path, default=ROOT / "data/linescan_roll")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/impact")
    parser.add_argument("--pilot-csv", type=Path)
    args = parser.parse_args()
    # Validate pilot inputs before doing expensive inference or writing any report.
    pilot = summarize_pilot(read_pilot(args.pilot_csv)) if args.pilot_csv else None
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "code_revision": revision,
        "implementation_sha256": {
            str(p.relative_to(ROOT)): sha256(p)
            for p in sorted([*(ROOT / "backend/threadeye").rglob("*.py"), Path(__file__).resolve()])
        },
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor(),
            "architecture": platform.machine(),
            "logical_cpus": os.cpu_count(),
        },
        "runtime_versions": {name: version(name) for name in ("onnxruntime", "numpy", "opencv-python-headless")},
        "demo": measure(args.model, args.roll),
        "paired_pilot": pilot,
        "pilot_csv_sha256": sha256(args.pilot_csv) if args.pilot_csv else None,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "evidence.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "REPORT.md").write_text(markdown(report), encoding="utf-8")
    print(f"Written: {args.out / 'REPORT.md'} and evidence.json")


if __name__ == "__main__":
    main()
