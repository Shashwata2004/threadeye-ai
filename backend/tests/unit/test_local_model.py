"""LocalModelDetector without a real model: a fake forward pass returns YOLOX head outputs for known boxes."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from threadeye.core.frames import FrameImage, FramePacket, FramePosition  # noqa: E402
from threadeye.core.providers import ProviderNotConfigured  # noqa: E402
from threadeye.providers.local_model import LocalModelDetector, tile_positions  # noqa: E402
from threadeye.providers.registry import create_provider  # noqa: E402

CLASSES = ["hole", "stain", "broken_yarn"]
ANCHORS = 80 * 80 + 40 * 40 + 20 * 20


def encode(raw: Any, box: tuple[float, float, float, float], cls: int, score: float) -> None:
    """Write ``box`` (tile input pixels) into a stride-8 anchor of one tile's raw head output."""
    x0, y0, x1, y1 = box
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    gx, gy = int(cx // 8), int(cy // 8)
    a = gy * 80 + gx
    raw[a, 0], raw[a, 1] = cx / 8 - gx, cy / 8 - gy
    raw[a, 2], raw[a, 3] = math.log(w / 8), math.log(h / 8)
    raw[a, 4] = 1.0
    raw[a, 5 + cls] = score


class FakeModel(LocalModelDetector):
    """Answers per tile offset: {(x0, y0): [(box in tile px, cls, score), ...]}."""

    def __init__(self, tmp_path: Path, plan: dict[tuple[int, int], list[Any]], **cfg: Any) -> None:
        model = tmp_path / "threadeye_s.onnx"
        model.write_bytes(b"fake")
        (tmp_path / "model_info.json").write_text(json.dumps({"classes": CLASSES, "input": [640, 640], "size": "s"}))
        super().__init__({"model_path": str(model), **cfg}, ctx=None)  # type: ignore[arg-type]
        self.plan = plan
        self.offsets: list[tuple[int, int]] = []

    def run(self, batch: Any) -> Any:
        assert batch.shape[1:] == (3, 640, 640) and batch.dtype == np.float32
        out = np.zeros((len(batch), ANCHORS, 5 + len(CLASSES)), np.float32)
        for i, off in enumerate(self.offsets):
            for box, cls, score in self.plan.get(off, []):
                encode(out[i], box, cls, score)
        return out

    def detect_array(self, image: Any) -> Any:
        h, w = image.shape[:2]
        self.offsets = [
            (x, y) for y in tile_positions(h, 640, self.overlap) for x in tile_positions(w, 640, self.overlap)
        ]
        return super().detect_array(image)


def test_tiles_match_the_training_cut() -> None:
    assert tile_positions(1920, 640, 0.2) == [0, 427, 853, 1280]
    assert tile_positions(1008, 640, 0.2) == [0, 368]
    assert tile_positions(500, 640, 0.2) == [0]


def test_boxes_come_back_in_view_pixels_and_overlap_copies_merge(tmp_path: Path) -> None:
    plan = {
        # One stain seen by two overlapping tiles (view x 500..540): one detection after NMS.
        (0, 0): [((500, 100, 540, 140), 1, 0.9)],
        (427, 0): [((73, 100, 113, 140), 1, 0.8), ((273, 200, 313, 260), 0, 0.7)],
        # Below the threshold: dropped.
        (1280, 368): [((10, 10, 50, 50), 2, 0.1)],
    }
    det = FakeModel(tmp_path, plan)
    found = det.detect_array(np.zeros((1008, 1920, 3), np.uint8))
    assert [(c, round(s, 2)) for _, c, s in found] == [("stain", 0.9), ("hole", 0.7)]
    assert found[0][0] == pytest.approx((500, 100, 540, 140), abs=0.01)
    assert found[1][0] == pytest.approx((700, 200, 740, 260), abs=0.01)


def test_a_scaled_capture_is_mapped_back_to_view_pixels(tmp_path: Path) -> None:
    det = FakeModel(tmp_path, {(427, 0): [((273, 200, 313, 260), 0, 0.7)]})
    _, jpg = cv2.imencode(".jpg", np.zeros((504, 960, 3), np.uint8))
    pos = FramePosition(7, 0.2, 0.0, 0.0, 1.1, 18.0, "running", 200.0, False)
    result = det.detect(FramePacket(pos, FrameImage(jpg.tobytes(), 960, 504, scale=0.5)))
    assert result.error is None and result.frame == 7
    (d,) = result.detections
    assert d.cls == "hole" and d.confidence is None and d.attributes["score"] == pytest.approx(0.7)
    assert d.bbox_px == pytest.approx((700, 200, 740, 260), abs=0.5)
    assert "not calibrated" in d.explanation


def test_no_model_is_reported_not_hidden(tmp_path: Path) -> None:
    stub = create_provider("local_model")
    assert stub.info.classes == () and stub.info.version == "0.0.0"
    with pytest.raises(ProviderNotConfigured):
        stub.prepare(None)  # type: ignore[arg-type]
    with pytest.raises(ProviderNotConfigured, match=r"model_info\.json"):
        create_provider("local_model", {"model_path": str(tmp_path / "missing.onnx")})


def test_model_file_hash_is_checked(tmp_path: Path) -> None:
    pytest.importorskip("onnxruntime")
    det = FakeModel(tmp_path, {}, sha256="0" * 64)
    with pytest.raises(ProviderNotConfigured, match="SHA-256"):
        det.prepare(None)  # type: ignore[arg-type]
    assert det.info.classes == tuple(CLASSES)
