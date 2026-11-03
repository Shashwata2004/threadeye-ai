from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from threadeye.services.roll_image import image_bytes


def test_mosaic_tracks_drift_skips_hands_and_keeps_first_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    (tmp_path / "roll_meta.json").write_text(
        json.dumps(
            {
                "view_region": {"x": 0, "y": 10, "w": 140, "h": 40},
                "fabric_width_cm": 80,
                "px_per_cm": 1,
                "roll_length_yd": 160 / 91.44,
            }
        )
    )
    (tmp_path / "frames.csv").write_text(
        "frame,roll_y_top_px,fabric_x0_px,hand_visible\n0,0,20,0\n1,40,30,1\n2,80,40,0\n3,80,40,0\n4,120,20,0\n"
    )
    (tmp_path / "roll_video.mp4").touch()
    # No answer key or annotated preview exists. Magenta board/label/hand pixels
    # must never appear in the stitched fabric; a repeated frame must not replace it.
    frames = []
    for x, color in [
        (20, (20, 140, 20)),
        (30, (255, 0, 255)),
        (40, (140, 20, 20)),
        (40, (255, 0, 255)),
        (20, (20, 20, 140)),
    ]:
        frame = np.full((60, 140, 3), (255, 0, 255), dtype=np.uint8)
        frame[10:50, x : x + 80] = color
        frames.append(frame)

    class Capture:
        released = False

        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, Any]:
            return (True, frames.pop(0)) if frames else (False, None)

        def release(self) -> None:
            self.released = True

    capture = Capture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: capture)
    rendered = image_bytes(tmp_path)
    image = Image.open(io.BytesIO(rendered))
    assert image.size == (160, 80)
    for xy, expected in [
        ((20, 40), (20, 140, 20)),
        ((60, 40), (65, 65, 65)),
        ((100, 40), (20, 20, 140)),
        ((140, 40), (140, 20, 20)),
    ]:
        assert image.getpixel(xy) == pytest.approx(expected, abs=5)
    assert capture.released
    # The second request uses the cached image, not a second decoder pass.
    assert image_bytes(tmp_path) == rendered


def test_missing_video_is_unavailable_instead_of_using_answer_key_preview(tmp_path: Path) -> None:
    (tmp_path / "roll_preview.png").write_bytes(b"annotated-answer-key")
    with pytest.raises(FileNotFoundError):
        image_bytes(tmp_path)
