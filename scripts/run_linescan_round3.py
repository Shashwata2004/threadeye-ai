"""Resume bounded Kaggle preparation/training/CPU verification without production writes.

Phases are explicit so the actual labelled previews are inspected before the GPU job is submitted.
All sources/checkpoints are existing private Kaggle artifacts; code input contains no credentials.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUND = os.environ.get("THREADEYE_EXPERIMENT", "round3")
if ROUND not in {"round3", "round4"}:
    raise ValueError("unknown line-scan experiment")
STAGE = ROOT / "build/kaggle" / ROUND
DOC = ROOT / "docs/model" / ROUND
CONFIG = json.loads((DOC / "run.json").read_text())
PREP = CONFIG.get(
    "preparation_job", "shashwatanandi2004/threadeye-linescan-round3-prepare/v2"
)
TRAIN = CONFIG.get("training_job", "shashwatanandi2004/threadeye-linescan-round3-train")
CODE = CONFIG.get("code_dataset", "shashwatanandi2004/threadeye-linescan-round3-code")
DEADLINE = datetime.fromisoformat(
    CONFIG.get("continuation_deadline_utc", CONFIG["deadline_utc"])
)
UV = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
CLI = [UV, "tool", "run", "--from", "kaggle==2.2.4", "--with", "six", "kaggle"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(phase, **extra):
    payload = {
        "phase": phase,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "deadline_utc": DEADLINE.isoformat(),
        "original_deadline_utc": CONFIG["deadline_utc"],
        "running_model_changed": False,
        **extra,
    }
    tmp = DOC / "state.tmp"
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(DOC / "state.json")
    print(json.dumps(payload), flush=True)


def kaggle(args):
    r = subprocess.run(
        [*CLI, *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=180
    )
    return r.stdout


def status(ref):
    return subprocess.check_output(
        [*CLI[:-1], "python", str(ROOT / "scripts/kaggle_artifacts.py"), "status", ref],
        text=True,
        timeout=180,
    )


def wait(ref, phase):
    while datetime.now(UTC) < DEADLINE:
        current = status(ref)
        if '"COMPLETE"' in current:
            return
        if any(x in current for x in ['"ERROR"', "CANCEL_ACKNOWLEDGED"]):
            raise RuntimeError(f"{ref}: job failed; inspect private execution log")
        state(phase, job=ref)
        time.sleep(45)
    raise TimeoutError("six-hour experiment deadline reached")


def download(ref, dest, pattern):
    dest.mkdir(parents=True, exist_ok=True)
    print("DOWNLOAD", ref, pattern, flush=True)
    print(
        subprocess.check_output(
            [
                *CLI[:-1],
                "python",
                str(ROOT / "scripts/kaggle_artifacts.py"),
                "download",
                ref,
                "--out",
                str(dest),
                "--pattern",
                pattern,
            ],
            text=True,
            timeout=600,
        ),
        flush=True,
    )


def one(root, name):
    candidates = list(root.rglob(name))
    if len(candidates) != 1:
        raise ValueError(f"expected one {name}; found {len(candidates)}")
    return candidates[0]


def preparation():
    diagnostics = ROOT / CONFIG.get(
        "prior_diagnostics_dir", str(STAGE.relative_to(ROOT) / "diagnostics")
    )
    if len(list(diagnostics.glob("*/*/*.json"))) != 36:
        raise ValueError("diagnostic matrix incomplete")
    for p in diagnostics.glob("*/*/*.json"):
        if json.loads(p.read_text()).get("analysis_version") != 2:
            raise ValueError("diagnostic analysis has not been verified")
    wait(PREP, "data_preparation_running")
    dest = STAGE / "prepared-output"
    download(
        PREP,
        dest,
        r"(preparation\.json|frozen_videos\.json)$",
    )
    report = one(dest, "preparation.json")
    prep = json.loads(report.read_text())
    manifest = (
        ROOT / "build/kaggle/existing/packed-metadata/threadeye_packed/manifest.csv"
    )
    if prep["manifest_sha256"] != sha(manifest):
        raise ValueError("prepared dataset manifest differs")
    rows = list(csv.DictReader(manifest.open()))
    members = {}
    for r in rows:
        members.setdefault(r["original"], set()).add(r["split"])
    sets = {}
    annotations = {}
    provenance = {}
    preview_data = STAGE / "preview-data"
    subprocess.run(
        [
            *CLI[:-1],
            "python",
            str(ROOT / "scripts/fetch_linescan_previews.py"),
            "--ref",
            PREP,
            "--out",
            str(preview_data),
        ],
        check=True,
        cwd=ROOT,
    )
    for split in ["train", "val"]:
        annotations[split] = json.loads(
            (preview_data / split / "annotations.json").read_text()
        )
        provenance[split] = json.loads(
            (preview_data / split / "provenance.json").read_text()
        )
        sets[split] = {
            group for r in provenance[split] for group in r.get("groups", [r["group"]])
        }
        if any(
            members[original] != {"train"}
            for r in provenance[split]
            for original in r.get("originals", [r["original"]])
        ):
            raise ValueError("test pixels entered fine-tuning data")
    if sets["train"] & sets["val"]:
        raise ValueError("train/validation source leakage")
    frozen = json.loads(one(dest, "frozen_videos.json").read_text())
    for video in frozen["val"]:
        if sets["train"] & set(video["groups"]):
            raise ValueError("validation video donor in train")
    for video in frozen["test"]:
        if any(members[original] != {"test"} for original in video["originals"]):
            raise ValueError("final video is not held-out test")
    expected_count = CONFIG.get("train_images", 10000)
    if prep["splits"]["train"]["buckets"] != {
        "target": expected_count // 2,
        "replay": expected_count * 3 // 10,
        "clean": expected_count // 5,
    }:
        raise ValueError("training mixture differs")
    from PIL import Image, ImageDraw

    data = annotations["train"]
    anns = {}
    prov = {p["file"]: p for p in provenance["train"]}
    for a in data["annotations"]:
        anns.setdefault(a["image_id"], []).append(a)
    selected = [
        im
        for im in data["images"]
        if (preview_data / "train" / im["file_name"]).is_file()
    ]
    canvas = Image.new("RGB", (1280, 300 * ((len(selected) + 2) // 3)), (25, 25, 25))
    draw = ImageDraw.Draw(canvas)
    names = {c["id"]: c["name"] for c in data["categories"]}
    for n, im in enumerate(selected):
        image = Image.open(preview_data / "train" / im["file_name"]).convert("RGB")
        pen = ImageDraw.Draw(image)
        for a in anns.get(im["id"], []):
            x, y, w, h = a["bbox"]
            pen.rectangle((x, y, x + w, y + h), outline="yellow", width=2)
            pen.text((x, max(0, y - 12)), names[a["category_id"]], fill="yellow")
        image.thumbnail((415, 248))
        x = (n % 3) * 425
        y = (n // 3) * 300
        canvas.paste(image, (x, y))
        p = prov[im["file_name"]]
        draw.text((x + 3, y + 252), im["file_name"] + " " + p["kind"], fill="white")
        draw.text((x + 3, y + 268), p["original"][-55:], fill="white")
    review = STAGE / "review"
    review.mkdir(exist_ok=True)
    canvas.save(review / "previews.jpg", quality=95)
    proof = {
        "preparation_sha256": sha(report),
        "metadata_sha256": {
            str(p.relative_to(preview_data)): sha(p)
            for p in preview_data.glob("*/*.json")
        },
        "groups_disjoint": True,
        "previews": str(review / "previews.jpg"),
        "summary": prep["splits"],
        "requires_agent_visual_review": True,
    }
    (review / "checks.json").write_text(json.dumps(proof, indent=2))
    shutil.copy(report, DOC / "preparation.json")
    download(
        PREP,
        dest,
        r"videos/val_.*\.(mp4|json|csv|png)$|videos/test_\d/roll_meta\.json$",
    )
    sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "backend")]
    from linescan_metadata import stage_videos
    from threadeye.datasets.contracts import validate_dataset

    original = one(dest, "frozen_videos.json")
    normalized, manifest = stage_videos(
        original.parent, STAGE / "normalized-video-inputs"
    )
    for n in range(4):
        contract, _ = validate_dataset(normalized / f"val_{n}", require_media=True)
        if not contract.ok:
            raise ValueError(
                "validation video contract failed: " + str(contract.errors)
            )
    shutil.copy(original, DOC / "frozen_videos-original.json")
    (DOC / "frozen_videos.json").write_text(json.dumps(manifest, indent=2))
    state(
        "label_previews_ready",
        preview=str(review / "previews.jpg"),
        preparation_sha256=proof["preparation_sha256"],
    )


def training():
    sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "backend")]
    from linescan_metadata import stage_videos
    from threadeye.datasets.contracts import validate_dataset

    original = one(STAGE / "prepared-output", "frozen_videos.json")
    video_root, manifest = stage_videos(
        original.parent, STAGE / "normalized-video-inputs"
    )
    if manifest != json.loads((DOC / "frozen_videos.json").read_text()):
        raise ValueError("normalized frozen-video identity differs")
    for n in range(4):
        contract, _ = validate_dataset(video_root / f"val_{n}", require_media=True)
        if not contract.ok:
            raise ValueError("validation video contract failed before GPU submission")
    checked = json.loads((STAGE / "review/checks.json").read_text())
    approved = json.loads((STAGE / "review/approved.json").read_text())
    if checked["preparation_sha256"] != approved["preparation_sha256"]:
        raise ValueError("preview approval is for another dataset")
    if (DEADLINE - datetime.now(UTC)).total_seconds() < 3600:
        raise TimeoutError("less than one hour remains; no GPU job launched")
    if '"COMPLETE"' not in status(PREP):
        raise ValueError("cannot attach an unfinished preparation notebook")
    job = STAGE / "train-job"
    job.mkdir(exist_ok=True)
    seconds = max(60, int((DEADLINE - datetime.now(UTC)).total_seconds()) - 300)
    bootstrap = (
        'import os\nos.environ["THREADEYE_ROUND3_BUDGET_SECONDS"]='
        + repr(str(seconds))
        + "\n"
    )
    bootstrap += (
        'os.environ["THREADEYE_ROUND3_DEADLINE"]=' + repr(CONFIG["deadline_utc"]) + "\n"
    )
    bootstrap += (
        'os.environ["THREADEYE_VIDEO_MANIFEST_SHA"]='
        + repr(
            hashlib.sha256(
                json.dumps(
                    json.loads((DOC / "frozen_videos.json").read_text()),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        + "\n"
    )
    if CONFIG.get("reuse_pilots_sha"):
        bootstrap += (
            'os.environ["THREADEYE_REUSE_PILOTS_SHA"]='
            + repr(CONFIG["reuse_pilots_sha"])
            + "\n"
        )
    bootstrap += 'import runpy\nfrom pathlib import Path\ncode=Path("/kaggle/working/train_implementation.py")\n'
    bootstrap += (
        "code.write_text("
        + repr((ROOT / "ml/kaggle/train_linescan.py").read_text())
        + ')\nrunpy.run_path(str(code),run_name="__main__")\n'
    )
    (job / "run.py").write_text(bootstrap)
    meta = {
        "id": TRAIN,
        "title": TRAIN.split("/")[1],
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "docker_image": json.loads(
            (
                ROOT / "build/kaggle/existing/threadeye-train-2/kernel-metadata.json"
            ).read_text()
        )["docker_image"],
        "dataset_sources": [CODE],
        "kernel_sources": [
            "shashwatanandi2004/threadeye-train-2",
            "shashwatanandi2004/threadeye-linescan-r2",
            PREP,
            "shashwatanandi2004/threadeye-pack-dataset",
        ],
    }
    (job / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))
    result = kaggle(
        [
            "kernels",
            "push",
            "-p",
            str(job),
            "--timeout",
            str(max(60, int((DEADLINE - datetime.now(UTC)).total_seconds()))),
        ]
    )
    if "not valid kernel sources" in result:
        raise RuntimeError(result)
    (job / "submission.txt").write_text(result)
    state("gpu_pilots_submitted", job=TRAIN)


def collect():
    wait(TRAIN, "gpu_pilots_or_final_running")
    dest = STAGE / "candidate-output"
    download(
        TRAIN,
        dest,
        r"(status\.json|pilots\.json|selection\.json|validation_modes\.json|final_test\.json|candidate/(threadeye_s\.onnx|model_info\.json|test_report\.json))$",
    )
    status_file = one(dest, "status.json")
    result = json.loads(status_file.read_text())
    shutil.copy(status_file, DOC / "training-result.json")
    if result["phase"] != "candidate_ready_not_deployed":
        (DOC / "REPORT.md").write_text(
            "# Round-three result\n\nNo candidate passed the pilot gate. No final training or model replacement.\n\n"
            + json.dumps(result, indent=2)
        )
        state("pilot_gate_failed", result=result)
        return
    model = one(dest, "threadeye_s.onnx")
    selection = json.loads(one(dest, "selection.json").read_text())
    card = model.with_name("model_info.json")
    if sha(model) != result["sha256"]:
        raise ValueError("candidate model hash mismatch")
    model_card = json.loads(card.read_text())
    (DOC / "MODEL_CARD.md").write_text(
        f"# Line-scan {ROUND} candidate\n\n"
        + f"Model SHA256: `{sha(model)}`\n\nModel metadata SHA256: `{sha(card)}`\n\n"
        + f"Prepared input: `{PREP}`; preparation SHA256: `{sha(DOC / 'preparation.json')}`.\n\n"
        + f"Frozen video manifest SHA256: `{sha(DOC / 'frozen_videos.json')}`.\n\n"
        + "Validation-selected model metadata (thresholds are uncalibrated detector scores):\n\n```json\n"
        + json.dumps(model_card, indent=2)
        + "\n```\n\n"
        + "Training sources, original/variant counts and exclusions: [preparation.json](preparation.json). "
        + "Source isolation and validation limitations: [WORK_LOG.md](WORK_LOG.md). "
        + "Deployment eligibility and measured CPU/video results: [REPORT.md](REPORT.md). "
        + "The model is a candidate until every release gate passes; no business decision is automated by this card.\n"
    )
    download(PREP, STAGE / "prepared-output", r"videos/.*\.(mp4|json|csv|png)$")
    frozen = json.loads((DOC / "frozen_videos.json").read_text())
    sys.path.insert(0, str(ROOT / "ml"))
    from linescan_metadata import stage_videos

    raw_videos = one(STAGE / "prepared-output", "val_0").parent
    videos, normalized_frozen = stage_videos(
        raw_videos.parent, STAGE / "normalized-video-inputs"
    )
    if normalized_frozen != frozen:
        raise ValueError("normalized metadata differs from frozen pre-training repair")
    for split in ["val", "test"]:
        for n, record in enumerate(frozen[split]):
            directory = videos / f"{split}_{n}"
            for name, expected in record["files"].items():
                if (
                    name.endswith((".mp4", ".json", ".csv"))
                    and sha(directory / name) != expected
                ):
                    raise ValueError("frozen video changed")
    sys.path[:0] = [
        str(ROOT / "scripts"),
        str(ROOT / "backend"),
        str(ROOT / "ml"),
        str(ROOT / "ml/kaggle"),
    ]
    from evaluate_linescan import aggregate
    from linescan_release import release_reasons
    from measure_impact import measure

    summary = {}
    cpu = []
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
        ("final_test", [f"test_{n}" for n in range(4)]),
    ]:
        if kind == "final_test" and any(
            summary["validation"]["metrics"][k] < threshold
            for k, threshold in [
                ("precision", 0.85),
                ("recall", 0.85),
                ("broken_right_recall", 0.8),
            ]
        ):
            summary[kind] = {
                "metrics": {},
                "reason": "not opened: CPU validation failed",
            }
            break
        rows = []
        for name in names:
            if datetime.now(UTC) >= DEADLINE:
                raise TimeoutError(
                    "CPU verification reached experiment deadline; no deployment"
                )
            directory = ROOT / "data" / name if kind == "regression" else videos / name
            state("laptop_cpu_verification", dataset=name)
            report = measure(model, directory, threads=2)
            (DOC / f"cpu-{name}.json").write_text(json.dumps(report, indent=2))
            e = report["evaluation"]
            ratio = (
                report["timing"]["headless_seconds_including_model_setup"]
                / report["timing"]["video_duration_seconds"]
            )
            cpu.append(ratio)
            rows.append(
                {
                    "dataset": name,
                    "tp": e["tp"],
                    "fp": e["fp"],
                    "fn": e["fn"],
                    "broken_truth": report["broken_yarn_truth"],
                    "broken_right": report["broken_yarn_right"],
                    "cpu_ratio": ratio,
                }
            )
        summary[kind] = {"metrics": aggregate(rows), "rolls": rows}
    reasons = release_reasons(
        summary["regression"]["rolls"],
        summary["validation"]["metrics"],
        summary["final_test"]["metrics"],
        cpu,
        native_validation=selection["selected"]["metrics"],
    )
    summary.update(
        {
            "model_sha256": sha(model),
            "native_validation": selection["selected"]["metrics"],
            "card_sha256": sha(card),
            "release_passed": not reasons,
            "reasons": reasons,
            "model_deployed": False,
        }
    )
    (DOC / "result.json").write_text(json.dumps(summary, indent=2))
    previous = json.loads(
        (ROOT / "docs/model/round2/candidate-comparison.json").read_text()
    )
    old_rows = {r["dataset"]: r for r in previous["rolls"]}
    lines = [
        f"# Line-scan {ROUND} result",
        "",
        f"Release gates passed: {not reasons}",
        f"Candidate model SHA256: `{sha(model)}`",
        "Current four videos are development regressions, not blind tests.",
        "",
        "## Existing four regression videos",
        "",
        "| Video | Original TP/FP | Round two TP/FP | New TP/FP/FN | Correct broken yarn | CPU / video |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in summary["regression"]["rolls"]:
        old = old_rows[r["dataset"]]
        lines.append(
            f"| {r['dataset']} | {old['before']['tp']}/{old['before']['fp']} | {old['after']['tp']}/{old['after']['fp']} | {r['tp']}/{r['fp']}/{r['fn']} | {r['broken_right']}/{r['broken_truth']} | {r['cpu_ratio']:.2f} |"
        )
    lines += [
        "",
        "## Native image validation",
        "",
        "| Model | Recall | Correct-class recall | Precision | Correct broken-yarn recall |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in ["baseline", "round2"]:
        path = DOC / f"native-{label}.json"
        if path.is_file():
            m = json.loads(path.read_text())
            lines.append(
                f"| {label} | {m['found_any_class']} | {m['found_right_class']} | {m['precision']} | {m['broken_right_recall']} |"
            )
    m = summary["native_validation"]
    lines += [
        f"| {CONFIG.get('round_label', 'Round three')} | {m['recall']} | {m['right_recall']} | {m['precision']} | {m['broken_right_recall']} |",
        "",
        "Old image thresholds are frozen production values; new thresholds were selected on this validation. This is a development comparison, not an independent test.",
    ]
    lines += [
        "",
        "## New validation videos: production-pipeline comparison",
        "",
        "| Video | Original TP/FP | Round two TP/FP | New TP/FP/FN | New correct broken yarn |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in summary["validation"].get("rolls", []):
        cells = []
        for label in ["baseline", "round2"]:
            path = DOC / f"video-{label}-{r['dataset']}.json"
            e = json.loads(path.read_text())["evaluation"] if path.is_file() else {}
            cells.append(f"{e.get('tp', 'unmeasured')}/{e.get('fp', 'unmeasured')}")
        lines.append(
            f"| {r['dataset']} | {cells[0]} | {cells[1]} | {r['tp']}/{r['fp']}/{r['fn']} | {r['broken_right']}/{r['broken_truth']} |"
        )
    for group in ["validation", "final_test"]:
        lines += [
            "",
            f"## {group}",
            "",
            json.dumps(summary[group]["metrics"], indent=2)
            if summary[group]["metrics"]
            else summary[group].get("reason", "not evaluated"),
        ]
    lines += [
        "",
        "## Selected inference and overall dataset comparison",
        "",
        json.dumps(
            {
                k: json.loads(card.read_text()).get(k)
                for k in [
                    "version",
                    "inference",
                    "infer_scale",
                    "postprocess",
                    "thresholds",
                    "export_parity",
                ]
            },
            indent=2,
        ),
        "",
        "| Model | Global recall | Correct-class recall | Precision | Correct broken-yarn recall |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, report_path in [
        ("Original 44 epoch", ROOT / "build/kaggle/baseline-model/test_report.json"),
        (
            "Round two",
            ROOT / "build/kaggle/round2/candidate-output/model/test_report.json",
        ),
        (CONFIG.get("round_label", "Round three"), model.with_name("test_report.json")),
    ]:
        if report_path.is_file():
            global_metrics = json.loads(report_path.read_text())
            lines.append(
                f"| {label} | {global_metrics.get('found_any_class')} | {global_metrics.get('found_right_class')} | {global_metrics.get('precision')} | {global_metrics.get('per_class', {}).get('broken_yarn', {}).get('recall')} |"
            )
    lines += [
        "",
        "Fine-tuning validation originals were seen by the starting checkpoints during older training. AITEX 006 still has one training original. Fresh final videos use non-AITEX official test donors because regression pools already used the AITEX test defects. Global results are advisory; they cannot conceal a line-scan failure.",
        "Global test uses the original native tile evaluation protocol, without video tracking/stitching. Frozen videos retain identical pixels/truth/frame coordinates; expected-score serialization alone was repaired before restarted final training (old/new metadata hashes are in frozen_videos.json).",
        "",
        "## Release blockers",
        "",
        *["- " + r for r in reasons],
        "",
        "No production model was changed by this collector. Original global test remains advisory.",
    ]
    (DOC / "REPORT.md").write_text("\n".join(lines) + "\n")
    state(
        "release_ready" if not reasons else "candidate_not_qualified",
        reasons=reasons,
        model_sha256=sha(model),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "train", "collect"])
    args = parser.parse_args()
    try:
        {"prepare": preparation, "train": training, "collect": collect}[args.phase]()
    except Exception as exc:
        state("needs_attention", error_type=type(exc).__name__, detail=str(exc)[:400])
        raise
