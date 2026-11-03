"""Unannotated fabric mosaic from video pixels and public frame positions only.

The simulator's roll_preview contains answer-key boxes and must never be used here.
Grey areas are unobserved: hands, missing frames and off-roll pixels are not invented.
"""

from __future__ import annotations

import csv
import io
import json
from functools import lru_cache
from pathlib import Path

from PIL import Image


def image_bytes(directory: Path) -> bytes:
    names = ("roll_video.mp4", "frames.csv", "roll_meta.json")
    signature = tuple((directory / name).stat().st_mtime_ns for name in names)
    return _render(str(directory), signature)


@lru_cache(maxsize=4)
def _render(directory: str, signature: tuple[int, ...]) -> bytes:
    import cv2

    root = Path(directory)
    meta = json.loads((root / "roll_meta.json").read_text())
    region = meta["view_region"]
    width = round(meta["fabric_width_cm"] * meta["px_per_cm"])
    length = round(meta["roll_length_yd"] * 91.44 * meta["px_per_cm"])
    scale = min(8192 / length, 1024 / width, 1)
    mosaic = Image.new("RGB", (max(1, round(width * scale)), max(1, round(length * scale))), (65, 65, 65))
    # Prefer the first unobstructed observation of each longitudinal strip. Repeated
    # stopped frames cannot overwrite the fabric with a later hand or stop artifact.
    covered = 0
    cap = cv2.VideoCapture(str(root / "roll_video.mp4"))
    try:
        if not cap.isOpened():
            raise ValueError("roll video cannot be decoded")
        with (root / "frames.csv").open(newline="") as stream:
            for pos in csv.DictReader(stream):
                ok, frame = cap.read()
                if not ok:
                    raise ValueError("roll video ended before its frame positions")
                if pos.get("hand_visible", "0") in ("1", "True", "true"):
                    continue
                top = round(float(pos["roll_y_top_px"]))
                start, end = max(0, top, covered), min(length, top + region["h"])
                if end <= start:
                    continue
                x = region["x"] + round(float(pos["fabric_x0_px"]))
                y = region["y"] + start - top
                if x < 0 or x + width > frame.shape[1]:
                    continue
                strip = Image.fromarray(cv2.cvtColor(frame[y : y + end - start, x : x + width], cv2.COLOR_BGR2RGB))
                y0, y1 = round(start * scale), round(end * scale)
                if y1 > y0:
                    mosaic.paste(strip.resize((mosaic.width, y1 - y0), Image.Resampling.LANCZOS), (0, y0))
                covered = end
    finally:
        cap.release()
    # Across-fabric becomes the vertical axis; roll yards run left to right.
    output = io.BytesIO()
    mosaic.transpose(Image.Transpose.TRANSPOSE).save(output, "JPEG", quality=92)
    return output.getvalue()
