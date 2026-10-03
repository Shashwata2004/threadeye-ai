"""Contract v0: inspection lifecycle, browser-clocked advance loop, defects, verdict (M1/M2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from threadeye.api.schemas.common import ApiModel
from threadeye.api.schemas.events import EventEnvelope

InspectionStatus = Literal["created", "running", "paused", "interrupted", "completed", "aborted"]
Verdict = Literal["PASS", "BORDERLINE", "FAIL"]
FinalDecision = Literal["ACCEPT", "ACCEPT_WITH_CLAIM", "REJECT"]
DefectStatus = Literal["pending", "confirmed", "rejected"]
RejectReason = Literal["sticker", "loose_thread", "wrinkle", "pin_hole", "hand", "board", "not_visible", "other"]


class SourceSpec(ApiModel):
    kind: Literal["video_file"] = "video_file"
    dataset_id: str = Field(min_length=1, max_length=128)


class InspectionCreate(ApiModel):
    roll_code: str = Field(min_length=1, max_length=64)
    machine_id: uuid.UUID
    source: SourceSpec
    provider_config_id: uuid.UUID | None = None


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
    yards_inspected: float
    coverage_pct: float


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
    score: ScoreSummary | None
    system_verdict: Verdict | None
    final_verdict: FinalDecision | None
    started_at: datetime | None
    completed_at: datetime | None


class Capture(ApiModel):
    frame: int = Field(ge=0)
    jpeg_b64: str = Field(max_length=2_000_000)
    width: int = Field(gt=0, le=4096)
    height: int = Field(gt=0, le=4096)


class AdvanceIn(ApiModel):
    until_frame: int = Field(ge=0)
    after_seq: int = Field(ge=0)
    captures: list[Capture] = Field(default_factory=list, max_length=8)


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

    fps: float
    frame_count: int
    px_per_cm: float
    view_region: tuple[int, int, int, int]
    roll_y_top_px: list[float]
    top_yd: list[float]
    bottom_yd: list[float]
    speed_m_min: list[float]
    state: list[Literal["running", "stopped"]]
    fabric_x0_px: list[float]
    hand_visible: list[bool]


class DefectOut(ApiModel):
    id: uuid.UUID
    defect_no: str
    origin: Literal["detector", "manual"]
    predicted_cls: str
    current_cls: str
    kind: Literal["defect", "nondefect"]
    nondefect_category: str | None
    status: DefectStatus
    start_yd: float
    end_yd: float
    center_yd: float
    across_start_cm: float
    across_end_cm: float
    length_in: float
    length_source: Literal["pixels", "inspector"]
    is_continuous: bool
    sightings: int
    points: int | None
    excluded_reason: str | None
    explanation: str | None
    provider_label: str | None
    crop_url: str | None


class ConfirmIn(ApiModel):
    note: str | None = Field(default=None, max_length=500)


class RejectIn(ApiModel):
    reason_category: RejectReason
    note: str | None = Field(default=None, max_length=500)


class ReclassifyIn(ApiModel):
    to_cls: str = Field(min_length=1, max_length=64)


class LengthIn(ApiModel):
    length_in: float = Field(gt=0, le=2000)


class ManualDefectIn(ApiModel):
    cls: str = Field(min_length=1, max_length=64)
    center_yd: float = Field(ge=0)
    across_cm: float | None = Field(default=None, ge=0)
    length_in: float = Field(gt=0, le=2000)
    note: str | None = Field(default=None, max_length=500)


class MeasurementIn(ApiModel):
    kind: Literal["width", "length"]
    position_yd: float | None = Field(default=None, ge=0)
    value: float = Field(gt=0)
    unit: Literal["in", "yd", "cm", "m"]


class DecisionIn(ApiModel):
    final_verdict: FinalDecision
    reason: str = Field(min_length=3, max_length=1000)
