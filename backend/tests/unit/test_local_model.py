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

    def __init__(
        self,
        tmp_path: Path,
        plan: dict[tuple[int, int], list[Any]],
        thresholds: dict | None = None,
        card: dict | None = None,
        **cfg: Any,
    ) -> None:
        model = tmp_path / "threadeye_s.onnx"
        model.write_bytes(b"fake")
        info = {"classes": CLASSES, "input": [640, 640], "size": "s", "thresholds": thresholds or {}, **(card or {})}
        (tmp_path / "model_info.json").write_text(json.dumps(info))
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


def test_running_yarn_stitching_preserves_separate_and_unrelated_defects() -> None:
    from threadeye.providers.local_model import stitch_running_yarn

    found = stitch_running_yarn(
        [
            ((0, 10, 100, 20), "broken_yarn", 0.7),
            ((80, 11, 180, 21), "broken_yarn", 0.6),
            ((200, 10, 300, 20), "broken_yarn", 0.8),  # real gap: never bridge it
            ((0, 50, 100, 60), "broken_yarn", 0.9),  # a different line
            ((0, 10, 100, 20), "loose_thread", 0.9),
        ]
    )
    assert found[0] == ((0, 10, 180, 21), "broken_yarn", 0.7)
    assert len(found) == 4


def test_vertical_yarn_fragments_stitch_without_hallucinating_confidence() -> None:
    from threadeye.providers.local_model import stitch_running_yarn

    assert stitch_running_yarn([((20, 0, 25, 100), "missing_yarn", 0.5), ((21, 80, 26, 180), "missing_yarn", 0.8)]) == [
        ((20, 0, 26, 180), "missing_yarn", 0.8)
    ]


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


def test_per_class_thresholds_from_the_model_card(tmp_path: Path) -> None:
    plan = {(0, 0): [((100, 100, 140, 140), 0, 0.5), ((300, 300, 340, 340), 1, 0.5)]}
    det = FakeModel(tmp_path, plan, thresholds={"hole": 0.6, "stain": 0.4})
    assert [c for _, c, _ in det.detect_array(np.zeros((640, 640, 3), np.uint8))] == ["stain"]
    det = FakeModel(tmp_path, plan, thresholds={"hole": 0.6, "stain": 0.4}, score_threshold=0.45)
    assert sorted(c for _, c, _ in det.detect_array(np.zeros((640, 640, 3), np.uint8))) == ["hole", "stain"]


def test_the_model_card_sets_the_inference_scale(tmp_path: Path) -> None:
    det = FakeModel(tmp_path, {(0, 0): [((100, 100, 140, 140), 0, 0.7)]}, card={"infer_scale": 2})
    assert det.infer_scale == 2.0
    _, jpg = cv2.imencode(".jpg", np.zeros((320, 320, 3), np.uint8))
    pos = FramePosition(1, 0.2, 0.0, 0.0, 1.1, 18.0, "running", 200.0, False)
    (d,) = det.detect(FramePacket(pos, FrameImage(jpg.tobytes(), 320, 320, scale=1.0))).detections
    assert d.bbox_px == pytest.approx((50, 50, 70, 70), abs=0.5)  # model pixels / 2 = view pixels
    assert FakeModel(tmp_path, {}, card={"infer_scale": 2}, infer_scale=1.0).infer_scale == 1.0


class StripModel(LocalModelDetector):
    """A line-scan strip: answers one box (in input pixels) in the first input it gets."""

    def __init__(self, tmp_path: Path, box: tuple[float, float, float, float], any_size: bool) -> None:
        model = tmp_path / "threadeye_s.onnx"
        model.write_bytes(b"fake")
        (tmp_path / "model_info.json").write_text(json.dumps({"classes": CLASSES, "input": [640, 640], "size": "s"}))
        super().__init__({"model_path": str(model), "score_threshold": 0.3}, ctx=None)  # type: ignore[arg-type]
        self._any_size = any_size
        self.box = box
        self.shapes: list[tuple[int, ...]] = []

    def run(self, batch: Any) -> Any:
        self.shapes.append(batch.shape)
        h, w = batch.shape[2:]
        out = np.zeros((len(batch), sum((h // s) * (w // s) for s in (8, 16, 32)), 5 + len(CLASSES)), np.float32)
        x0, y0, x1, y1 = self.box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        a = int(cy // 8) * (w // 8) + int(cx // 8)
        out[0, a, :2] = cx / 8 - int(cx // 8), cy / 8 - int(cy // 8)
        out[0, a, 2:5] = math.log((x1 - x0) / 8), math.log((y1 - y0) / 8), 1
        out[0, a, 6] = 0.9
        return out


def test_a_line_scan_strip_is_stacked_two_pieces_per_tile(tmp_path: Path) -> None:
    # 3840 x 248: eight pieces in four tiles; the second piece of the first tile (x 457) sits 280 rows down.
    m = StripModel(tmp_path, (100, 330, 110, 340), any_size=False)
    found = m.detect_array(np.zeros((248, 3840, 3), np.uint8))
    assert m.shapes == [(4, 3, 640, 640)]
    assert [(tuple(round(v) for v in box), cls) for box, cls, _ in found] == [((557, 50, 567, 60), "stain")]


def test_an_any_size_model_sees_the_whole_strip_at_once(tmp_path: Path) -> None:
    m = StripModel(tmp_path, (2000, 50, 2010, 60), any_size=True)
    found = m.detect_array(np.zeros((248, 3840, 3), np.uint8))
    assert m.shapes == [(1, 3, 256, 3840)]
    assert [(tuple(round(v) for v in box), cls) for box, cls, _ in found] == [((2000, 50, 2010, 60), "stain")]
