"""Realtime channel contract (PLAN.md §5.1).

Durable events are stored append-only with a per-inspection ``seq`` and delivered by SSE (edge),
polling (cloud) and inside ``/advance`` responses. Clients apply them idempotently by ``seq``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(StrEnum):
    SESSION_STARTED = "session.started"
    SESSION_PAUSED = "session.paused"
    SESSION_RESUMED = "session.resumed"
    SESSION_INTERRUPTED = "session.interrupted"
    SESSION_COMPLETED = "session.completed"
    SESSION_ABORTED = "session.aborted"
    MACHINE_STOPPED = "machine.stopped"
    MACHINE_STARTED = "machine.started"
    FRAME_SAMPLED = "frame.sampled"
    DETECTION_BATCH = "detection.batch"
    DEFECT_UPSERTED = "defect.upserted"
    SCORE_UPDATED = "score.updated"
    MEASUREMENT_RECORDED = "measurement.recorded"
    VERDICT_COMPUTED = "verdict.computed"
    VERDICT_DECIDED = "verdict.decided"
    CLIP_READY = "clip.ready"
    ALERT = "alert"


EPHEMERAL_TYPES = ("machine.tick", "heartbeat")
"""Not stored, no ``seq``; only for server-clocked sources (future webcam)."""


class Actor(BaseModel):
    kind: Literal["user", "engine", "system"]
    user_id: uuid.UUID | None = None


class EventEnvelope(BaseModel):
    v: Literal[1] = 1
    inspection_id: uuid.UUID
    seq: int = Field(ge=1)
    type: EventType
    at: datetime
    actor: Actor
    simulated: bool
    provider: str | None = None
    """``provider_id@version`` that produced the detections in this inspection."""
    payload: dict[str, Any]


class EventsPage(BaseModel):
    inspection_id: uuid.UUID
    events: list[EventEnvelope]
    last_seq: int
    has_more: bool
