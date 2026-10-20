"""Kaggle (CPU): draw the trained model's boxes next to the truth on test tiles of chosen sources.

Inputs: the build notebook's output (threadeye_v1) and a training notebook's output (threadeye_s.onnx +
model_info.json). Writes /kaggle/working/inspect_<source>.jpg contact sheets (green: truth, red: model
at its per-class threshold, with class and score) and inspect_stats.json (truth box sizes, hits, misses,
false alarms per source and class), to see why a source is weak.
"""

import json
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "-q", "install", "onnxruntime"], check=False)
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

DATA = next(Path("/kaggle/input").rglob("threadeye_v1/summary.json")).parent
MODEL = next(Path("/kaggle/input").rglob("threadeye_s.onnx"))
INFO = json.loads(MODEL.with_name("model_info.json").read_text())
CLASSES, THR = INFO["classes"], INFO.get("thresholds") or {}
SOURCES = ["aitex", "fabricspotdefect", "wfdd", "moratuwa", "tianchi"]
PER_SOURCE = 16
OUT = Path("/kaggle/working")
sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])


def predict(img: np.ndarray) -> list[tuple[list[float], str, float]]:
    h, w = img.shape[:2]
    r = min(640 / h, 640 / w)
    pad = np.full((640, 640, 3), 114, np.uint8)
    pad[: int(h * r), : int(w * r)] = cv2.resize(img, (int(w * r), int(h * r)))
    raw = sess.run(None, {"images": pad.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    grids, strides = [], []
    for s in (8, 16, 32):
        xv, yv = np.meshgrid(np.arange(640 // s), np.arange(640 // s))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((len(grids[-1]), 1), s))
    g, st = np.concatenate(grids), np.concatenate(strides)
    xy = (raw[:, :2] + g) * st
    wh = np.exp(raw[:, 2:4]) * st
    cls = raw[:, 5:].argmax(1)
    score = raw[:, 4] * raw[np.arange(len(cls)), 5 + cls]
    out = []
    for c in np.unique(cls):
        name = CLASSES[c]
        idx = np.nonzero((cls == c) & (score >= THR.get(name, 0.3)))[0]
        if not len(idx):
            continue
        boxes = [[float(xy[i, 0] - wh[i, 0] / 2), float(xy[i, 1] - wh[i, 1] / 2), float(wh[i, 0]), float(wh[i, 1])] for i in idx]
        keep = cv2.dnn.NMSBoxes(boxes, [float(score[i]) for i in idx], 0.0, 0.45)
        for k in np.array(keep).reshape(-1):
            x, y, bw, bh = (v / r for v in boxes[k])
            out.append(([x, y, x + bw, y + bh], name, float(score[idx[k]])))
    return out


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


coco = json.loads((DATA / "test/annotations.json").read_text())
cname = {c["id"]: c["name"] for c in coco["categories"]}
anns = defaultdict(list)
for a in coco["annotations"]:
    x, y, w, h = a["bbox"]
    anns[a["image_id"]].append(([x, y, x + w, y + h], cname[a["category_id"]]))
stats = {}
for src in SOURCES:
    ims = sorted((im for im in coco["images"] if im["file_name"].startswith(src + "__") and anns.get(im["id"])),
                 key=lambda im: zlib.crc32(im["file_name"].encode()))
    sizes, hit, miss, fa = [], Counter(), Counter(), Counter()
    cells = []
    for im in ims[:200]:
        img = cv2.imread(str(DATA / "test/images" / im["file_name"]))
        preds = predict(img)
        truth = anns[im["id"]]
        for box, c in truth:
            sizes.append((box[2] - box[0], box[3] - box[1]))
            found = any(iou(box, p) >= 0.3 or (box[0] <= (p[0] + p[2]) / 2 <= box[2] and box[1] <= (p[1] + p[3]) / 2 <= box[3]) for p, _, _ in preds)
            (hit if found else miss)[c] += 1
        for p, c, s in preds:
            if not any(iou(p, b) >= 0.3 or (b[0] <= (p[0] + p[2]) / 2 <= b[2] and b[1] <= (p[1] + p[3]) / 2 <= b[3]) for b, _ in truth):
                fa[c] += 1
        if len(cells) < PER_SOURCE:
            vis = img.copy()
            for box, c in truth:
                cv2.rectangle(vis, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 200, 0), 2)
                cv2.putText(vis, c, (int(box[0]), max(12, int(box[1]) - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 0), 1)
            for p, c, s in preds:
                cv2.rectangle(vis, (int(p[0]), int(p[1])), (int(p[2]), int(p[3])), (0, 0, 255), 2)
                cv2.putText(vis, f"{c} {s:.2f}", (int(p[0]), min(vis.shape[0] - 4, int(p[3]) + 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
            s = 400 / max(vis.shape[:2])
            vis = cv2.resize(vis, (int(vis.shape[1] * s), int(vis.shape[0] * s)))
            cell = np.full((400, 400, 3), 40, np.uint8)
            cell[: vis.shape[0], : vis.shape[1]] = vis
            cells.append(cell)
    if cells:
        while len(cells) % 4:
            cells.append(np.full((400, 400, 3), 40, np.uint8))
        sheet = np.vstack([np.hstack(cells[i:i + 4]) for i in range(0, len(cells), 4)])
        cv2.imwrite(str(OUT / f"inspect_{src}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    wh = np.array(sizes) if sizes else np.zeros((0, 2))
    stats[src] = {
        "tiles_checked": min(len(ims), 200),
        "truth_box_px_median_wh": np.median(wh, 0).round(1).tolist() if len(wh) else [],
        "truth_boxes_under_16px": int((wh.min(1) < 16).sum()) if len(wh) else 0,
        "found": dict(hit), "missed": dict(miss), "false_alarms": dict(fa),
    }
    print(src, json.dumps(stats[src]), flush=True)
(OUT / "inspect_stats.json").write_text(json.dumps(stats, indent=1))
