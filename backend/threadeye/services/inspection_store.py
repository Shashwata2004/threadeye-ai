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

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from threadeye.core.runner import RunnerEvent
from threadeye.db.models import DefectRow, Inspection, InspectionEvent, InspectionFrame

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
    "reject_reason",
    "uncertain",
    "is_continuous",
    "excluded_reason",
    "points_reason",
    "first_frame",
    "last_frame",
    "best_bbox_px",
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
    locked: Inspection | None = None,
) -> AppendResult:
    """Append events and update projections. The caller commits (or rolls back) the transaction.

    ``locked``: the inspection row, when the caller already holds its lock (saves a round trip).
    """
    batch = list(events)
    inspection = locked if locked is not None and locked.id == inspection_id else _lock(db, inspection_id)
    keys = [e.idempotency_key for e in batch]
    existing = set(db.scalars(select(InspectionEvent.idempotency_key).where(InspectionEvent.idempotency_key.in_(keys))))
    seq = inspection.last_seq
    written = 0
    defects: dict[str, dict[str, Any]] = {}
    decided: dict[str, dict[str, Any]] = {}
    frames: dict[int, dict[str, Any]] = {}
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
            row = _defect_values(inspection_id, event.payload["defect"])
            # The last version of a defect in the batch wins; decisions also record who decided.
            defects[row["defect_no"]] = row
            if event.payload.get("decision"):
                decided[row["defect_no"]] = row
        elif event.type == "frame.sampled":
            f = _frame_values(inspection_id, event.payload)
            frames[f["frame"]] = f
    inspection.last_seq = seq
    if checkpoint_frame is not None and checkpoint_frame > inspection.checkpoint_frame:
        inspection.checkpoint_frame = checkpoint_frame
    db.flush()
    # One statement per projection, not one per row: each round trip to a remote database costs.
    _upsert_defects(db, [r for no, r in defects.items() if no not in decided], None)
    _upsert_defects(db, list(decided.values()), actor_user_id)
    _upsert_frames(db, list(frames.values()))
    return AppendResult(written=written, skipped=len(batch) - written, last_seq=seq)


def _defect_values(inspection_id: uuid.UUID, defect: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {k: defect.get(k) for k in DEFECT_FIELDS}
    values["is_continuous"] = bool(values["is_continuous"])
    return {"inspection_id": inspection_id, "defect_no": defect["defect_no"], **values}


def _upsert_defects(db: Session, rows: list[dict[str, Any]], decided_by: uuid.UUID | None) -> None:
    if not rows:
        return
    if decided_by is not None:
        rows = [{**r, "decided_by": decided_by} for r in rows]
    stmt = insert(DefectRow).values(rows)
    update: dict[str, Any] = {k: stmt.excluded[k] for k in DEFECT_FIELDS}
    if decided_by is not None:
        update |= {"decided_by": stmt.excluded.decided_by, "decided_at": func.now()}
    db.execute(stmt.on_conflict_do_update(constraint="uq_defects_inspection_id_defect_no", set_=update))


def _frame_values(inspection_id: uuid.UUID, frame: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "inspection_id": inspection_id,
        "frame": frame["frame"],
        "top_yd": frame.get("top_yd"),
        "bottom_yd": frame.get("bottom_yd"),
        "hand_visible": bool(frame.get("hand_visible")),
        "sample_reason": frame.get("sample_reason"),
    }


def _upsert_frames(db: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = insert(InspectionFrame).values(rows)
    update = {k: stmt.excluded[k] for k in ("top_yd", "bottom_yd", "hand_visible", "sample_reason")}
    db.execute(stmt.on_conflict_do_update(constraint="uq_inspection_frames_inspection_id_frame", set_=update))


def events_after(db: Session, inspection_id: uuid.UUID, after_seq: int, limit: int = 500) -> list[InspectionEvent]:
    return list(
        db.scalars(
            select(InspectionEvent)
            .where(InspectionEvent.inspection_id == inspection_id, InspectionEvent.seq > after_seq)
            .order_by(InspectionEvent.seq)
            .limit(limit)
        )
    )
