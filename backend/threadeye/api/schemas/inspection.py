"""Contract: inspection lifecycle, browser-clocked advance loop, defects, verdict (M2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from threadeye.api.schemas.common import ApiModel
from threadeye.api.schemas.events import EventEnvelope

InspectionStatus = Literal["created", "running", "paused", "interrupted", "completed", "aborted"]
Verdict = Literal["PASS", "BORDERLINE", "FAIL"]
FinalDecision = Literal["ACCEPT", "ACCEPT_WITH_CLAIM", "REJECT"]
DefectStatus = Literal["pending", "confirmed", "rejected"]
RejectReason = Literal["sticker", "loose_thread", "wrinkle", "pin_hole", "hand", "board", "not_visible", "other"]
Preset = Literal["perfect", "realistic"]


class SourceSpec(ApiModel):
    kind: Literal["video_file"] = "video_file"
    dataset_id: str = Field(min_length=1, max_length=128)


class InspectionCreate(ApiModel):
    roll_code: str = Field(min_length=1, max_length=64)
    machine_id: uuid.UUID
    source: SourceSpec
    provider_config_id: uuid.UUID | None = None
    preset: Preset | None = None
    """Simulated detector only: ``realistic`` (false alarms and misses) or ``perfect`` (answer key)."""


class ProviderInfoOut(ApiModel):
    provider_id: str
    version: str
    display_name: str
    kind: Literal["simulated", "api", "local_model", "classical"]
    is_simulated: bool
    requires_image: bool
    calibrated_confidence: bool
    bbox_quality: Literal["precise", "approximate"]
    config_hash: str
    preset: str | None = None


class ScoreSummary(ApiModel):
    provisional_points: int
    confirmed_points: int
    per_100_provisional: float | None
    per_100_confirmed: float | None
    threshold: float
    borderline_below: float
    borderline_above: float
    points_budget: float | None
    provisional_verdict: Verdict | None
    confirmed_verdict: Verdict | None = None
    verdict_settled: bool = False
    """The pending defects cannot change the verdict (same verdict whether they are rejected or confirmed)."""
    yards_inspected: float
    at_frame: int | None = None
    """Last frame processed when this score was computed. The server may work ahead of the video the
    inspector watches (like a camera mounted before the inspection board): the screen shows a score
    once the video reaches this frame."""
    coverage_pct: float
    defects: int = 0
    pending: int = 0
    confirmed: int = 0
    rejected: int = 0
    nondefects_ignored: dict[str, int] = Field(default_factory=dict)
    cells: dict[str, int] = Field(default_factory=dict)
    """Yard index → points after the per-yard cap (provisional)."""


class RollContext(ApiModel):
    """The roll, its delivery and the rules it is scored by (shown on the live and verdict screens)."""

    roll_code: str
    mill_roll_no: str
    declared_length_yd: float
    declared_width_in: float
    lot_id: uuid.UUID
    challan_no: str
    supplier: str
    buyer: str
    fabric_type: str
    rule_profile: str
    threshold_per_100: float


class InspectionSnapshot(ApiModel):
    id: uuid.UUID
    roll_id: uuid.UUID
    roll_code: str
    machine_id: uuid.UUID
    status: InspectionStatus
    mode: Literal["production", "demo", "verification", "evaluation"]
    is_simulated: bool
    clock: Literal["browser", "server", "headless"]
    provider: ProviderInfoOut
    rule_profile_id: uuid.UUID
    checkpoint_frame: int
    checkpoint_yd: float
    last_seq: int
    driver_session: bool
    """True if the caller holds the driver lease (may call /advance)."""
    lease_held_elsewhere: bool
    """Another browser session is driving this inspection right now."""
    score: ScoreSummary | None
    system_verdict: Verdict | None
    final_verdict: FinalDecision | None
    started_at: datetime | None
    completed_at: datetime | None
    finalized_at: datetime | None
    points_total: int | None
    points_per_100: float | None
    yards_inspected: float | None
    unreviewed: int = 0
    """Defects left undecided because they could not change the verdict (see ``points_if_all_confirmed``)."""
    points_if_all_confirmed: int | None = None
    verdict_cells: dict[str, int] | None = None
    """Yard index → points of the verdict (confirmed defects, after the per-yard cap)."""
    decision_reason: str | None
    decision_by: str | None
    decision_at: datetime | None
    inspector: str | None
    dataset_id: str | None
    frame_count: int
    roll: RollContext
    model_outdated: bool = False
    """Open, but started on a trained model that has since been replaced: abort it and inspect the roll again."""


class InspectionListItem(ApiModel):
    id: uuid.UUID
    roll_id: uuid.UUID
    roll_code: str
    status: InspectionStatus
    system_verdict: Verdict | None
    final_verdict: FinalDecision | None
    points_per_100: float | None
    checkpoint_frame: int
    started_at: datetime | None
    finalized_at: datetime | None
    created_at: datetime
    inspector: str | None
    is_simulated: bool
    model_outdated: bool = False


class Capture(ApiModel):
    frame: int = Field(ge=0)
    jpeg_b64: str = Field(max_length=2_000_000)
    width: int = Field(gt=0, le=4096)
    height: int = Field(gt=0, le=4096)


class AdvanceIn(ApiModel):
    until_frame: int = Field(ge=0)
    after_seq: int = Field(ge=0)
    captures: list[Capture] = Field(default_factory=list, max_length=8)
    start_key: str | None = Field(default=None, min_length=8, max_length=64)
    """Start (or resume) the inspection in the same request, with this idempotency key: one round trip
    instead of two before the video plays, so the first defect boxes are there from the first frame."""
    takeover: bool = False
    """With ``start_key``: take the driver lease from another device."""


class AdvanceOut(ApiModel):
    checkpoint_frame: int
    last_seq: int
    events: list[EventEnvelope]
    blocked_on_captures: list[int]
    """Frames whose image is required (image-based providers) but was not uploaded."""


class SamplingPlanOut(ApiModel):
    inspection_id: uuid.UUID
    overlap: float
    view_length_px: int
    step_px: float
    frames: list[int]


class TrackOut(ApiModel):
    """Per-frame positions (columnar) so the browser can draw boxes that move with the fabric."""

    dataset_id: str
    fps: float
    frame_count: int
    px_per_cm: float
    view_region: tuple[int, int, int, int]
    fabric_width_cm: float
    selvage_band_px: float | None
    roll_length_yd: float
    video_url: str | None
    video_type: str | None
    roll_y_top_px: list[float]
    top_yd: list[float]
    bottom_yd: list[float]
    speed_m_min: list[float]
    state: list[Literal["running", "stopped", "unknown"]]
    fabric_x0_px: list[float]
    hand_visible: list[bool]


class DefectOut(ApiModel):
    id: uuid.UUID
    inspection_id: uuid.UUID
    defect_no: str
    origin: Literal["detector", "manual"]
    predicted_cls: str
    current_cls: str
    kind: Literal["defect", "nondefect"]
    nondefect_category: str | None
    status: DefectStatus
    reject_reason: str | None
    uncertain: str | None
    start_yd: float
    end_yd: float
    center_yd: float
    across_start_cm: float
    across_end_cm: float
    length_in: float
    length_source: Literal["pixels", "inspector"]
    is_continuous: bool
    is_running: bool
    sightings: int
    first_frame: int | None
    last_frame: int | None
    best_frame: int
    points: int | None
    points_reason: str | None
    excluded_reason: str | None
    explanation: str | None
    provider_label: str | None
    crop_url: str | None
    decided_at: datetime | None


class ConfirmIn(ApiModel):
    note: str | None = Field(default=None, max_length=500)


class RejectIn(ApiModel):
    reason_category: RejectReason
    note: str | None = Field(default=None, max_length=500)


class ReclassifyIn(ApiModel):
    to_cls: str = Field(min_length=1, max_length=64)


class PromoteIn(ApiModel):
    to_cls: str | None = Field(default=None, min_length=1, max_length=64)


class LengthIn(ApiModel):
    length_in: float = Field(gt=0, le=2000)


class ManualDefectIn(ApiModel):
    """A defect the detector missed. Preferably drawn: ``frame`` + ``bbox_px`` (a box in view pixels of
    that frame, at the video's own scale) give the exact position and size, and ``capture`` (a photo
    of that frame) becomes its evidence photo. Otherwise ``center_yd`` + ``length_in``."""

    cls: str = Field(min_length=1, max_length=64)
    frame: int | None = Field(default=None, ge=0)
    bbox_px: tuple[float, float, float, float] | None = None
    capture: Capture | None = None
    center_yd: float | None = Field(default=None, ge=0)
    across_cm: float | None = Field(default=None, ge=0)
    length_in: float | None = Field(default=None, gt=0, le=2000)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _where(self) -> ManualDefectIn:
        if self.bbox_px is not None:
            if self.frame is None:
                raise ValueError("bbox_px needs the frame it was drawn on")
            if self.capture is not None and self.capture.frame != self.frame:
                raise ValueError("the capture must be of the frame the box was drawn on")
        elif self.center_yd is None or self.length_in is None:
            raise ValueError("give bbox_px + frame, or center_yd + length_in")
        return self


class ConfirmPendingIn(ApiModel):
    up_to_yd: float | None = Field(default=None, ge=0)
    """Only defects up to this yard (e.g. the part of the roll already seen); all when omitted."""
    note: str | None = Field(default=None, max_length=500)


class ConfirmPendingOut(ApiModel):
    confirmed: list[str]
    """Defect numbers confirmed by this call (empty if nothing was pending)."""


class MeasurementIn(ApiModel):
    kind: Literal["width", "length"]
    position_yd: float | None = Field(default=None, ge=0)
    value: float = Field(gt=0)
    unit: Literal["in", "yd", "cm", "m"]


class DecisionIn(ApiModel):
    final_verdict: FinalDecision
    reason: str = Field(min_length=3, max_length=1000)


class DatasetOut(ApiModel):
    """A simulated roll that can be inspected (its answer key is never exposed)."""

    id: str
    roll_length_yd: float
    fabric_width_in: float
    frames: int
    fps: float
    mode: str
    note: str | None
    has_video: bool
    video_url: str | None
    is_simulated: bool
