"""Private round-three pilots and validation-selected fine-tuning on existing Kaggle checkpoints.

Single-device training avoids the previous DDP evaluation barrier. No final-test video or global
test labels are opened during selection. All intermediate checkpoints remain in notebook output.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

START = time.monotonic()
DEADLINE = datetime.fromisoformat(
    os.environ.get("THREADEYE_ROUND3_DEADLINE", "2026-11-04T17:43:11+00:00")
)
DEADLINE = min(
    DEADLINE,
    datetime.now(UTC)
    + timedelta(
        seconds=int(os.environ.get("THREADEYE_ROUND3_BUDGET_SECONDS", "14400"))
    ),
)
print(
    "ROUND3_TRAIN_BOOT",
    datetime.now(UTC).isoformat(),
    "deadline",
    DEADLINE.isoformat(),
    flush=True,
)
RENDERED_PILOT = os.environ.get("THREADEYE_TRAIN_MODE") == "rendered_pilot"
INPUT_SHAPE = (int(os.environ.get("THREADEYE_TRAIN_HEIGHT", "640")), 640)
assert INPUT_SHAPE[0] % 32 == 0
OUT = Path(os.environ.get("THREADEYE_ROUND_OUTPUT", "/kaggle/working/round3"))
OUT.mkdir()


def find(name):
    inputs = Path("/kaggle/input")
    roots = (
        set(inputs.iterdir())
        | set(inputs.glob("datasets/*/*"))
        | set(inputs.glob("notebooks/*/*"))
    )
    suffixes = [
        name,
        "round3_code/" + name,
        "ml/" + name,
        "round3_code/ml/" + name,
        "prepared/" + name,
        "model/" + name,
        "runs/*/" + name,
        "threadeye_packed/" + name,
    ]
    return sorted(
        {p for r in roots for suffix in suffixes for p in r.glob(suffix) if p.is_file()}
    )


def run(argv, **kw):
    if datetime.now(UTC) >= DEADLINE:
        raise TimeoutError("six-hour experiment deadline reached")
    print("RUN", argv, flush=True)
    return subprocess.run(argv, check=True, **kw)


run(
    [
        sys.executable,
        "-m",
        "pip",
        "-q",
        "install",
        "loguru",
        "tabulate",
        "pycocotools",
        "thop",
        "ninja",
        "onnx",
        "onnxruntime",
        "scipy",
        "opencv-python-headless",
        "pydantic>=2.10,<3",
        "pydantic-settings",
        "pyyaml",
        "sqlalchemy",
        "psycopg[binary]",
    ]
)
code = Path("/kaggle/working/code")
bundles = find("round3_code.zip")
if bundles:
    with zipfile.ZipFile(bundles[0]) as archive:
        archive.extractall(code)
else:
    module = find("linescan_targeted.py")
    assert len(module) == 1
    shutil.copytree(module[0].parent.parent, code)
sys.path[:0] = [str(code / "ml"), str(code / "backend"), str(code / "scripts")]
from fabricdata.classes import DEFECT_CLASSES
from fabricdata.operating import Det, Truth, choose_thresholds, match, report
from linescan_metadata import stage_videos
from linescan_release import rank_validation
from threadeye.providers.local_model import stitch_running_yarn

prepared = find("preparation.json")
if os.environ.get("THREADEYE_PREP_SOURCE_SLUG"):
    prepared = [
        p for p in prepared if os.environ["THREADEYE_PREP_SOURCE_SLUG"] in p.parts
    ]
assert len(prepared) == 1, "prepared source output missing or ambiguous"
prepared = prepared[0].parent
prep = json.loads((prepared / "preparation.json").read_text())
assert prep["train_val_groups_disjoint"]
if os.environ.get("THREADEYE_PREPARATION_SHA"):
    assert (
        hashlib.sha256(
            json.dumps(prep, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == os.environ["THREADEYE_PREPARATION_SHA"]
    ), "prepared-data identity differs from visual review"
video_prepared = prepared
if os.environ.get("THREADEYE_VIDEO_SOURCE_SLUG"):
    matches = [
        p
        for p in find("frozen_videos.json")
        if os.environ["THREADEYE_VIDEO_SOURCE_SLUG"] in p.parts
    ]
    assert len(matches) == 1, "frozen video source missing/ambiguous"
    video_prepared = matches[0].parent
video_root, frozen_video_manifest = stage_videos(video_prepared, OUT / "video_inputs")
video_manifest_sha = hashlib.sha256(
    json.dumps(frozen_video_manifest, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
if os.environ.get("THREADEYE_VIDEO_MANIFEST_SHA"):
    assert video_manifest_sha == os.environ["THREADEYE_VIDEO_MANIFEST_SHA"], (
        "normalized video manifest differs"
    )
work = Path("/kaggle/working/data")
work.mkdir()
for split in ["train", "val"]:
    (work / split).mkdir()
    run(
        [
            "tar",
            "-xf",
            str(prepared / f"{split}_prepared.tar"),
            "-C",
            str(work / split),
            "--no-same-owner",
        ]
    )
expected_metadata = json.loads(os.environ.get("THREADEYE_METADATA_HASHES", "{}"))
for relative, expected in expected_metadata.items():
    assert hashlib.sha256((work / relative).read_bytes()).hexdigest() == expected, (
        "prepared annotation/provenance identity differs"
    )
categories = json.loads((work / "train/annotations.json").read_text())["categories"]
classes = [c["name"] for c in sorted(categories, key=lambda c: c["id"])]
val = json.loads((work / "val/annotations.json").read_text())
name_of = {i["id"]: i["file_name"] for i in val["images"]}
truths = [
    Truth(
        name_of[a["image_id"]],
        classes[a["category_id"] - 1],
        (
            a["bbox"][0],
            a["bbox"][1],
            a["bbox"][0] + a["bbox"][2],
            a["bbox"][1] + a["bbox"][3],
        ),
    )
    for a in val["annotations"]
]
YOLOX = Path("/kaggle/working/YOLOX")
run(
    [
        "git",
        "clone",
        "-q",
        "https://github.com/Megvii-BaseDetection/YOLOX.git",
        str(YOLOX),
    ]
)
COMMIT = "6ddff4824372906469a7fae2dc3206c7aa4bbaee"
run(["git", "checkout", "-q", COMMIT], cwd=YOLOX)
sys.path.insert(0, str(YOLOX))
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
os.environ["PYTHONPATH"] = str(YOLOX) + os.pathsep + os.environ.get("PYTHONPATH", "")
import cv2
import numpy as np
import torch
from yolox.data import ValTransform
from yolox.exp import get_exp
from yolox.utils import postprocess

# T4x2: keep controller-side validation on GPU 1; the single training process uses GPU 0.
torch.cuda.set_device(1 if torch.cuda.device_count() > 1 else 0)

# Checkpoint path selection is by notebook slug, never by whichever file has the newest timestamp.
checkpoints = find("latest_ckpt.pth")
baseline = next(p for p in checkpoints if "threadeye-train-2" in p.parts)
round2 = next(p for p in checkpoints if "threadeye-linescan-r2" in p.parts)
cache = {}
tf = ValTransform(legacy=False)
for im in val["images"]:
    image = cv2.imread(str(work / "val" / im["file_name"]))
    assert image is not None
    cache[im["file_name"]] = (
        tf(image, None, INPUT_SHAPE)[0],
        min(INPUT_SHAPE[0] / image.shape[0], INPUT_SHAPE[1] / image.shape[1]),
    )


def evaluate_checkpoint(checkpoint, exp_path, destination):
    started = time.perf_counter()
    destination.mkdir(parents=True, exist_ok=True)
    exp = get_exp(str(exp_path), None)
    model = exp.get_model()
    model.load_state_dict(
        torch.load(checkpoint, map_location="cpu", weights_only=False)["model"]
    )
    model.cuda().eval().half()
    names = list(cache)
    dets = []
    with torch.no_grad():
        for i in range(0, len(names), 16):
            chunk = names[i : i + 16]
            xs = np.stack([cache[n][0] for n in chunk])
            outputs = postprocess(
                model(torch.from_numpy(xs).cuda().half()), len(classes), 0.01, 0.45
            )
            for name, p in zip(chunk, outputs, strict=True):
                if p is None:
                    continue
                ratio = cache[name][1]
                for x0, y0, x1, y1, obj, cs, c in p.float().cpu().numpy().tolist():
                    dets.append(
                        Det(
                            name,
                            classes[int(c)],
                            obj * cs,
                            (x0 / ratio, y0 / ratio, x1 / ratio, y1 / ratio),
                        )
                    )
    del model, exp
    torch.cuda.empty_cache()
    # Per-class thresholds are selected on fine-tuning validation only. Require 85% precision
    # where possible, maximizing recall at that precision, with ties using fewer false alerts.
    thresholds = choose_thresholds(dets, truths, classes)
    for c in DEFECT_CLASSES:
        tc = [t for t in truths if t.cls == c]
        if not tc:
            continue
        trials = []
        for threshold in [i / 100 for i in range(2, 96, 2)]:
            dc = [d for d in dets if d.cls == c and d.score >= threshold]
            found, tp, dup = match(dc, tc, lambda a, b: a == b)
            fp = len(dc) - len(tp) - len(dup)
            precision = len(tp) / max(1, len(tp) + fp)
            if precision >= 0.85:
                trials.append((len(found) / len(tc), -fp, threshold))
        if trials:
            thresholds[c] = max(trials)[2]
    kept = [d for d in dets if d.score >= thresholds.get(d.cls, 0.3)]
    alternatives = []
    for stitch in (False, True):
        chosen = kept
        if stitch:
            byname = {}
            for d in kept:
                byname.setdefault(d.image, []).append((d.box, d.cls, d.score))
            chosen = [
                Det(n, c, s, b)
                for n, rows in byname.items()
                for b, c, s in stitch_running_yarn(rows)
            ]
        rep = report(
            chosen,
            truths,
            {c: 0 for c in classes},
            set(DEFECT_CLASSES),
            lambda _: "native-line-scan",
            names,
        )
        bd = [d for d in chosen if d.cls == "broken_yarn"]
        bt = [t for t in truths if t.cls == "broken_yarn"]
        found, _, _ = match(bd, bt, lambda a, b: a == b)
        metrics = {
            "precision": rep["precision"],
            "recall": rep["found_any_class"],
            "right_recall": rep["found_right_class"],
            "broken_right_recall": len(found) / max(1, len(bt)),
            "false_alarms": rep["false_alarms"],
            "seconds": time.perf_counter() - started,
            "stitch_yarn": stitch,
            "thresholds": thresholds,
            "report": rep,
        }
        alternatives.append(metrics)
    qualified = [m for m in alternatives if rank_validation(m) is not None]
    best = (
        max(qualified, key=rank_validation)
        if qualified
        else max(alternatives, key=lambda r: (r["precision"], r["broken_right_recall"]))
    )
    (destination / "validation.json").write_text(json.dumps(best, indent=2))
    (destination / "validation_detections.json").write_text(
        json.dumps([[d.image, d.cls, d.score, d.box] for d in dets])
    )
    print(
        "VALIDATION",
        str(checkpoint),
        {k: v for k, v in best.items() if k not in ["report", "thresholds"]},
        flush=True,
    )
    return best


def train(name, start, lr, epochs):
    if (DEADLINE - datetime.now(UTC)).total_seconds() < 900:
        raise TimeoutError("less than 15 minutes remain; no new training")
    destination = OUT / name
    destination.mkdir()
    exp_path = destination / "exp.py"
    exp_path.write_text(f"""from yolox.exp import Exp as Base
class Exp(Base):
 def __init__(self):
  super().__init__()
  self.depth,self.width=.33,.5
  self.num_classes={len(classes)}
  self.data_dir={str(work)!r}
  self.train_ann='train.json'
  self.val_ann='val.json'
  self.input_size=self.test_size={INPUT_SHAPE!r}
  self.max_epoch={epochs}
  self.no_aug_epochs=1
  self.warmup_epochs=1
  self.basic_lr_per_img*={lr}
  self.data_num_workers=4
  self.seed=202611043
  self.exp_name={name!r}
  self.output_dir={str(destination)!r}
  self.mosaic_prob=0
  self.degrees=0
  self.hsv_prob=.2
  self.enable_mixup=False
  self.mixup_prob=0
  self.random_size=(20,20)
  self.save_history_ckpt=True
 @property
 def eval_interval(self):return 1000000
 @eval_interval.setter
 def eval_interval(self,value):pass
 def get_data_loader(self,*args,**kwargs):
  import sys,json
  from pathlib import Path
  sys.path.insert(0,{str(code / "ml")!r})
  from linescan_targeted import BalancedStream
  loader=super().get_data_loader(*args,**kwargs)
  provenance=json.loads((Path(self.data_dir)/'train/provenance.json').read_text())
  kind_of={{row['file']:row['kind'] for row in provenance}}
  original=self.dataset
  while hasattr(original,'_dataset'):original=original._dataset
  kinds=[kind_of[original.coco.loadImgs(i)[0]['file_name']] for i in original.ids]
  loader.batch_sampler.sampler=BalancedStream(kinds,202611043)
  return loader
 def get_trainer(self,args):
  import sys
  sys.path.insert(0,{str(code / "ml")!r})
  from yolox.core import Trainer
  from linescan_training import history_trainer
  return history_trainer(Trainer)(self,args)
 def random_resize(self,*args,**kwargs):
  return self.input_size if self.input_size!=(640,640) else super().random_resize(*args,**kwargs)
 def get_dataset(self,cache=False,cache_type='ram'):
  from yolox.data import COCODataset,TrainTransform
  return COCODataset(data_dir=self.data_dir,json_file=self.train_ann,name='train',img_size=self.input_size,
   preproc=TrainTransform(max_labels=100,flip_prob=.5,hsv_prob=.2))
 def get_eval_dataset(self,**kwargs):
  from yolox.data import COCODataset,ValTransform
  return COCODataset(data_dir=self.data_dir,json_file=self.val_ann,name='val',img_size=self.test_size,
   preproc=ValTransform(legacy=False))
""")
    (work / "annotations").mkdir(exist_ok=True)
    for split in ["train", "val"]:
        shutil.copy(
            work / split / "annotations.json", work / f"annotations/{split}.json"
        )
    # exp's COCODataset expects native train/val file layout; labels are never repacked/resampled.
    budget = max(1, int((DEADLINE - datetime.now(UTC)).total_seconds() - 300))
    command = [
        "timeout",
        "--signal=INT",
        "--kill-after=60s",
        str(budget) + "s",
        sys.executable,
        "tools/train.py",
        "-f",
        str(exp_path),
        "-d",
        "1",
        "-b",
        "8",
        "--fp16",
        "-c",
        str(start),
    ]
    run(command, cwd=YOLOX)
    directory = destination / name
    checkpoints = sorted(directory.glob("epoch_*_ckpt.pth"))
    # History names vary across the pinned trainer; latest is always a valid last-epoch checkpoint.
    if epochs <= 2:
        checkpoints = [directory / "latest_ckpt.pth"]
    else:
        checkpoints = [
            p
            for p in checkpoints
            if any(p.name == f"epoch_{n}_ckpt.pth" for n in (2, 4, 6, 8))
        ]
        if not checkpoints:
            raise RuntimeError("required epoch checkpoint history was not written")
    results = []
    for checkpoint in checkpoints:
        metrics = evaluate_checkpoint(
            checkpoint, exp_path, destination / checkpoint.stem
        )
        results.append(
            {
                "checkpoint": str(checkpoint),
                "exp": str(exp_path),
                "name": name,
                "lr": lr,
                "starting_checkpoint": str(start),
                "metrics": metrics,
            }
        )
    (destination / "results.json").write_text(json.dumps(results, indent=2))
    return results


pilots = []
recovery = os.environ.get("THREADEYE_REUSE_PILOTS_SHA")
if RENDERED_PILOT:
    pilots.extend(train("renderer_pilot", round2, 0.1, 2))
elif recovery:
    evidence = code / os.environ.get(
        "THREADEYE_REUSE_PILOTS_PATH", "docs/model/round3/pilots-recovery.json"
    )
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == recovery
    recorded = json.loads(evidence.read_text())
    for r in recorded["pilots"]:
        r["starting_checkpoint"] = str(
            round2 if r["starting_source"] == "round2" else baseline
        )
        pilots.append(r)
    print("REUSED_COMPLETED_PILOTS", recorded["source_job"], flush=True)
else:
    for name, lr in [("pilot_A", 0.1), ("pilot_B", 0.3)]:
        pilots.extend(train(name, baseline, lr, 2))
eligible = [r for r in pilots if rank_validation(r["metrics"]) is not None]
lr = (
    max(eligible, key=lambda r: rank_validation(r["metrics"]))["lr"]
    if eligible
    else 0.1
)
if not recovery and not RENDERED_PILOT:
    pilots.extend(train("pilot_C", round2, lr, 2))
(OUT / "pilots.json").write_text(json.dumps(pilots, indent=2))
eligible = [
    r
    for r in pilots
    if rank_validation(r["metrics"]) is not None
    and r["metrics"]["broken_right_recall"] > 0
]
if not eligible and not RENDERED_PILOT:
    (OUT / "status.json").write_text(
        json.dumps(
            {
                "phase": "pilot_gate_failed",
                "reason": "no pilot has positive broken recall at precision >=85%; no final training",
                "pilots": pilots,
            },
            indent=2,
        )
    )
    print("PILOT_GATE_FAILED", flush=True)
    sys.exit(0)
winner = (
    pilots[0]
    if RENDERED_PILOT
    else max(eligible, key=lambda r: rank_validation(r["metrics"]))
)
final = (
    pilots
    if RENDERED_PILOT
    else train("final", Path(winner["starting_checkpoint"]), winner["lr"], 8)
)
qualified = [r for r in final if rank_validation(r["metrics"]) is not None]
if not qualified and not RENDERED_PILOT:
    raise RuntimeError("no final checkpoint meets validation precision")
chosen = (
    max(qualified, key=lambda r: rank_validation(r["metrics"]))
    if qualified
    else max(
        final,
        key=lambda r: (r["metrics"]["precision"], r["metrics"]["broken_right_recall"]),
    )
)
candidate = OUT / "candidate"
candidate.mkdir()
shutil.copy(chosen["checkpoint"], candidate / "selected_ckpt.pth")
exp = get_exp(chosen["exp"], None)
model = exp.get_model()
model.load_state_dict(
    torch.load(chosen["checkpoint"], map_location="cpu", weights_only=False)["model"]
)
model.eval()
model.head.decode_in_inference = False
torch.onnx.export(
    model,
    torch.zeros(1, 3, *INPUT_SHAPE),
    str(candidate / "threadeye_s.onnx"),
    input_names=["images"],
    output_names=["output"],
    opset_version=17,
    dynamic_axes={
        "images": {0: "batch", 2: "height", 3: "width"},
        "output": {0: "batch", 1: "anchors"},
    },
    dynamo=False,
)
import onnxruntime as ort

# Compare real validation pixels at both native-strip and packed-tile shapes. The exported
# raw head is what production decodes; a successful export alone does not establish parity.
session = ort.InferenceSession(
    str(candidate / "threadeye_s.onnx"), providers=["CPUExecutionProvider"]
)
parity = []
sample = next(iter(cache.values()))[0][None].astype(np.float32)
for pixels in [sample, sample[:, :, :256, :]]:
    with torch.no_grad():
        expected = model(torch.from_numpy(pixels)).numpy()
    actual = session.run(None, {session.get_inputs()[0].name: pixels})[0]
    error = float(np.max(np.abs(expected - actual)))
    np.testing.assert_allclose(actual, expected, rtol=1e-3, atol=1e-4)
    parity.append({"shape": list(pixels.shape), "max_absolute_error": error})
(OUT / "export_parity.json").write_text(json.dumps(parity, indent=2))
del session
card = {
    "framework": "YOLOX",
    "yolox_commit": COMMIT,
    "runtime_versions": {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "numpy": np.__version__,
        "onnxruntime": ort.__version__,
    },
    "export_parity": parity,
    "size": "s",
    "input": list(INPUT_SHAPE),
    "classes": classes,
    "version": os.environ.get("THREADEYE_MODEL_VERSION", "linescan-round3"),
    "thresholds": chosen["metrics"]["thresholds"],
    "postprocess": {"stitch_yarn": chosen["metrics"]["stitch_yarn"]},
    "infer_scale": 1,
    "preprocessing": "native BGR, pad 114, whole-strip or tiles selected on validation only",
    "starting_checkpoint": winner["starting_checkpoint"],
    "selected_checkpoint": chosen["checkpoint"],
    "split_manifest_sha256": prep["manifest_sha256"],
    "frozen_video_manifest_sha256": video_manifest_sha,
    "video_manifest_hash_format": "canonical sorted JSON",
    "data_generation": {
        k: prep.get(k)
        for k in ["target_frame_pipeline", "broken_yarn_source_audit", "splits"]
    },
    "run_status": [
        "training: finished all epochs",
        "validation selected epoch checkpoint",
    ],
    "purpose": "simulated native line-scan; deployment requires independent release gates",
    "train_parameters": {
        "seed": 202611043,
        "lr_scale": winner["lr"],
        "epochs": 2 if RENDERED_PILOT else 8,
        "batch": 8,
        "buckets": {"target": 0.5, "replay": 0.3, "clean": 0.2},
    },
}
(candidate / "model_info.json").write_text(json.dumps(card, indent=2))
sys.path.insert(0, str(code / "ml/kaggle"))
from evaluate_linescan import TorchDetector, aggregate, video_metrics

model = model.cuda().half().eval()
validation_modes = []
for layout in os.environ.get("THREADEYE_EVAL_LAYOUTS", "whole,tiles,packed").split(","):
    for scale in tuple(
        int(value)
        for value in os.environ.get("THREADEYE_EVAL_SCALES", "1,2").split(",")
    ):
        for stitch in (False, True):
            if datetime.now(UTC) >= DEADLINE:
                raise TimeoutError("validation mode selection deadline")
            configuration = {
                "model_path": str(candidate / "threadeye_s.onnx"),
                "whole_strip": layout == "whole",
                "pack": layout == "packed",
                "infer_scale": scale,
                "stitch_yarn": stitch,
            }
            detector = TorchDetector(configuration, model)
            started = time.perf_counter()
            rows = [
                video_metrics(detector, p) for p in sorted(video_root.glob("val_*"))
            ]
            summary = aggregate(rows)
            summary["seconds"] = time.perf_counter() - started
            validation_modes.append(
                {"config": configuration, "metrics": summary, "rolls": rows}
            )
            print("VALIDATION_MODE", layout, scale, stitch, summary, flush=True)
choices = [m for m in validation_modes if rank_validation(m["metrics"]) is not None]
best_mode = (
    max(choices, key=lambda m: rank_validation(m["metrics"]))
    if choices
    else max(
        validation_modes,
        key=lambda m: (m["metrics"]["precision"], m["metrics"]["recall"]),
    )
)
(OUT / "validation_modes.json").write_text(json.dumps(validation_modes, indent=2))
cfg = best_mode["config"]
card["inference"] = {k: cfg[k] for k in ("whole_strip", "pack")}
card["infer_scale"] = cfg["infer_scale"]
card["postprocess"] = {"stitch_yarn": cfg["stitch_yarn"]}
card["preprocessing"] = (
    "native BGR, pad 114; inference layout and pixel scale selected only on held-out validation video groups"
)
card["validation_video_metrics"] = best_mode["metrics"]
(candidate / "model_info.json").write_text(json.dumps(card, indent=2))
if RENDERED_PILOT:
    from linescan_release import rendered_pilot_reasons

    bundles = find("roll_evaluation_bundle.tar.gz")
    if bundles:
        evaluation_root = Path("/kaggle/tmp/regression_evaluation")
        evaluation_root.mkdir(parents=True)
        run(
            [
                "tar",
                "-xzf",
                str(bundles[0]),
                "-C",
                str(evaluation_root),
                "--no-same-owner",
            ]
        )
    else:
        configs = find("evaluation-config.json")
        assert len(configs) == 1, "fixed regression video bundle missing"
        evaluation_root = configs[0].parent
    detector = TorchDetector(cfg, model)
    expected_regression = json.loads(
        (code / "docs/model/round4/regression-hashes.json").read_text()
    )
    for name, files in expected_regression.items():
        for filename, expected in files.items():
            assert (
                hashlib.sha256(
                    (evaluation_root / "data" / name / filename).read_bytes()
                ).hexdigest()
                == expected
            ), "fixed regression input differs"
    regression = [
        video_metrics(detector, evaluation_root / "data" / name)
        for name in [
            "linescan_roll",
            "demo_basic_roll",
            "demo_mixed_roll",
            "demo_challenge_roll",
        ]
    ]
    protocol = json.loads((code / "docs/model/round4/run.json").read_text())
    reasons = rendered_pilot_reasons(
        regression, chosen["metrics"], best_mode["metrics"], protocol["pilot_gate"]
    )
    (OUT / "renderer_pilot.json").write_text(
        json.dumps(
            {
                "regression": {"rolls": regression, "metrics": aggregate(regression)},
                "validation": best_mode,
                "native_validation": chosen["metrics"],
                "pilot_gate_passed": not reasons,
                "reasons": reasons,
                "final_test_evaluated": False,
            },
            indent=2,
        )
    )
    (OUT / "selection.json").write_text(
        json.dumps({"pilot": winner, "selected": chosen}, indent=2)
    )
    (OUT / "final_test.json").write_text(
        json.dumps(
            {"phase": "not_opened", "reason": "pilot only; final test reserved"},
            indent=2,
        )
    )
    (OUT / "status.json").write_text(
        json.dumps(
            {
                "phase": "renderer_pilot_evaluated",
                "pilot_gate_passed": not reasons,
                "reasons": reasons,
                "sha256": hashlib.sha256(
                    (candidate / "threadeye_s.onnx").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
    )
    shutil.rmtree(work)
    shutil.rmtree(YOLOX)
    shutil.rmtree(OUT / "video_inputs")
    print("RENDERER_PILOT_EVALUATED", not reasons, reasons, flush=True)
    sys.exit(0)
if (
    best_mode["metrics"]["precision"] >= 0.85
    and best_mode["metrics"]["recall"] >= 0.85
    and best_mode["metrics"]["broken_right_recall"] >= 0.8
):
    detector = TorchDetector(cfg, model)
    final_rows = [video_metrics(detector, p) for p in sorted(video_root.glob("test_*"))]
    (OUT / "final_test.json").write_text(
        json.dumps(
            {
                "config_frozen_before_test": cfg,
                "metrics": aggregate(final_rows),
                "rolls": final_rows,
            },
            indent=2,
        )
    )
else:
    (OUT / "final_test.json").write_text(
        json.dumps(
            {
                "phase": "not_opened",
                "reason": "validation video gate failed; fresh test reserved",
            }
        )
    )
# Advisory comparison on the unchanged original test tiles. It is never used to choose a
# checkpoint, threshold or inference mode and does not override the line-scan release gates.
if (DEADLINE - datetime.now(UTC)).total_seconds() > 300:
    packed_paths = find("PACKED")
    if packed_paths:
        packed = packed_paths[0].parent
        original = json.loads((packed / "test/annotations.json").read_text())
        original_names = {im["id"]: im["file_name"] for im in original["images"]}
        original_truths = [
            Truth(
                original_names[a["image_id"]],
                classes[a["category_id"] - 1],
                (
                    a["bbox"][0],
                    a["bbox"][1],
                    a["bbox"][0] + a["bbox"][2],
                    a["bbox"][1] + a["bbox"][3],
                ),
            )
            for a in original["annotations"]
        ]
        global_dir = Path("/kaggle/working/global_test")
        global_dir.mkdir()
        run(
            [
                "tar",
                "-xf",
                str(packed / "test.tar"),
                "-C",
                str(global_dir),
                "--no-same-owner",
            ]
        )
        # Frozen pack tar members can live under a split directory; keep original names.
        for name in original_names.values():
            if not (global_dir / name).is_file():
                matches = list(global_dir.rglob(Path(name).name))
                assert len(matches) == 1, "ambiguous global test image"
                shutil.move(matches[0], global_dir / name)
        model.head.decode_in_inference = True
        test_dets = []
        names = list(original_names.values())
        with torch.no_grad():
            for i in range(0, len(names), 16):
                batch_names = names[i : i + 16]
                xs = []
                ratios = []
                for name in batch_names:
                    image = cv2.imread(str(global_dir / name))
                    xs.append(tf(image, None, (640, 640))[0])
                    ratios.append(min(640 / image.shape[0], 640 / image.shape[1]))
                values = postprocess(
                    model(torch.from_numpy(np.stack(xs)).cuda().half()),
                    len(classes),
                    0.01,
                    0.45,
                )
                for name, ratio, p in zip(batch_names, ratios, values, strict=True):
                    if p is None:
                        continue
                    for x0, y0, x1, y1, obj, cs, c in p.float().cpu().numpy().tolist():
                        test_dets.append(
                            Det(
                                name,
                                classes[int(c)],
                                obj * cs,
                                (x0 / ratio, y0 / ratio, x1 / ratio, y1 / ratio),
                            )
                        )
        global_report = report(
            test_dets,
            original_truths,
            card["thresholds"],
            set(DEFECT_CLASSES),
            lambda n: n.split("__")[0],
            names,
        )
        global_report["thresholds_from"] = (
            "new native line-scan validation; original test unchanged and advisory"
        )
        (candidate / "test_report.json").write_text(json.dumps(global_report, indent=2))
        model.head.decode_in_inference = False
        shutil.rmtree(global_dir)
(OUT / "selection.json").write_text(
    json.dumps({"pilot": winner, "selected": chosen}, indent=2)
)
(OUT / "status.json").write_text(
    json.dumps(
        {
            "phase": "candidate_ready_not_deployed",
            "elapsed_seconds": time.monotonic() - START,
            "sha256": hashlib.sha256(
                (candidate / "threadeye_s.onnx").read_bytes()
            ).hexdigest(),
        },
        indent=2,
    )
)
print("CANDIDATE_READY_NOT_DEPLOYED", flush=True)
if os.environ.get("THREADEYE_TRAIN_MODE") == "rendered_final":
    shutil.rmtree(work)
    shutil.rmtree(YOLOX)
    shutil.rmtree(OUT / "video_inputs")
