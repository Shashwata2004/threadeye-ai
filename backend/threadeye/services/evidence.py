"""Evidence photos: which captured frame shows a defect best, and the crop around it.

The browser captures the camera view of sampled frames during the live run. A defect's roll box is
projected into each captured frame (roll → view pixels, PLAN.md §6.1 step 5); the frame where it is
fully visible and closest to the view centre, with no hand in view, gives the evidence photo.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw

from threadeye.core.frames import Calibration, FramePosition
from threadeye.core.geometry import YARD_CM, RollBox, roll_to_view
from threadeye.db.models import DefectRow, InspectionFrame


@dataclass(frozen=True)
class Evidence:
    frame: InspectionFrame
    view_box: tuple[float, float, float, float]


def defect_box(d: DefectRow) -> RollBox:
    return RollBox(d.start_yd * YARD_CM, d.end_yd * YARD_CM, d.across_start_cm, d.across_end_cm)


def best_capture(
    d: DefectRow, frames: Sequence[InspectionFrame], track: Sequence[FramePosition], calib: Calibration
) -> Evidence | None:
    box = defect_box(d)
    view_w, view_h = calib.view_region[2], calib.view_region[3]
    best: tuple[tuple[int, float], Evidence] | None = None
    for f in frames:
        if f.image_key is None or not 0 <= f.frame < len(track):
            continue
        x0, y0, x1, y1 = roll_to_view(box, track[f.frame], calib)
        height = max(y1 - y0, 1e-6)
        visible = (min(y1, view_h) - max(y0, 0.0)) / height
        if visible < 0.5 or x1 < 0 or x0 > view_w:
            continue
        rank = (1 if f.hand_visible else 0, abs((y0 + y1) / 2 - view_h / 2) + (1 - visible) * view_h)
        if best is None or rank < best[0]:
            best = (rank, Evidence(f, (x0, y0, x1, y1)))
    return best[1] if best else None


def crop(
    image: bytes,
    view_box: tuple[float, float, float, float],
    scale: float,
    *,
    size: int = 360,
    context: float = 2.2,
    view_width: float | None = None,
) -> bytes:
    """Square crop around the defect, the box outlined, as JPEG. ``context`` = window side ÷ defect size."""
    with Image.open(io.BytesIO(image)) as img:
        # Older captures can have stale metadata after a smaller image overwrote their blob.
        # Derive the scale from the actual JPEG and the calibrated camera width when available.
        if view_width is not None:
            scale = img.width / view_width
        x0, y0, x1, y1 = (v * scale for v in view_box)
        side = max(x1 - x0, y1 - y0) * context
        side = max(side, 120 * scale * context / 2.2)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        side = min(side, img.width, img.height)
        # Keep the window inside the image (a defect near the edge is then off-centre, not cut off).
        left = min(max(cx - side / 2, 0), img.width - side)
        top = min(max(cy - side / 2, 0), img.height - side)
        region = img.convert("RGB").crop((round(left), round(top), round(left + side), round(top + side)))
        draw = ImageDraw.Draw(region)
        draw.rectangle(
            (x0 - left - 3, y0 - top - 3, x1 - left + 3, y1 - top + 3),
            outline=(220, 38, 38),
            width=max(2, round(side / 120)),
        )
        region = region.resize((size, size))
        out = io.BytesIO()
        region.save(out, "JPEG", quality=85)
        return out.getvalue()
