"""Inspection event store: append-only events + projections, in the caller's transaction.

Power-loss safety (PLAN.md §6.1, §12) comes from three properties, all tested:
- events and the defect projection they change are written in ONE transaction (all or nothing)
- ``seq`` is allocated under a row lock on the inspection, so it is gap-free and ordered
- every event carries a deterministic idempotency key, so re-processing frames after a crash
  writes nothing new
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from threadeye.core.runner import RunnerEvent
from threadeye.db.models import DefectRow, Inspection, InspectionEvent

DEFECT_FIELDS = (
    "origin",
    "predicted_cls",
    "current_cls",
    "kind",
    "nondefect_category",
    "status",
    "start_yd",
    "end_yd",
    "center_yd",
    "across_start_cm",
    "across_end_cm",
    "length_in",
    "length_source",
    "is_running",
    "sightings",
    "best_frame",
    "points",
    "explanation",
    "provider",
)


@dataclass(frozen=True)
class AppendResult:
    written: int
    skipped: int
    last_seq: int


def _lock(db: Session, inspection_id: uuid.UUID) -> Inspection:
    inspection = db.scalars(select(Inspection).where(Inspection.id == inspection_id).with_for_update()).one()
    return inspection


def append_events(
    db: Session,
    inspection_id: uuid.UUID,
    events: Iterable[RunnerEvent],
    *,
    actor_kind: str = "engine",
    actor_user_id: uuid.UUID | None = None,
    checkpoint_frame: int | None = None,
) -> AppendResult:
    """Append events and update projections. The caller commits (or rolls back) the transaction."""
    batch = list(events)
    inspection = _lock(db, inspection_id)
    keys = [e.idempotency_key for e in batch]
    existing = set(db.scalars(select(InspectionEvent.idempotency_key).where(InspectionEvent.idempotency_key.in_(keys))))
    seq = inspection.last_seq
    written = 0
    for event in batch:
        if event.idempotency_key in existing:
            continue
        existing.add(event.idempotency_key)
        seq += 1
        db.add(
            InspectionEvent(
                inspection_id=inspection_id,
                seq=seq,
                type=event.type,
                actor_kind=actor_kind,
                actor_user_id=actor_user_id,
                idempotency_key=event.idempotency_key,
                payload=event.payload,
            )
        )
        written += 1
        if event.type == "defect.upserted":
            _upsert_defect(db, inspection_id, event.payload["defect"])
    inspection.last_seq = seq
    if checkpoint_frame is not None and checkpoint_frame > inspection.checkpoint_frame:
        inspection.checkpoint_frame = checkpoint_frame
    db.flush()
    return AppendResult(written=written, skipped=len(batch) - written, last_seq=seq)


def _upsert_defect(db: Session, inspection_id: uuid.UUID, defect: Mapping[str, Any]) -> None:
    values = {k: defect[k] for k in DEFECT_FIELDS}
    stmt = insert(DefectRow).values(inspection_id=inspection_id, defect_no=defect["defect_no"], **values)
    stmt = stmt.on_conflict_do_update(constraint="uq_defects_inspection_id_defect_no", set_=values)
    db.execute(stmt)


def events_after(db: Session, inspection_id: uuid.UUID, after_seq: int, limit: int = 500) -> list[InspectionEvent]:
    return list(
        db.scalars(
            select(InspectionEvent)
            .where(InspectionEvent.inspection_id == inspection_id, InspectionEvent.seq > after_seq)
            .order_by(InspectionEvent.seq)
            .limit(limit)
        )
    )
