"""LocalModelDetector: the ThreadEye detector trained on Kaggle (YOLOX, ``ml/kaggle/train.py``), run with ONNX
Runtime on the CPU.

Config (``threadeye.providers.registry.create_provider("local_model", config)``):
  model_path       the exported ``threadeye_<size>.onnx`` (required)
  info_path        its ``model_info.json`` (classes, input size, training data); default: next to the model
  sha256           optional: refuse a model file whose SHA-256 differs (the file pinned on the model version)
  score_threshold  one threshold for every class; default: the per-class thresholds chosen on the val split
                   (model_info.json "thresholds", ml/fabricdata/operating.py), else 0.30
  nms_iou  0.45;  overlap  0.2 (tile overlap, as in training);  threads  0 (= ORT default)
  infer_scale      1.0: model pixels per view pixel (a scaled capture is resized to this first)

A frame is the camera view (``FrameImage``; a browser capture may be scaled). It is cut into model-size tiles
with overlap exactly like the training tiles (``ml/fabricdata/tiles.py``), so defects keep the pixel size the
model learned. Each tile is prepared as YOLOX's ValTransform does (BGR, resized by min(input / side), padded
with 114 at the bottom right, no normalisation). The export has no decoding in the graph (YOLOX's default),
so the raw head output is decoded here, boxes are mapped back to view pixels and merged with per-class NMS.

Scores are not calibrated: ``confidence`` stays None and the score is shown in the explanation and attributes.
Needs the ``onnx`` extra (onnxruntime, numpy, OpenCV); imports are lazy so the cloud bundle can list the provider.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from threadeye.core.frames import FramePacket, SourceInfo
from threadeye.core.providers import (
    BBox,
    Detection,
    DetectionResult,
    DetectorProvider,
    ProviderContext,
    ProviderInfo,
    ProviderNotConfigured,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

    Array = NDArray[Any]

PAD_VALUE = 114
STRIDES = (8, 16, 32)


def tile_positions(length: int, size: int, overlap: float) -> list[int]:
    """Start offsets of tiles along one side (same rule as ml/fabricdata/tiles.py ``positions``)."""
    if length <= size:
        return [0]
    step = size * (1 - overlap)
    n = math.ceil((length - size) / step) + 1
    stride = (length - size) / (n - 1)
    return [round(i * stride) for i in range(n)]


def letterbox(tile: Array, size: tuple[int, int]) -> tuple[Array, float]:
    """YOLOX ValTransform: resize by min(h_in / h, w_in / w), pad 114 bottom-right, HWC → CHW float32."""
    import cv2
    import numpy as np

    h_in, w_in = size
    r = min(h_in / tile.shape[0], w_in / tile.shape[1])
    resized = cv2.resize(tile, (int(tile.shape[1] * r), int(tile.shape[0] * r)), interpolation=cv2.INTER_LINEAR).astype(
        np.uint8
    )
    out = np.full((h_in, w_in, 3), PAD_VALUE, dtype=np.uint8)
    out[: resized.shape[0], : resized.shape[1]] = resized
    return np.ascontiguousarray(out.transpose(2, 0, 1), dtype=np.float32), r


def decode(raw: Array, size: tuple[int, int]) -> Array:
    """Raw YOLOX head output (N, A, 5 + C) → boxes in input pixels: cx, cy, w, h, obj, cls scores."""
    import numpy as np

    grids, strides = [], []
    for s in STRIDES:
        hs, ws = size[0] // s, size[1] // s
        xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
        grids.append(np.stack((xv, yv), 2).reshape(1, -1, 2))
        strides.append(np.full((1, hs * ws, 1), s))
    grid = np.concatenate(grids, 1).astype(np.float32)
    stride = np.concatenate(strides, 1).astype(np.float32)
    out = raw.copy()
    out[..., :2] = (out[..., :2] + grid) * stride
    out[..., 2:4] = np.exp(out[..., 2:4]) * stride
    return out


def nms(boxes: Array, scores: Array, iou: float) -> list[int]:
    """Greedy NMS on x0, y0, x1, y1 boxes; returns kept indices, best score first."""
    import numpy as np

    order = np.argsort(-scores)
    keep: list[int] = []
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        xx0 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy0 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx1 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy1 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx1 - xx0, 0, None) * np.clip(yy1 - yy0, 0, None)
        overlap = inter / np.maximum(area[i] + area[rest] - inter, 1e-9)
        order = rest[overlap <= iou]
    return keep


class LocalModelDetector(DetectorProvider):
    def __init__(self, config: Mapping[str, Any], ctx: ProviderContext) -> None:
        super().__init__(config, ctx)
        self._session: Any = None
        self._input_name = ""
        self._model_sha = ""
        self.classes: tuple[str, ...] = ()
        self.input_size: tuple[int, int] = (640, 640)
        self.score_threshold = float(self.config.get("score_threshold", 0.30))
        self.class_thresholds: dict[str, float] = {}
        self.nms_iou = float(self.config.get("nms_iou", 0.45))
        self.overlap = float(self.config.get("overlap", 0.2))
        self.infer_scale = float(self.config.get("infer_scale", 1.0))
        self._load_info()

    # ------------------------------------------------------------------------------------ model files
    def _model_path(self) -> Path:
        if not self.config.get("model_path"):
            raise ProviderNotConfigured("LocalModelDetector: no model installed (config model_path)")
        return Path(self.config["model_path"])

    def _load_info(self) -> None:
        if not self.config.get("model_path"):
            return
        info_path = Path(self.config.get("info_path") or self._model_path().with_name("model_info.json"))
        if not info_path.exists():
            raise ProviderNotConfigured(f"LocalModelDetector: {info_path} missing (classes and input size)")
        info = json.loads(info_path.read_text())
        self.classes = tuple(info["classes"])
        self.input_size = (int(info["input"][0]), int(info["input"][1]))
        self._version = str(info.get("version") or f"yolox-{info.get('size', '?')}")
        if "score_threshold" not in self.config:
            self.class_thresholds = {str(k): float(v) for k, v in (info.get("thresholds") or {}).items()}
        if "infer_scale" not in self.config and info.get("infer_scale"):
            # The scale the model was trained to look at (e.g. 2: AITEX-size defects enlarged): a model card
            # says it, so installing the model cannot leave it running at the wrong scale.
            self.infer_scale = float(info["infer_scale"])

    @property
    def info(self) -> ProviderInfo:
        model = self.config.get("model_path")
        return ProviderInfo(
            provider_id="local_model",
            version=getattr(self, "_version", "0.0.0") if model else "0.0.0",
            display_name="ThreadEye local model (YOLOX, ONNX on CPU)"
            if model
            else "ThreadEye local model (no model installed)",
            kind="local_model",
            is_simulated=False,
            requires_image=True,
            calibrated_confidence=False,
            bbox_quality="precise",
            classes=self.classes,
            config_hash=hashlib.sha256(
                json.dumps(
                    {
                        "model_sha256": self._model_sha or self.config.get("sha256"),
                        "score_threshold": self.score_threshold,
                        "class_thresholds": self.class_thresholds,
                        "nms_iou": self.nms_iou,
                        "overlap": self.overlap,
                        "infer_scale": self.infer_scale,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:16],
        )

    def prepare(self, source: SourceInfo) -> None:
        if self._session is not None:
            return
        path = self._model_path()
        if not path.exists():
            raise ProviderNotConfigured(f"LocalModelDetector: model file {path} not found")
        try:
            import onnxruntime as ort
        except ImportError as exc:  # the cloud bundle has no onnxruntime
            raise ProviderNotConfigured("LocalModelDetector needs the onnx extra (onnxruntime)") from exc
        data = path.read_bytes()
        self._model_sha = hashlib.sha256(data).hexdigest()
        want = self.config.get("sha256")
        if want and want != self._model_sha:
            raise ProviderNotConfigured(
                f"LocalModelDetector: {path.name} SHA-256 {self._model_sha[:12]}… != {want[:12]}…"
            )
        opts = ort.SessionOptions()
        if int(self.config.get("threads", 0)):
            opts.intra_op_num_threads = int(self.config["threads"])
        self._session = ort.InferenceSession(data, sess_options=opts, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def close(self) -> None:
        self._session = None

    # ------------------------------------------------------------------------------------ inference
    def run(self, batch: Array) -> Array:
        """One forward pass: (B, 3, H, W) → raw head output (B, A, 5 + C). Tests replace this."""
        if self._session is None:
            raise ProviderNotConfigured("LocalModelDetector: prepare() was not called")
        out: Array = self._session.run(None, {self._input_name: batch})[0]
        return out

    def detect_array(self, image: Array) -> list[tuple[BBox, str, float]]:
        """Detections (box in image pixels, class, score) for one BGR view image."""
        import numpy as np

        size = self.input_size
        h, w = image.shape[:2]
        tiles, offsets, ratios = [], [], []
        for y0 in tile_positions(h, size[0], self.overlap):
            for x0 in tile_positions(w, size[1], self.overlap):
                chw, r = letterbox(image[y0 : y0 + size[0], x0 : x0 + size[1]], size)
                tiles.append(chw)
                offsets.append((x0, y0))
                ratios.append(r)
        raw = self.run(np.stack(tiles))
        preds = decode(raw, size)
        thr = np.array([self.class_thresholds.get(c, self.score_threshold) for c in self.classes], np.float32)
        all_boxes, all_scores, all_cls = [], [], []
        for p, (x0, y0), r in zip(preds, offsets, ratios, strict=True):
            cls_scores = p[:, 5:]
            cls = cls_scores.argmax(1)
            score = p[:, 4] * cls_scores[np.arange(len(cls)), cls]
            ok = score >= thr[cls]
            if not ok.any():
                continue
            cx, cy, bw, bh = (p[ok, i] for i in range(4))
            boxes = np.stack((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), 1) / r
            boxes[:, [0, 2]] += x0
            boxes[:, [1, 3]] += y0
            all_boxes.append(boxes)
            all_scores.append(score[ok])
            all_cls.append(cls[ok])
        if not all_boxes:
            return []
        boxes = np.concatenate(all_boxes)
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
        scores = np.concatenate(all_scores)
        classes = np.concatenate(all_cls)
        out: list[tuple[BBox, str, float]] = []
        for c in np.unique(classes):
            idx = np.nonzero(classes == c)[0]
            for k in nms(boxes[idx], scores[idx], self.nms_iou):
                b = boxes[idx[k]]
                if b[2] - b[0] >= 1 and b[3] - b[1] >= 1:
                    box = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                    out.append((box, self.classes[int(c)], float(scores[idx[k]])))
        return sorted(out, key=lambda d: -d[2])

    def detect(self, frame: FramePacket) -> DetectionResult:
        t0 = time.perf_counter()
        self._model_path()  # no model installed: refuse to run (never an empty "no defects" result)
        if frame.image is None:
            return self._result(frame, [], t0, "LocalModelDetector needs the frame image")
        import cv2
        import numpy as np

        image = cv2.imdecode(np.frombuffer(frame.image.jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return self._result(frame, [], t0, "frame image could not be decoded")
        # Run at infer_scale × view pixels whatever the capture size, so defects have the pixel size the model
        # was tuned on (a 960-px browser capture of a 1920-px view is scaled back up).
        target = self.infer_scale / (frame.image.scale or 1.0)
        if abs(target - 1.0) > 1e-3:
            image = cv2.resize(image, (round(image.shape[1] * target), round(image.shape[0] * target)))
        found = self.detect_array(image)
        detections = [
            Detection(
                bbox_px=_unscale(box, self.infer_scale),
                cls=cls,
                confidence=None,
                explanation=f"ThreadEye model: {cls} (score {score:.2f}, not calibrated)",
                attributes={"score": round(score, 4)},
            )
            for box, cls, score in found
        ]
        return self._result(frame, detections, t0)

    def _result(
        self, frame: FramePacket, dets: Sequence[Detection], t0: float, error: str | None = None
    ) -> DetectionResult:
        return DetectionResult(frame.pos.frame, list(dets), (time.perf_counter() - t0) * 1000, self.info, error)


def _unscale(box: BBox, scale: float) -> BBox:
    """Pixels of the image the model ran on → view pixels."""
    return (box[0] / scale, box[1] / scale, box[2] / scale, box[3] / scale)
