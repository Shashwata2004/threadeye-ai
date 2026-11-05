"""Trace real predictions for missed line-scan defects. Offline, no DB access or training.

The hook observes decoded anchors before thresholds. Only candidates overlapping visible truth
regions are retained. Truths never enter inference. Cached actual detections are replayed through
the production mapper/filter/deduper with production sampling and every-frame sampling separately.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np
from threadeye.core.evaluation import _matches
from threadeye.core.frames import FramePacket
from threadeye.core.geometry import roll_to_view
from threadeye.core.providers import (
    Detection,
    DetectionResult,
    DetectorProvider,
    ProviderContext,
)
from threadeye.core.runner import RollSpec, Runner
from threadeye.core.sampling import Sample, plan
from threadeye.core.scoring.profile import simulator_parity_profile
from threadeye.datasets.answer_key import load_answer_key
from threadeye.providers.local_model import PACK_GAP, LocalModelDetector
from threadeye.services.benchmark import truth_from_key
from threadeye.sources.simulated_roll import TrackFrameSource, VideoFileSource

MODES = {
    f"{layout}-{scale}x": {
        "whole_strip": layout == "whole",
        "pack": layout == "packed",
        "infer_scale": scale,
    }
    for layout in ("whole", "tiles", "packed")
    for scale in (1, 2)
}
ROLLS = ("linescan_roll", "demo_mixed_roll", "demo_challenge_roll")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlaps(
    boxes: np.ndarray, truth: tuple, *, minimum_iou: float = 0.1
) -> np.ndarray:
    """A visible thin defect: IoU >= .1 or prediction centre inside its 2 px halo.

    Diagnostic association only; release scoring keeps its own frozen matching rules.
    """
    lo = np.maximum(boxes[:, :2], truth[:2])
    hi = np.minimum(boxes[:, 2:], truth[2:])
    inter = np.maximum(hi - lo, 0).prod(1)
    area = np.maximum(boxes[:, 2:] - boxes[:, :2], 0).prod(1)
    ta = max(0, truth[2] - truth[0]) * max(0, truth[3] - truth[1])
    iou = inter / np.maximum(area + ta - inter, 1e-8)
    centres = (boxes[:, :2] + boxes[:, 2:]) / 2
    inside = (
        (centres >= np.array(truth[:2]) - 2) & (centres <= np.array(truth[2:]) + 2)
    ).all(1)
    return (iou >= minimum_iou) | inside


def project(
    decoded: np.ndarray, layout: list, ratio: float, ph: int, scale: float
) -> tuple:
    centres = decoded[:, :2]
    boxes = (
        np.concatenate(
            (centres - decoded[:, 2:4] / 2, centres + decoded[:, 2:4] / 2), 1
        )
        / ratio
    )
    if len(layout) == 1:
        keep = np.ones(len(boxes), bool)
        slots = np.zeros(len(boxes), int)
    else:
        slots = (decoded[:, 1] // (ph + PACK_GAP)).astype(int)
        keep = (
            (slots >= 0)
            & (slots < len(layout))
            & (decoded[:, 1] - slots * (ph + PACK_GAP) < ph)
        )
        boxes = boxes[keep]
        slots = slots[keep]
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - (slots * (ph + PACK_GAP))[:, None]).clip(
            0, ph
        )
    offsets = np.array(layout)[slots]
    boxes[:, [0, 2]] += offsets[:, :1]
    boxes[:, [1, 3]] += offsets[:, 1:]
    return boxes / scale, decoded[keep]


class Replay(DetectorProvider):
    def __init__(self, detector: LocalModelDetector, captures: dict):
        super().__init__({}, ProviderContext())
        self.detector = detector
        self.captures = captures

    @property
    def info(self):
        return dataclasses.replace(self.detector.info, requires_image=False)

    def prepare(self, source):
        pass

    def detect(self, frame: FramePacket):
        dets = [
            Detection(
                tuple(d["box"]),
                d["class"],
                None,
                "offline actual prediction",
                {"score": d["score"]},
            )
            for d in self.captures.get(frame.pos.frame, [])
        ]
        return DetectionResult(
            frame=frame.pos.frame, detections=dets, provider=self.info, latency_ms=0
        )


def replay(detector, roll, captures, truths, *, every_frame):
    source = TrackFrameSource(roll)
    meta = source.parsed.meta
    runner = Runner(
        source,
        Replay(detector, captures),
        simulator_parity_profile(),
        RollSpec(meta.fabric_width_in, meta.roll_length_yd),
        inspection_id="offline-diagnosis",
    )
    if every_frame:
        runner._sample_frames = {
            p.frame: Sample(p.frame, p.roll_y_top_px, "travel") for p in runner.track
        }
    runner.run_to_end()
    result = {}
    for truth in truths:
        matched = []
        for t in runner.deduper.tracks:
            if _matches(t.box, truth.box, 0.3, 3.0) is None:
                continue
            view = runner.defect_view(t)
            matched.append(
                {
                    "number": t.defect_no,
                    "class": view["current_cls"],
                    "kind": view["kind"],
                    "filter": view["nondefect_category"],
                    "box": dataclasses.asdict(t.box),
                    "correct_class": view["current_cls"] == truth.cls,
                }
            )
        result[truth.defect_id] = matched
    return result


def analyse(detector, roll, captures, truths, records):
    production = replay(detector, roll, captures, truths, every_frame=False)
    full = replay(detector, roll, captures, truths, every_frame=True)
    findings = []
    for truth in truths:
        tid = truth.defect_id
        raw = [r for f in records for r in f["raw"].get(tid, [])]
        threshold = detector.class_thresholds.get(truth.cls, detector.score_threshold)
        p = production[tid]
        a = full[tid]
        correct = lambda rows: any(
            r["correct_class"] and r["kind"] == "defect" for r in rows
        )
        good_raw = [r for r in raw if r["argmax_class"] == truth.cls]
        best = max((r["broken_score"] for r in good_raw), default=0)
        after = [
            d
            for f in records
            if tid in f["truth_boxes"]
            for d in f["after_threshold_nms"]
            if d["class"] == truth.cls
            and overlaps(np.array([d["box"]]), f["truth_boxes"][tid])[0]
        ]
        if correct(p):
            cause = "detected"
        elif correct(a):
            cause = "sampling"
        elif any(r["correct_class"] and r["kind"] != "defect" for r in a):
            cause = "nondefect_filter"
        elif after:
            cause = "tracking_or_geometry"
        elif best >= threshold:
            cause = "nms_or_projection"
        elif best >= 0.01:
            cause = "threshold"
        elif any(r["score"] >= 0.05 and r["argmax_class"] != truth.cls for r in raw):
            cause = "wrong_class"
        else:
            cause = "no_usable_prediction"
        findings.append(
            {
                "id": tid,
                "class": truth.cls,
                "yard": truth.box.center_yd,
                "cause": cause,
                "threshold": threshold,
                "best_broken_argmax_score": best,
                "best_any_broken_score": max(
                    (r["broken_score"] for r in raw), default=0
                ),
                "production_tracks": p,
                "every_frame_tracks": a,
            }
        )
    return findings


def diagnose(model: Path, roll: Path, mode: str, out: Path, deadline: datetime):
    source = VideoFileSource(roll)
    meta = source.parsed.meta
    key = load_answer_key(roll, require_media=True)
    truths = [
        t for t in truth_from_key(key, meta.px_per_cm)[0] if t.cls == "broken_yarn"
    ]
    track = source.track()
    samples = {s.frame for s in plan(track, meta.view_region.h).samples}
    regions = {}
    for pos in track:
        visible = {}
        for t in truths:
            x0, y0, x1, y1 = roll_to_view(t.box, pos, source.calibration)
            if min(y1, meta.view_region.h) - max(y0, 0) >= 0.1 * (y1 - y0):
                visible[t.defect_id] = (x0, max(y0, 0), x1, min(y1, meta.view_region.h))
        if visible:
            regions[pos.frame] = visible
    detector = LocalModelDetector(
        {"model_path": str(model), "threads": 2, **MODES[mode]}, ProviderContext()
    )
    detector.prepare(source.open())
    records = []
    captures = {}
    current = {}
    scale = MODES[mode]["infer_scale"]
    truth_class = detector.classes.index("broken_yarn")

    def trace(preds, layouts, ratios, ph):
        for pred, layout, ratio in zip(preds, layouts, ratios, strict=True):
            boxes, decoded = project(pred, layout, ratio, ph, scale)
            for tid, box in current.items():
                selected = overlaps(boxes, box)
                if not selected.any():
                    continue
                scores = decoded[selected, 4:5] * decoded[selected, 5:]
                ds = decoded[selected]
                bs = boxes[selected]
                indices = set(
                    np.argsort(-scores[:, truth_class])[:3].tolist()
                    + np.argsort(-scores.max(1))[:3].tolist()
                )
                for i in indices:
                    c = int(scores[i].argmax())
                    raw_by_truth[tid].append(
                        {
                            "box": bs[i].round(3).tolist(),
                            "argmax_class": detector.classes[c],
                            "score": float(scores[i, c]),
                            "broken_score": float(scores[i, truth_class]),
                            "objectness": float(ds[i, 4]),
                            "class_scores": dict(
                                zip(
                                    detector.classes,
                                    scores[i].round(6).tolist(),
                                    strict=True,
                                )
                            ),
                        }
                    )

    detector.diagnostic_hook = trace
    try:
        for packet in source.read(0, None, lambda p: p.frame in regions):
            if datetime.now(UTC) >= deadline:
                raise TimeoutError("diagnostic budget exhausted")
            if packet.image is None:
                continue
            current = regions[packet.pos.frame]
            raw_by_truth = {tid: [] for tid in current}
            started = perf_counter()
            result = detector.detect(packet)
            elapsed = perf_counter() - started
            if result.error:
                raise RuntimeError(result.error)
            captures[packet.pos.frame] = [
                {"box": list(d.bbox_px), "class": d.cls, "score": d.attributes["score"]}
                for d in result.detections
            ]
            records.append(
                {
                    "frame": packet.pos.frame,
                    "production_sampled": packet.pos.frame in samples,
                    "seconds": elapsed,
                    "truth_boxes": current,
                    "raw": raw_by_truth,
                    "after_threshold_nms": captures[packet.pos.frame],
                }
            )
    finally:
        source.close()
    findings = analyse(detector, roll, captures, truths, records)
    detector.close()
    payload = {
        "model_sha256": digest(model),
        "card_sha256": digest(model.with_name("model_info.json")),
        "video_sha256": digest(roll / "roll_video.mp4"),
        "mode": mode,
        "findings": findings,
        "frames": records,
        "scope": "All frames where a broken-yarn truth is visible; actual predictions replayed through production filter/tracker. Other frames emit no predictions in this diagnostic replay.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(
        json.dumps(
            {
                "model": model.parent.name,
                "roll": roll.name,
                "mode": mode,
                "findings": [
                    (f["id"], f["cause"], round(f["best_broken_argmax_score"], 4))
                    for f in findings
                ],
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", action="append", required=True, help="label=ONNX path"
    )
    parser.add_argument("--modes", nargs="+", default=list(MODES), choices=list(MODES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--analyse-only",
        action="store_true",
        help="Recompute pipeline association from cached actual predictions",
    )
    parser.add_argument("--deadline", required=True, help="UTC ISO deadline")
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.deadline)
    for spec in args.model:
        label, path = spec.split("=", 1)
        model = Path(path)
        for name in ROLLS:
            for mode in args.modes:
                out = args.out / label / name / f"{mode}.json"
                if out.exists():
                    old = json.loads(out.read_text())
                    if args.analyse_only:
                        source = TrackFrameSource(ROOT / "data" / name)
                        truths = [
                            t
                            for t in truth_from_key(
                                load_answer_key(ROOT / "data" / name),
                                source.calibration.px_per_cm,
                            )[0]
                            if t.cls == "broken_yarn"
                        ]
                        detector = LocalModelDetector(
                            {"model_path": str(model), **MODES[mode]}, ProviderContext()
                        )
                        captures = {
                            f["frame"]: f["after_threshold_nms"] for f in old["frames"]
                        }
                        old["findings"] = analyse(
                            detector,
                            ROOT / "data" / name,
                            captures,
                            truths,
                            old["frames"],
                        )
                        old["analysis_version"] = 2
                        out.write_text(json.dumps(old, indent=2))
                        print(
                            label,
                            name,
                            mode,
                            [(f["id"], f["cause"]) for f in old["findings"]],
                            flush=True,
                        )
                        continue
                    if (
                        old["model_sha256"] == digest(model)
                        and old["card_sha256"]
                        == digest(model.with_name("model_info.json"))
                        and old["video_sha256"]
                        == digest(ROOT / "data" / name / "roll_video.mp4")
                    ):
                        continue
                if not args.analyse_only:
                    diagnose(model, ROOT / "data" / name, mode, out, deadline)


if __name__ == "__main__":
    main()
