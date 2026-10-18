"""Time the trained detector on this computer's CPU, the way the app runs it, and optionally make an int8 copy.

    backend/.venv/bin/python ml/scripts/bench_model.py MODEL_DIR            # fp32 timing on sample-roll frames
    backend/.venv/bin/python ml/scripts/bench_model.py MODEL_DIR --int8     # + int8 copy, timing and agreement

MODEL_DIR holds threadeye_<size>.onnx and model_info.json (the Kaggle training output). Frames are the ones the
app samples from data/sample_roll (threadeye.core.sampling.plan): the full 1920 x 1008 camera view, cut into the
same 8 tiles LocalModelDetector uses. The int8 copy (static QDQ quantisation, calibrated on tiles of other
sample-roll frames) is written next to the model as threadeye_<size>_int8.onnx; agreement says how many fp32
detections the int8 model also finds (same class, IoU >= 0.5).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from threadeye.core.sampling import plan  # noqa: E402
from threadeye.providers.local_model import LocalModelDetector, letterbox, tile_positions  # noqa: E402
from threadeye.providers.registry import create_provider  # noqa: E402
from threadeye.sources.simulated_roll import TrackFrameSource  # noqa: E402

ROLL = ROOT / "data/sample_roll"


def sampled_frames(n: int) -> list[np.ndarray]:
    src = TrackFrameSource(ROLL)
    info = src.open()
    wanted = [s.frame for s in plan(src.track(), info.calibration.view_height_px).samples]
    x, y, w, h = info.calibration.view_region
    cap = cv2.VideoCapture(str(ROLL / "roll_video.mp4"))
    frames = []
    for f in wanted[:n]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, img = cap.read()
        if ok:
            frames.append(img[y : y + h, x : x + w])
    return frames


def detector(model: Path, threads: int) -> LocalModelDetector:
    info = model.with_name("model_info.json")
    det = create_provider("local_model", {"model_path": str(model), "info_path": str(info), "threads": threads})
    det.prepare(None)  # type: ignore[arg-type]
    assert isinstance(det, LocalModelDetector)
    return det


def bench(model: Path, frames: list[np.ndarray], threads: int) -> tuple[float, list[list[tuple]]]:
    det = detector(model, threads)
    det.detect_array(frames[0])  # warm-up
    times, found = [], []
    for img in frames:
        t0 = time.perf_counter()
        found.append(det.detect_array(img))
        times.append(time.perf_counter() - t0)
    return statistics.median(times), found


def iou(a: tuple, b: tuple) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def quantize(model: Path, calib: list[np.ndarray]) -> Path:
    from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
    from onnxruntime.quantization.shape_inference import quant_pre_process

    tiles = []
    for img in calib:
        h, w = img.shape[:2]
        for y0 in tile_positions(h, 640, 0.2):
            for x0 in tile_positions(w, 640, 0.2):
                tiles.append(letterbox(img[y0 : y0 + 640, x0 : x0 + 640], (640, 640))[0][None])

    class Reader(CalibrationDataReader):
        def __init__(self) -> None:
            self.it = iter(tiles)

        def get_next(self) -> dict | None:
            t = next(self.it, None)
            return None if t is None else {"images": t}

    pre = model.with_name(model.stem + "_pre.onnx")
    quant_pre_process(str(model), str(pre))
    out = model.with_name(model.stem + "_int8.onnx")
    quantize_static(str(pre), str(out), Reader(), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)
    pre.unlink()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_dir", type=Path)
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--threads", type=int, nargs="*", default=[0, 4])
    ap.add_argument("--int8", action="store_true")
    args = ap.parse_args()
    model = next(args.model_dir.glob("threadeye_*.onnx"))
    frames = sampled_frames(args.frames + 6)
    test, calib = frames[: args.frames], frames[args.frames :]
    print(f"{model.name}: {model.stat().st_size / 1e6:.0f} MB, {len(test)} sampled frames of 1920x1008 (8 tiles each)")
    ref = None
    for th in args.threads:
        t, found = bench(model, test, th)
        ref = ref or found
        print(f"  fp32 threads={th or 'auto'}: {t * 1000:.0f} ms per frame, {sum(map(len, found))} detections")
    if args.int8:
        q = quantize(model, calib)
        print(f"{q.name}: {q.stat().st_size / 1e6:.0f} MB")
        for th in args.threads:
            t, found = bench(q, test, th)
            print(f"  int8 threads={th or 'auto'}: {t * 1000:.0f} ms per frame, {sum(map(len, found))} detections")
        hit = total = 0
        for fr, fq in zip(ref, found, strict=True):
            for box, cls, _ in fr:
                total += 1
                hit += any(c == cls and iou(box, b) >= 0.5 for b, c, _ in fq)
        print(f"  agreement: int8 finds {hit} of {total} fp32 detections")


if __name__ == "__main__":
    main()
