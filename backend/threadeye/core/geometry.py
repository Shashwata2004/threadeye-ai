"""Pixels ↔ roll coordinates (PLAN.md §6.1 step 5).

View pixels are measured inside ``view_region`` (y from its top edge). Roll coordinates:
``along`` = distance from the roll's start (cm), ``across`` = distance from the fabric's left edge (cm).

    roll_y_px = roll_y_top_px[f] + y        across_cm = (x - fabric_x0_px[f]) / px_per_cm
    yard      = roll_y_px / px_per_cm / 91.44

The inverse lets the browser overlay keep a box attached to the fabric as it moves between detections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from threadeye.core.frames import Calibration, FramePosition
from threadeye.core.providers import BBox

YARD_CM = 91.44
INCH_CM = 2.54
Truncation = Literal["top", "bottom", "both"] | None


@dataclass(frozen=True)
class RollBox:
    along_start_cm: float
    along_end_cm: float
    across_start_cm: float
    across_end_cm: float

    def __post_init__(self) -> None:
        if self.along_end_cm < self.along_start_cm or self.across_end_cm < self.across_start_cm:
            raise ValueError(f"inverted roll box {self}")

    # ---------------------------------------------------------------------------- derived values
    @property
    def start_yd(self) -> float:
        return self.along_start_cm / YARD_CM

    @property
    def end_yd(self) -> float:
        return self.along_end_cm / YARD_CM

    @property
    def center_yd(self) -> float:
        return (self.along_start_cm + self.along_end_cm) / 2 / YARD_CM

    @property
    def along_center_cm(self) -> float:
        return (self.along_start_cm + self.along_end_cm) / 2

    @property
    def across_center_cm(self) -> float:
        return (self.across_start_cm + self.across_end_cm) / 2

    @property
    def height_cm(self) -> float:
        return self.along_end_cm - self.along_start_cm

    @property
    def width_cm(self) -> float:
        return self.across_end_cm - self.across_start_cm

    @property
    def length_in(self) -> float:
        """Largest dimension in inches: the 4-point "length" (same formula as the simulator)."""
        return max(self.width_cm, self.height_cm) / INCH_CM

    # ---------------------------------------------------------------------------- comparisons
    def intersection_area(self, other: RollBox) -> float:
        h = min(self.along_end_cm, other.along_end_cm) - max(self.along_start_cm, other.along_start_cm)
        w = min(self.across_end_cm, other.across_end_cm) - max(self.across_start_cm, other.across_start_cm)
        return max(0.0, h) * max(0.0, w)

    def iou(self, other: RollBox) -> float:
        inter = self.intersection_area(other)
        union = self.height_cm * self.width_cm + other.height_cm * other.width_cm - inter
        return inter / union if union > 0 else 0.0

    def center_distance_cm(self, other: RollBox) -> float:
        da = self.along_center_cm - other.along_center_cm
        dx = self.across_center_cm - other.across_center_cm
        return float((da * da + dx * dx) ** 0.5)

    def union(self, other: RollBox) -> RollBox:
        return RollBox(
            min(self.along_start_cm, other.along_start_cm),
            max(self.along_end_cm, other.along_end_cm),
            min(self.across_start_cm, other.across_start_cm),
            max(self.across_end_cm, other.across_end_cm),
        )

    @staticmethod
    def mean(boxes: list[RollBox]) -> RollBox:
        n = len(boxes)
        if not n:
            raise ValueError("no boxes to average")
        return RollBox(
            sum(b.along_start_cm for b in boxes) / n,
            sum(b.along_end_cm for b in boxes) / n,
            sum(b.across_start_cm for b in boxes) / n,
            sum(b.across_end_cm for b in boxes) / n,
        )


def view_to_roll(bbox_px: BBox, pos: FramePosition, calib: Calibration, image_scale: float = 1.0) -> RollBox:
    """Map a box in (possibly scaled) view pixels of frame ``pos`` into roll coordinates."""
    x0, y0, x1, y1 = (v / image_scale for v in bbox_px)
    fabric_x0 = pos.fabric_x0_px or 0.0
    ppc = calib.px_per_cm
    return RollBox(
        along_start_cm=(pos.roll_y_top_px + y0) / ppc,
        along_end_cm=(pos.roll_y_top_px + y1) / ppc,
        across_start_cm=(x0 - fabric_x0) / ppc,
        across_end_cm=(x1 - fabric_x0) / ppc,
    )


def roll_to_view(box: RollBox, pos: FramePosition, calib: Calibration) -> BBox:
    """Where a roll box appears in frame ``pos`` (view pixels, unclipped)."""
    ppc = calib.px_per_cm
    fabric_x0 = pos.fabric_x0_px or 0.0
    return (
        box.across_start_cm * ppc + fabric_x0,
        box.along_start_cm * ppc - pos.roll_y_top_px,
        box.across_end_cm * ppc + fabric_x0,
        box.along_end_cm * ppc - pos.roll_y_top_px,
    )


def clip_to_view(bbox: BBox, calib: Calibration) -> BBox | None:
    w, h = calib.view_region[2], calib.view_region[3]
    x0, y0, x1, y1 = max(0.0, bbox[0]), max(0.0, bbox[1]), min(float(w), bbox[2]), min(float(h), bbox[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def truncation(bbox: BBox, calib: Calibration, margin_px: float = 3.0) -> Truncation:
    """Whether a box touches the top/bottom edge of the view (the defect continues outside it)."""
    top = bbox[1] <= margin_px
    bottom = bbox[3] >= calib.view_region[3] - margin_px
    if top and bottom:
        return "both"
    if top:
        return "top"
    if bottom:
        return "bottom"
    return None


def yd_to_px(yd: float, calib: Calibration) -> float:
    return yd * YARD_CM * calib.px_per_cm
