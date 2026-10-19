from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from threadeye.api.schemas.common import ApiModel


class HealthOut(ApiModel):
    status: Literal["ok", "error"]
    db: Literal["ok", "error"]
    profile: Literal["edge", "cloud_demo"]
    version: str
    simulated_mode: bool


class WorkerStatus(ApiModel):
    alive: bool
    last_seen_at: datetime | None


class ProviderAvailabilityOut(ApiModel):
    provider_id: str
    display_name: str
    kind: Literal["simulated", "api", "local_model", "classical"]
    is_simulated: bool
    availability: Literal["available", "planned", "stub"]
    milestone: str
    note: str
    active: bool


class SystemStatusOut(ApiModel):
    profile: Literal["edge", "cloud_demo"]
    version: str
    db: Literal["ok", "error"]
    worker: WorkerStatus
    active_provider: ProviderAvailabilityOut
    simulated_mode: bool
    sample_data_present: bool


class AuditEntryOut(ApiModel):
    id: int
    at: datetime
    actor_user_id: uuid.UUID | None
    actor_role: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    hash: str


class AuditVerifyOut(ApiModel):
    ok: bool
    checked: int
    first_bad_id: int | None
    reason: str | None


class ClassResultOut(ApiModel):
    cls: str
    nondefect: bool
    """A non-defect class (sticker, loose thread, wrinkle, hand): the app shows it grey, never scores it."""
    threshold: float
    truth: int
    recall: float | None
    precision: float | None


class SourceResultOut(ApiModel):
    source: str
    tiles: int
    defects: int
    found_any_class: float | None
    found_right_class: float | None
    false_alarms_per_100_tiles: float


class ModelEvaluationOut(ApiModel):
    """The trained detector measured on the held-out test split (never seen in training)."""

    model: str
    framework: str
    epochs: int
    train_minutes: float | None
    classes: list[str]
    matching: str
    thresholds_from: str
    tiles: int
    defects: int
    found_any_class: float | None
    found_right_class: float | None
    defect_boxes: int
    precision: float | None
    """Share of defect boxes on a real defect (duplicates of a found defect not counted)."""
    false_alarms: int
    false_alarms_per_100_tiles: float
    nondefects: int
    nondefects_called_defect: float | None
    per_class: list[ClassResultOut]
    per_source: list[SourceResultOut]
