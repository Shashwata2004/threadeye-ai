"""Live inspection service (M2): lifecycle, the browser-clocked advance loop, inspector decisions, verdict.

Every command runs in one transaction under a row lock on the inspection (``SELECT … FOR UPDATE``):
commands on one roll are serialised, and events + projections + checkpoint commit together or not
at all (PLAN.md §6.1). The runner (pure core) is rebuilt from stored events when needed, so any API
process, or a restarted one after a power cut, continues exactly where the inspection stopped. A
small per-process cache avoids the rebuild between calls; it is keyed by ``last_seq`` and an entry is
put back only after a successful commit.

The driver lease: only one browser session at a time may call /advance for an inspection (the one
playing the video). It expires after ``LEASE_SECONDS`` without a call; a running inspection whose
lease expired is shown as "interrupted" and can be resumed from its checkpoint.
"""

from __future__ import annotations

import base64
import binascii
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from threadeye.core.providers import ProviderContext
from threadeye.core.runner import DecisionError, RollSpec, Runner, RunnerEvent
from threadeye.core.scoring.profile import RuleProfile
from threadeye.db import audit
from threadeye.db.models import (
    DefectRow,
    Inspection,
    InspectionEvent,
    InspectionFrame,
    Lot,
    Machine,
    Roll,
    RuleProfileRow,
    User,
)
from threadeye.providers.registry import REGISTRY, create_provider
from threadeye.providers.simulated import PRESETS
from threadeye.services import datasets, storage
from threadeye.services.inspection_store import append_events, events_after
from threadeye.settings import get_settings

LEASE_SECONDS = 30
OPEN = ("created", "running", "paused", "interrupted")
CACHE_SIZE = 16


class InspectionError(Exception):
    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.extra = extra


def now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------------------------------ runner cache
@dataclass
class _Entry:
    last_seq: int
    checkpoint: int
    runner: Runner


_cache: OrderedDict[uuid.UUID, _Entry] = OrderedDict()
_cache_lock = threading.Lock()


def _take(insp: Inspection) -> Runner | None:
    with _cache_lock:
        entry = _cache.pop(insp.id, None)
    if entry and entry.last_seq == insp.last_seq and entry.checkpoint == insp.checkpoint_frame:
        return entry.runner
    return None


def _give_back(insp: Inspection, runner: Runner) -> None:
    with _cache_lock:
        _cache[insp.id] = _Entry(insp.last_seq, insp.checkpoint_frame, runner)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def roll_spec(insp: Inspection, roll: Roll, info: datasets.DatasetInfo) -> RollSpec:
    """Width is the roll's declared width. While the camera is simulated, the roll's length is the
    simulated roll's length: the score covers what the video shows, not the 100 yd on the label."""
    return RollSpec(width_in=roll.declared_width_in, declared_length_yd=info.roll_length_yd)


def build_runner(db: Session, insp: Inspection) -> Runner:
    if not insp.dataset_id:
        raise InspectionError(409, "this inspection has no video source")
    info = datasets.get_dataset(insp.dataset_id)
    roll = db.get(Roll, insp.roll_id)
    profile_row = db.get(RuleProfileRow, insp.rule_profile_id)
    assert roll and profile_row
    snap = insp.provider_snapshot
    provider = create_provider(
        snap["provider_id"],
        snap.get("config") or {},
        ProviderContext(seed=int((snap.get("config") or {}).get("seed", 0)), extras={"dataset_dir": str(info.path)}),
    )
    return Runner(
        datasets.track_source(info),
        provider,
        RuleProfile(**profile_row.rules),
        roll_spec(insp, roll, info),
        inspection_id=str(insp.id),
    )


def runner_for(db: Session, insp: Inspection) -> Runner:
    """The runner at the inspection's stored state (cached, or rebuilt from the events)."""
    cached = _take(insp)
    if cached is not None:
        return cached
    runner = build_runner(db, insp)
    rows = db.execute(
        select(InspectionEvent.type, InspectionEvent.payload)
        .where(InspectionEvent.inspection_id == insp.id)
        .order_by(InspectionEvent.seq)
    ).all()
    runner.restore(((r.type, r.payload) for r in rows), insp.checkpoint_frame)
    return runner


def read_runner(db: Session, insp: Inspection) -> Runner:
    """For read-only use: returns the runner to the cache right away."""
    runner = runner_for(db, insp)
    _give_back(insp, runner)
    return runner


# ------------------------------------------------------------------------------------------ helpers
def lock(db: Session, inspection_id: uuid.UUID) -> Inspection:
    insp = db.scalars(select(Inspection).where(Inspection.id == inspection_id).with_for_update()).one_or_none()
    if insp is None:
        raise InspectionError(404, "inspection not found")
    return insp


def effective_status(insp: Inspection) -> str:
    if insp.status == "running" and (insp.driver_expires_at is None or insp.driver_expires_at < now()):
        return "interrupted"
    return insp.status


def holds_lease(insp: Inspection, session_id: uuid.UUID | None) -> bool:
    return bool(
        session_id
        and insp.driver_session_id == session_id
        and insp.driver_expires_at is not None
        and insp.driver_expires_at >= now()
    )


def _cmd_key(insp: Inspection, idem: str) -> Callable[[str, str], str]:
    return lambda type_, no: f"{insp.id}:cmd:{idem}:{type_}{':' + no if no else ''}"


def provider_snapshot(preset: str) -> dict[str, Any]:
    if preset not in PRESETS:
        raise InspectionError(422, f"unknown simulated preset {preset!r}")
    config = dict(PRESETS[preset])
    spec = REGISTRY["simulated"]
    info = create_provider("simulated", config).info
    return {
        "provider_id": spec.provider_id,
        "preset": preset,
        "config": config,
        "info": {
            "provider_id": info.provider_id,
            "version": info.version,
            "display_name": info.display_name,
            "kind": info.kind,
            "is_simulated": info.is_simulated,
            "requires_image": info.requires_image,
            "calibrated_confidence": info.calibrated_confidence,
            "bbox_quality": info.bbox_quality,
            "config_hash": info.config_hash,
        },
    }


def _audit(db: Session, action: str, insp: Inspection, actor: User, ip: str | None, **after: Any) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="inspection",
        entity_id=str(insp.id),
        after=after or None,
        ip=ip,
    )


# ------------------------------------------------------------------------------------------ lifecycle
def create(
    db: Session,
    *,
    roll_code: str,
    machine_id: uuid.UUID,
    dataset_id: str,
    preset: str | None,
    actor: User,
    ip: str | None = None,
) -> Inspection:
    roll = db.scalar(select(Roll).where(Roll.roll_code == roll_code.strip().upper()).with_for_update())
    if roll is None:
        raise InspectionError(404, "no roll with this code")
    if db.get(Machine, machine_id) is None:
        raise InspectionError(404, "machine not found")
    try:
        info = datasets.get_dataset(dataset_id)
    except datasets.DatasetNotFound as exc:
        raise InspectionError(422, f"no simulated roll called {dataset_id!r}") from exc
    open_insp = db.scalar(select(Inspection).where(Inspection.roll_id == roll.id, Inspection.status.in_(OPEN)))
    if open_insp is not None:
        raise InspectionError(409, "this roll already has an open inspection", inspection_id=str(open_insp.id))
    lot = db.get(Lot, roll.lot_id)
    assert lot
    snapshot = provider_snapshot(preset or get_settings().simulated_preset)
    source = datasets.track_source(info).open()
    insp = Inspection(
        roll_id=roll.id,
        machine_id=machine_id,
        inspector_id=actor.id,
        rule_profile_id=lot.rule_profile_id,
        provider_snapshot=snapshot,
        source_descriptor=dict(source.descriptor),
        dataset_id=info.id,
        mode="demo",
        is_simulated=True,
        clock="browser",
        status="created",
    )
    db.add(insp)
    roll.status = "in_inspection"
    db.flush()
    _audit(
        db, "inspection.create", insp, actor, ip, roll_code=roll.roll_code, dataset=info.id, preset=snapshot["preset"]
    )
    return insp


def start(
    db: Session, insp: Inspection, actor: User, session_id: uuid.UUID | None, idem: str, *, takeover: bool = False
) -> list[RunnerEvent]:
    """Start or resume, and take the driver lease for this browser session."""
    if session_id is None:
        raise InspectionError(401, "no session")
    status = effective_status(insp)
    if status not in OPEN:
        raise InspectionError(409, f"inspection is {status}")
    if status == "running" and not holds_lease(insp, session_id) and not takeover:
        raise InspectionError(409, "another device is running this inspection", lease_held=True)
    key = _cmd_key(insp, idem)
    runner = runner_for(db, insp)
    pos = runner.position()
    at = {"checkpoint_frame": insp.checkpoint_frame, "checkpoint_yd": round(pos.bottom_yd, 3) if pos else 0.0}
    if insp.status == "created":
        events = [RunnerEvent("session.started", {**at, "inspector": actor.display_name}, key("session.started", ""))]
        insp.started_at = now()
    elif insp.status == "running" and holds_lease(insp, session_id):
        events = []
    else:
        reason = {"paused": "inspector", "interrupted": "power_or_connection"}.get(status, "takeover")
        events = [RunnerEvent("session.resumed", {**at, "reason": reason}, key("session.resumed", ""))]
    insp.status = "running"
    insp.driver_session_id = session_id
    insp.driver_expires_at = now() + timedelta(seconds=LEASE_SECONDS)
    append_events(db, insp.id, events, actor_kind="user", actor_user_id=actor.id)
    _give_back_after_commit(db, insp, runner)
    return events


def pause(db: Session, insp: Inspection, actor: User, idem: str) -> None:
    if effective_status(insp) not in ("running", "interrupted"):
        raise InspectionError(409, f"inspection is {insp.status}")
    insp.status = "paused"
    key = _cmd_key(insp, idem)
    ev = RunnerEvent("session.paused", {"checkpoint_frame": insp.checkpoint_frame}, key("session.paused", ""))
    append_events(db, insp.id, [ev], actor_kind="user", actor_user_id=actor.id)


def complete(db: Session, insp: Inspection, actor: User, idem: str, ip: str | None) -> None:
    """The whole roll has passed under the camera."""
    if insp.status not in OPEN:
        raise InspectionError(409, f"inspection is {insp.status}")
    runner = runner_for(db, insp)
    if not runner.finished:
        pos = runner.position()
        raise InspectionError(
            409,
            f"the roll has not run to the end yet ({pos.bottom_yd if pos else 0:.1f} of "
            f"{runner.track[-1].bottom_yd:.1f} yd)",
        )
    insp.status = "completed"
    insp.completed_at = now()
    insp.driver_session_id = None
    insp.driver_expires_at = None
    key = _cmd_key(insp, idem)
    payload = {"checkpoint_frame": insp.checkpoint_frame, **runner.counts()}
    append_events(
        db,
        insp.id,
        [RunnerEvent("session.completed", payload, key("session.completed", ""))],
        actor_kind="user",
        actor_user_id=actor.id,
    )
    _audit(db, "inspection.complete", insp, actor, ip, **runner.counts())
    _give_back_after_commit(db, insp, runner)


def abort(db: Session, insp: Inspection, actor: User, idem: str, ip: str | None) -> None:
    if insp.status not in OPEN:
        raise InspectionError(409, f"inspection is {insp.status}")
    insp.status = "aborted"
    insp.driver_session_id = None
    insp.driver_expires_at = None
    roll = db.get(Roll, insp.roll_id)
    if roll and roll.status == "in_inspection":
        roll.status = "registered"
    key = _cmd_key(insp, idem)
    ev = RunnerEvent("session.aborted", {"checkpoint_frame": insp.checkpoint_frame}, key("session.aborted", ""))
    append_events(db, insp.id, [ev], actor_kind="user", actor_user_id=actor.id)
    _audit(db, "inspection.abort", insp, actor, ip, checkpoint_frame=insp.checkpoint_frame)


# ------------------------------------------------------------------------------------------ advance
@dataclass(frozen=True)
class CaptureIn:
    frame: int
    jpeg_b64: str
    width: int
    height: int


def store_captures(db: Session, insp: Inspection, runner: Runner, captures: Sequence[CaptureIn]) -> int:
    """Evidence images captured by the browser (the view region of the frames it sampled)."""
    view_w = runner.calibration.view_region[2]
    stored = 0
    for c in captures:
        if not 0 <= c.frame < len(runner.track):
            raise InspectionError(422, f"frame {c.frame} is outside this roll")
        try:
            raw = base64.b64decode(c.jpeg_b64, validate=True)
            jpeg, w, h = storage.clean_jpeg(raw)
        except (binascii.Error, storage.StorageError) as exc:
            raise InspectionError(422, f"capture of frame {c.frame}: {exc}") from exc
        key = f"inspections/{insp.id}/frames/{c.frame:06d}.jpg"
        sha = storage.put(key, jpeg)
        row = db.scalar(
            select(InspectionFrame).where(InspectionFrame.inspection_id == insp.id, InspectionFrame.frame == c.frame)
        )
        pos = runner.track[c.frame]
        if row is None:
            row = InspectionFrame(
                inspection_id=insp.id,
                frame=c.frame,
                top_yd=pos.top_yd,
                bottom_yd=pos.bottom_yd,
                hand_visible=bool(pos.hand_visible),
                sample_reason="capture",
            )
            db.add(row)
        row.image_key, row.image_sha256, row.width, row.height = key, sha, w, h
        row.image_scale = w / view_w
        row.captured_at = now()
        stored += 1
    return stored


@dataclass(frozen=True)
class AdvanceResult:
    checkpoint_frame: int
    last_seq: int
    written: int


def advance(
    db: Session,
    insp: Inspection,
    *,
    until_frame: int,
    captures: Sequence[CaptureIn],
    session_id: uuid.UUID | None,
) -> AdvanceResult:
    status = effective_status(insp)
    if status != "running" or not holds_lease(insp, session_id):
        if status in ("running", "interrupted") and not holds_lease(insp, session_id):
            raise InspectionError(409, "this browser does not hold the driver lease: press resume", lease_lost=True)
        raise InspectionError(409, f"inspection is {status}")
    insp.driver_expires_at = now() + timedelta(seconds=LEASE_SECONDS)
    runner = runner_for(db, insp)
    store_captures(db, insp, runner, captures)
    events = runner.advance(until_frame)
    result = append_events(db, insp.id, events, checkpoint_frame=runner.checkpoint)
    _give_back_after_commit(db, insp, runner)
    return AdvanceResult(insp.checkpoint_frame, result.last_seq, result.written)


# ------------------------------------------------------------------------------------------ decisions
def decide(
    db: Session,
    insp: Inspection,
    defect_no: str | None,
    decision: dict[str, Any],
    actor: User,
    idem: str,
    ip: str | None,
) -> str:
    if insp.finalized_at is not None:
        raise InspectionError(409, "the verdict is already computed; defects can no longer change")
    if insp.status not in (*OPEN, "completed"):
        raise InspectionError(409, f"inspection is {insp.status}")
    runner = runner_for(db, insp)
    try:
        events = runner.decide(defect_no, decision, _cmd_key(insp, idem))
    except DecisionError as exc:
        raise InspectionError(409, str(exc)) from exc
    except KeyError as exc:
        raise InspectionError(404, "defect not found") from exc
    target = next((e.payload["defect"]["defect_no"] for e in events if e.payload.get("decision")), defect_no)
    append_events(db, insp.id, events, actor_kind="user", actor_user_id=actor.id)
    audit.record(
        db,
        action=f"defect.{decision['action']}",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="defect",
        entity_id=f"{insp.id}/{target}",
        after={k: v for k, v in decision.items() if k != "frame"},
        ip=ip,
    )
    _give_back_after_commit(db, insp, runner)
    assert target is not None
    return target


# ------------------------------------------------------------------------------------------ verdict
def finalize(db: Session, insp: Inspection, actor: User, idem: str, ip: str | None) -> None:
    if insp.finalized_at is not None:
        return
    if insp.status != "completed":
        raise InspectionError(409, "finish the roll first")
    runner = runner_for(db, insp)
    counts = runner.counts()
    if counts["pending"]:
        raise InspectionError(409, f"{counts['pending']} defect(s) still need a decision", pending=counts["pending"])
    score = runner.score(final=True)
    if score is None:
        raise InspectionError(409, "nothing was inspected")
    p = runner.profile
    insp.system_verdict = score.verdict
    insp.points_total = score.total_points
    insp.points_per_100 = round(score.per_100, p.per100_rounding)
    insp.yards_inspected = round(runner.yards_inspected, 3)
    insp.finalized_at = now()
    roll = db.get(Roll, insp.roll_id)
    if roll:
        roll.status = "inspected"
    payload = {
        "system_verdict": score.verdict,
        "points_total": score.total_points,
        "per_100": insp.points_per_100,
        "threshold": p.threshold_per_100,
        "borderline_below": p.borderline.below,
        "borderline_above": p.borderline.above,
        "cells": {str(k): v for k, v in score.cells.items()},
        "uncapped_cells": {str(k): v for k, v in score.uncapped_cells.items()},
        "explanation": score.explanation,
        "needs_decision": score.verdict == "BORDERLINE",
        **counts,
    }
    key = _cmd_key(insp, idem)
    append_events(
        db,
        insp.id,
        [RunnerEvent("verdict.computed", payload, key("verdict.computed", ""))],
        actor_kind="user",
        actor_user_id=actor.id,
    )
    _audit(db, "inspection.finalize", insp, actor, ip, verdict=score.verdict, points=score.total_points)
    _give_back_after_commit(db, insp, runner)


def decide_verdict(
    db: Session, insp: Inspection, final_verdict: str, reason: str, actor: User, idem: str, ip: str | None
) -> None:
    if insp.finalized_at is None:
        raise InspectionError(409, "compute the verdict first")
    override = (insp.system_verdict == "PASS" and final_verdict == "REJECT") or (
        insp.system_verdict == "FAIL" and final_verdict == "ACCEPT"
    )
    before = {"final_verdict": insp.final_verdict}
    insp.final_verdict = final_verdict
    insp.decision_by = actor.id
    insp.decision_reason = reason
    insp.decision_at = now()
    key = _cmd_key(insp, idem)
    payload = {
        "final_verdict": final_verdict,
        "system_verdict": insp.system_verdict,
        "override": override,
        "reason": reason,
        "by": actor.display_name,
    }
    append_events(
        db,
        insp.id,
        [RunnerEvent("verdict.decided", payload, key("verdict.decided", ""))],
        actor_kind="user",
        actor_user_id=actor.id,
    )
    audit.record(
        db,
        action="inspection.decision",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="inspection",
        entity_id=str(insp.id),
        before=before,
        after=payload,
        ip=ip,
    )


# ------------------------------------------------------------------------------------------ queries
def latest_score(db: Session, insp: Inspection) -> dict[str, Any] | None:
    row = db.scalar(
        select(InspectionEvent.payload)
        .where(InspectionEvent.inspection_id == insp.id, InspectionEvent.type == "score.updated")
        .order_by(InspectionEvent.seq.desc())
        .limit(1)
    )
    return dict(row) if row else None


def defects(db: Session, insp: Inspection) -> list[DefectRow]:
    return list(
        db.scalars(
            select(DefectRow)
            .where(DefectRow.inspection_id == insp.id)
            .order_by(DefectRow.center_yd, DefectRow.defect_no)
        )
    )


def captured_frames(db: Session, insp: Inspection) -> list[InspectionFrame]:
    return list(
        db.scalars(
            select(InspectionFrame)
            .where(InspectionFrame.inspection_id == insp.id, InspectionFrame.image_key.is_not(None))
            .order_by(InspectionFrame.frame)
        )
    )


def events_page(db: Session, insp: Inspection, after_seq: int, limit: int) -> list[InspectionEvent]:
    return events_after(db, insp.id, after_seq, limit)


def _give_back_after_commit(db: Session, insp: Inspection, runner: Runner) -> None:
    """Put the runner back in the cache once (and only if) the transaction commits."""

    def _after_commit(_: Session) -> None:
        event.remove(db, "after_rollback", _after_rollback)
        _give_back(insp, runner)

    def _after_rollback(_: Session) -> None:
        event.remove(db, "after_commit", _after_commit)

    event.listen(db, "after_commit", _after_commit, once=True)
    event.listen(db, "after_rollback", _after_rollback, once=True)
