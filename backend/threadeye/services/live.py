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
import hashlib
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from threadeye.core.frames import FrameImage
from threadeye.core.providers import ProviderContext, ProviderNotConfigured
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
from threadeye.providers.prefetch import PrefetchingDetector
from threadeye.providers.registry import REGISTRY, create_provider
from threadeye.providers.simulated import PRESETS
from threadeye.services import datasets, storage
from threadeye.services.inspection_store import append_events, events_after
from threadeye.services.provider_config import current_provider
from threadeye.settings import get_settings

LEASE_SECONDS = 30
MIN_STEP_FRAMES = 3
"""A request to a detector still working through the frames waits for at least this many (about 1 s)."""
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


def roll_spec(insp: Inspection, roll: Roll, info: datasets.DatasetInfo, profile: RuleProfile) -> RollSpec:
    """Apply the buyer's width basis. A simulated source supplies the reference length unless measured."""
    width = roll.declared_width_in
    if profile.width_basis in {"measured", "cuttable"}:
        width = insp.measured_width_in or width
    if profile.width_basis == "cuttable" and profile.selvage_exclusion.enabled:
        width -= 2 * profile.selvage_exclusion.distance_in
    if width <= 0:
        raise InspectionError(422, "cuttable width must remain positive after excluding the selvage")
    return RollSpec(
        width_in=width,
        declared_length_yd=insp.measured_length_yd or info.roll_length_yd,
    )


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
    # A detector that looks at the picture gets the roll video decoded here; the simulated one only
    # needs the positions (its answers come from the answer key).
    source = datasets.video_source(info) if snap["info"].get("requires_image") else datasets.track_source(info)
    profile = RuleProfile(**profile_row.rules)
    try:
        runner = Runner(
            source,
            provider,
            profile,
            roll_spec(insp, roll, info, profile),
            inspection_id=str(insp.id),
        )
    except ProviderNotConfigured as exc:
        # An inspection keeps the detector it started with (the model file is pinned by its SHA-256): after
        # a new model is installed, an inspection left open on the old one cannot go on.
        raise InspectionError(
            409, f"this inspection's detector is not available any more ({exc}); abort it and inspect the roll again"
        ) from exc
    if snap["info"].get("requires_image"):
        # The model works through the coming frames in the background, so a request waits on the database
        # only (PrefetchingDetector); the detections are the same.
        runner.provider = PrefetchingDetector(provider, lambda: datasets.video_source(info), runner.plan.frames)
    return runner


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


def _local_model_config() -> dict[str, Any]:
    """The trained detector in THREADEYE_MODEL_DIR, pinned by the SHA-256 of its ONNX file."""
    root = Path(get_settings().model_dir) if get_settings().model_dir else None
    models = sorted(root.glob("threadeye_*.onnx")) if root and root.is_dir() else []
    if not models:
        raise InspectionError(
            409, "no trained model installed: set THREADEYE_MODEL_DIR to the folder with threadeye_s.onnx"
        )
    model = models[0]
    return {"model_path": str(model), "info_path": str(model.with_name("model_info.json")), "sha256": _sha256(model)}


@lru_cache(maxsize=4)
def _sha256_cached(path: str, mtime: float, size: int) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path: Path) -> str:
    st = path.stat()
    return _sha256_cached(str(path), st.st_mtime, st.st_size)


def model_outdated(insp: Inspection) -> bool:
    """An open inspection pinned to a trained model that is no longer the installed one: it cannot go on
    (build_runner refuses it), only be aborted and the roll inspected again on the new model."""
    snap = insp.provider_snapshot or {}
    if insp.status not in OPEN or snap.get("provider_id") != "local_model":
        return False
    try:
        return bool(_local_model_config()["sha256"] != (snap.get("config") or {}).get("sha256"))
    except InspectionError:
        return True


def provider_snapshot(preset: str, db: Session | None = None) -> dict[str, Any]:
    """The detector pinned on a new inspection: the trained model when THREADEYE_DETECTOR_PROVIDER is
    local_model, otherwise the simulated detector with the given imperfection preset."""
    if (current_provider(db) if db is not None else get_settings().detector_provider) == "local_model":
        config = _local_model_config()
        spec = REGISTRY["local_model"]
        try:
            info = create_provider("local_model", config).info
        except ProviderNotConfigured as exc:
            raise InspectionError(409, str(exc)) from exc
        preset_out: str | None = None
    else:
        if preset not in PRESETS:
            raise InspectionError(422, f"unknown simulated preset {preset!r}")
        config = dict(PRESETS[preset])
        spec = REGISTRY["simulated"]
        info = create_provider("simulated", config).info
        preset_out = preset
    return {
        "provider_id": spec.provider_id,
        "preset": preset_out,
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
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise InspectionError(404, "machine not found")
    if not machine.active:
        raise InspectionError(409, "machine is disabled")
    try:
        info = datasets.get_dataset(dataset_id)
    except datasets.DatasetNotFound as exc:
        raise InspectionError(422, f"no simulated roll called {dataset_id!r}") from exc
    open_insp = db.scalar(select(Inspection).where(Inspection.roll_id == roll.id, Inspection.status.in_(OPEN)))
    if open_insp is not None:
        raise InspectionError(409, "this roll already has an open inspection", inspection_id=str(open_insp.id))
    lot = db.get(Lot, roll.lot_id)
    assert lot
    if lot.status == "archived":
        raise InspectionError(409, "this sample delivery is archived; register a new delivery")
    snapshot = provider_snapshot(preset or get_settings().simulated_preset, db)
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
    db: Session,
    insp: Inspection,
    actor: User,
    session_id: uuid.UUID | None,
    idem: str,
    *,
    takeover: bool = False,
    runner: Runner | None = None,
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
    runner = runner or runner_for(db, insp)
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
    append_events(db, insp.id, events, actor_kind="user", actor_user_id=actor.id, locked=insp)
    _give_back_after_commit(db, insp, runner)
    return events


def pause(db: Session, insp: Inspection, actor: User, idem: str) -> None:
    if effective_status(insp) not in ("running", "interrupted"):
        raise InspectionError(409, f"inspection is {insp.status}")
    insp.status = "paused"
    key = _cmd_key(insp, idem)
    ev = RunnerEvent("session.paused", {"checkpoint_frame": insp.checkpoint_frame}, key("session.paused", ""))
    append_events(db, insp.id, [ev], actor_kind="user", actor_user_id=actor.id, locked=insp)


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
        locked=insp,
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
    append_events(db, insp.id, [ev], actor_kind="user", actor_user_id=actor.id, locked=insp)
    _audit(db, "inspection.abort", insp, actor, ip, checkpoint_frame=insp.checkpoint_frame)


# ------------------------------------------------------------------------------------------ advance
@dataclass(frozen=True)
class CaptureIn:
    frame: int
    jpeg_b64: str
    width: int
    height: int


Photo = tuple[int, bytes, int, int]
"""An evidence photo: frame, JPEG, width, height."""


EVIDENCE_MAX_W = 1920
"""Width of the evidence photo the server keeps of a frame its detector found something on (a 3840-px
line-scan strip is halved: tiny defects stay a few pixels wide, the upload stays small)."""


def _decode_capture(c: CaptureIn) -> Photo:
    try:
        raw = base64.b64decode(c.jpeg_b64, validate=True)
        jpeg, w, h = storage.clean_jpeg(raw)
    except (binascii.Error, storage.StorageError) as exc:
        raise InspectionError(422, f"capture of frame {c.frame}: {exc}") from exc
    return c.frame, jpeg, w, h


def _evidence_photo(frame: int, image: FrameImage) -> Photo:
    """The server's own picture of a frame (the view region it decoded), at most EVIDENCE_MAX_W wide."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(image.jpeg)) as src:
        pic = src.convert("RGB")
    if pic.width > EVIDENCE_MAX_W:
        size = (EVIDENCE_MAX_W, max(1, round(pic.height * EVIDENCE_MAX_W / pic.width)))
        pic = pic.resize(size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    pic.save(out, "JPEG", quality=80)
    return frame, out.getvalue(), pic.width, pic.height


def store_frame_photos(db: Session, insp: Inspection, runner: Runner, photos: Sequence[Photo]) -> int:
    """Evidence photos (frame, JPEG, width, height) of the camera view, all in one statement per table: each
    round trip to a remote database costs (0.5 s to Supabase from Dhaka; one per photo made a request of five
    photos 3 s slower, 2026-10-26). Of two photos of a frame the larger one stays."""
    view_w = runner.calibration.view_region[2]
    best: dict[int, Photo] = {}
    for photo in photos:
        if not 0 <= photo[0] < len(runner.track):
            raise InspectionError(422, f"frame {photo[0]} is outside this roll")
        if photo[0] not in best or photo[2] >= best[photo[0]][2]:
            best[photo[0]] = photo
    if not best:
        return 0
    keys = [f"inspections/{insp.id}/frames/{f:06d}.jpg" for f in best]
    shas = storage.put_many(db, [(k, jpeg) for k, (_, jpeg, _, _) in zip(keys, best.values(), strict=True)])
    rows = []
    for key, sha, (f, _, w, h) in zip(keys, shas, best.values(), strict=True):
        pos = runner.track[f]
        rows.append(
            {
                "inspection_id": insp.id,
                "frame": f,
                "top_yd": pos.top_yd,
                "bottom_yd": pos.bottom_yd,
                "hand_visible": bool(pos.hand_visible),
                "sample_reason": "capture",
                "image_key": key,
                "image_sha256": sha,
                "width": w,
                "height": h,
                "image_scale": w / view_w,
                "captured_at": now(),
            }
        )
    stmt = pg_insert(InspectionFrame).values(rows)
    image = {k: stmt.excluded[k] for k in ("image_key", "image_sha256", "width", "height", "image_scale")}
    image["captured_at"] = stmt.excluded.captured_at
    # A smaller photo (the browser's 960-px capture) never replaces a larger one (the server's) of the frame.
    keep_larger = InspectionFrame.image_scale.is_(None) | (stmt.excluded.image_scale >= InspectionFrame.image_scale)
    db.execute(
        stmt.on_conflict_do_update(constraint="uq_inspection_frames_inspection_id_frame", set_=image, where=keep_larger)
    )
    return len(rows)


def store_captures(db: Session, insp: Inspection, runner: Runner, captures: Sequence[CaptureIn]) -> int:
    """Evidence images captured by the browser (the view region of the frames it sampled)."""
    return store_frame_photos(db, insp, runner, [_decode_capture(c) for c in captures])


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
    runner: Runner | None = None,
    wait_for_detector: bool = False,
) -> AdvanceResult:
    """``wait_for_detector``: process every frame up to ``until_frame`` even where the detector is still
    working (the request that starts the video: it gives the model its head start)."""
    status = effective_status(insp)
    if status != "running" or not holds_lease(insp, session_id):
        if status in ("running", "interrupted") and not holds_lease(insp, session_id):
            raise InspectionError(409, "this browser does not hold the driver lease: press resume", lease_lost=True)
        raise InspectionError(409, f"inspection is {status}")
    insp.driver_expires_at = now() + timedelta(seconds=LEASE_SECONDS)
    runner = runner or runner_for(db, insp)
    photos = [_decode_capture(c) for c in captures]
    if isinstance(runner.provider, PrefetchingDetector) and not wait_for_detector:
        # Hand back what the model has finished instead of waiting for the rest: the next request takes it.
        until_frame = min(until_frame, max(runner.provider.ready_until, runner.checkpoint + MIN_STEP_FRAMES))
    events = runner.advance(until_frame)
    # The frames the detector found something on: their photo goes with the detection, so a defect card has
    # its picture at once (the browser's capture comes only when the video reaches the frame).
    photos += [_evidence_photo(f, image) for f, image in runner.take_evidence().items()]
    store_frame_photos(db, insp, runner, photos)
    result = append_events(db, insp.id, events, checkpoint_frame=runner.checkpoint, locked=insp)
    _give_back_after_commit(db, insp, runner)
    return AdvanceResult(insp.checkpoint_frame, result.last_seq, result.written)


# ------------------------------------------------------------------------------------------ decisions
def _check_decidable(insp: Inspection) -> None:
    if insp.finalized_at is not None:
        raise InspectionError(409, "the verdict is already computed; defects can no longer change")
    if insp.status not in (*OPEN, "completed"):
        raise InspectionError(409, f"inspection is {insp.status}")


def decide(
    db: Session,
    insp: Inspection,
    defect_no: str | None,
    decision: dict[str, Any],
    actor: User,
    idem: str,
    ip: str | None,
    captures: Sequence[CaptureIn] = (),
) -> str:
    """One inspector decision. ``captures``: a photo of the frame a missed defect was drawn on."""
    _check_decidable(insp)
    runner = runner_for(db, insp)
    store_captures(db, insp, runner, captures)
    try:
        events = runner.decide(defect_no, decision, _cmd_key(insp, idem))
    except DecisionError as exc:
        raise InspectionError(409, str(exc)) from exc
    except KeyError as exc:
        raise InspectionError(404, "defect not found") from exc
    target = next((e.payload["defect"]["defect_no"] for e in events if e.payload.get("decision")), defect_no)
    append_events(db, insp.id, events, actor_kind="user", actor_user_id=actor.id, locked=insp)
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


def confirm_pending(
    db: Session,
    insp: Inspection,
    up_to_yd: float | None,
    note: str | None,
    actor: User,
    idem: str,
    ip: str | None,
) -> list[str]:
    """Confirm every defect still pending (up to ``up_to_yd``) in one step.

    The inspector rejects the false alarms they see and accepts the rest at once. Each defect gets its
    own event (with ``bulk: true`` in the decision) and the change ledger gets one entry listing them.
    """
    _check_decidable(insp)
    runner = runner_for(db, insp)
    numbers = runner.pending_defects(up_to_yd)
    if not numbers:
        _give_back(insp, runner)
        return []
    decision: dict[str, Any] = {"action": "confirm", "bulk": True, "note": note}
    try:
        events = runner.decide_many(numbers, decision, _cmd_key(insp, idem))
    except DecisionError as exc:
        raise InspectionError(409, str(exc)) from exc
    append_events(db, insp.id, events, actor_kind="user", actor_user_id=actor.id, locked=insp)
    audit.record(
        db,
        action="defect.confirm_bulk",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="inspection",
        entity_id=str(insp.id),
        after={"defects": numbers, "up_to_yd": up_to_yd, "note": note},
        ip=ip,
    )
    _give_back_after_commit(db, insp, runner)
    return numbers


# ------------------------------------------------------------------------------------------ verdict
def finalize(db: Session, insp: Inspection, actor: User, idem: str, ip: str | None) -> None:
    if insp.finalized_at is not None:
        return
    if insp.status != "completed":
        raise InspectionError(409, "finish the roll first")
    runner = runner_for(db, insp)
    if runner.profile.width_basis == "measured" and insp.measured_width_in is None:
        raise InspectionError(409, "this buyer profile requires a measured width before finalization")
    counts = runner.counts()
    # Pending defects block the verdict only while they could still change it (PASS/BORDERLINE/FAIL
    # is the same whether they are all rejected or all confirmed): the rest are recorded as not
    # reviewed, never silently accepted.
    if counts["pending"] and not runner.verdict_settled():
        raise InspectionError(
            409,
            f"{counts['pending']} defect(s) still need a decision: they could change the verdict",
            pending=counts["pending"],
        )
    score = runner.score(final=True)
    upper = runner.score(final=False)
    if score is None or upper is None:
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
        "unreviewed": counts["pending"],
        "points_if_all_confirmed": upper.total_points,
        "per_100_if_all_confirmed": round(upper.per_100, p.per100_rounding),
        **counts,
    }
    key = _cmd_key(insp, idem)
    append_events(
        db,
        insp.id,
        [RunnerEvent("verdict.computed", payload, key("verdict.computed", ""))],
        actor_kind="user",
        actor_user_id=actor.id,
        locked=insp,
    )
    _audit(
        db,
        "inspection.finalize",
        insp,
        actor,
        ip,
        verdict=score.verdict,
        points=score.total_points,
        unreviewed=counts["pending"],
    )
    _give_back_after_commit(db, insp, runner)


def decide_verdict(
    db: Session, insp: Inspection, final_verdict: str, reason: str, actor: User, idem: str, ip: str | None
) -> None:
    if insp.finalized_at is None:
        raise InspectionError(409, "compute the verdict first")
    if insp.final_verdict is not None:
        # Inspection rows are locked by the caller. Exact retries are harmless;
        # a second decision must never overwrite the signed decision or its reason.
        if insp.final_verdict == final_verdict and insp.decision_reason == reason and insp.decision_by == actor.id:
            return
        raise InspectionError(409, "the supervisor decision is already recorded and cannot be changed")
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
        locked=insp,
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
