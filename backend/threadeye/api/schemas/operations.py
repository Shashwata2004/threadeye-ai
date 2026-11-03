from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from threadeye.api.schemas.common import ApiModel
from threadeye.core.scoring.profile import RuleProfile


class EvaluationIn(ApiModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=5)
    provider_id: Literal["simulated", "local_model"] = "simulated"
    preset: Literal["perfect", "realistic"] = "realistic"
    seed: int = Field(default=42, ge=0, le=2147483647)
    machine_id: uuid.UUID | None = None
    min_recall: float = Field(default=0.8, ge=0, le=1)
    max_false_alarms: int = Field(default=0, ge=0)
    max_score_delta: float = Field(default=2.0, ge=0)


class RunOut(ApiModel):
    id: uuid.UUID
    kind: str
    status: str
    machine_id: uuid.UUID | None
    inspection_id: uuid.UUID | None
    inputs: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ScheduleIn(EvaluationIn):
    enabled: bool = True


class ProviderIn(ApiModel):
    provider_id: Literal["simulated", "local_model"]


class DemoScheduleIn(ApiModel):
    enabled: bool


class CuttingPolicyIn(ApiModel):
    selection: Literal["buyer", "all", "two_plus", "three_plus", "four_plus"]


class Calibration(ApiModel):
    px_per_cm: float = Field(gt=0)
    view_width_px: int = Field(gt=0, le=16384)
    note: str = Field(default="", max_length=500)


class MachineIn(ApiModel):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    active: bool = True
    calibration: Calibration | None = None


class MachineDetail(MachineIn):
    id: uuid.UUID


class ProfileIn(ApiModel):
    buyer_id: uuid.UUID | None = None
    rules: RuleProfile


class ProfileOut(ApiModel):
    id: uuid.UUID
    buyer_id: uuid.UUID | None
    name: str
    version: int
    status: str
    rules: RuleProfile
    rules_hash: str


class PreviewDefect(ApiModel):
    cls: str = "stain"
    start_yd: float = Field(ge=0)
    end_yd: float = Field(ge=0)
    across_start_cm: float = Field(default=10, ge=0)
    across_end_cm: float = Field(default=11, gt=0)
    length_in: float = Field(gt=0)


class PreviewIn(ApiModel):
    rules: RuleProfile
    length_yd: float = Field(gt=0)
    width_in: float = Field(gt=0)
    defects: list[PreviewDefect] = Field(default_factory=list, max_length=1000)
