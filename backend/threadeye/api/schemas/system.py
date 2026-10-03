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
