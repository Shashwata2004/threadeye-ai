"""Inspection lifecycle, the browser-clocked advance loop, events (poll + SSE), defects, verdict (M2).

PLAN.md §5, §6. Business rules live in ``threadeye.services.live``; this module maps HTTP to them.
Every command takes a row lock on the inspection and commits once.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from threadeye.api.deps import client_ip, current_session_id, idempotency_key, require
from threadeye.api.errors import NOT_IMPLEMENTED_RESPONSE, not_implemented
from threadeye.api.schemas.events import Actor, EventEnvelope, EventsPage
from threadeye.api.schemas.inspection import (
    AdvanceIn,
    AdvanceOut,
    ConfirmIn,
    DatasetOut,
    DecisionIn,
    DefectOut,
    InspectionCreate,
    InspectionListItem,
    InspectionSnapshot,
    LengthIn,
    ManualDefectIn,
    MeasurementIn,
    PromoteIn,
    ProviderInfoOut,
    ReclassifyIn,
    RejectIn,
    RollContext,
    SamplingPlanOut,
    ScoreSummary,
    TrackOut,
)
from threadeye.db.models import (
    Buyer,
    DefectRow,
    Inspection,
    InspectionEvent,
    Lot,
    Roll,
    RuleProfileRow,
    Supplier,
    User,
)
from threadeye.db.session import get_db, get_sessionmaker
from threadeye.reports.roll_report import build_roll_report
from threadeye.security.rbac import Perm
from threadeye.services import datasets, evidence, live, storage
from threadeye.services.inspection_store import events_after

router = APIRouter(tags=["inspections"])
defects_router = APIRouter(tags=["defects"])
datasets_router = APIRouter(tags=["datasets"])

READ = [Depends(require(Perm.INSPECTIONS_READ))]
IDEMPOTENCY_NOTE = "Send an `Idempotency-Key` header (UUID); retries with the same key are no-ops."
SSE_SECONDS = 300
PDF: dict[int | str, dict[str, Any]] = {200: {"content": {"application/pdf": {}}, "description": "PDF document"}}
JPEG: dict[int | str, dict[str, Any]] = {200: {"content": {"image/jpeg": {}}, "description": "JPEG image"}}


def _http(exc: live.InspectionError) -> HTTPException:
    detail: Any = {"message": str(exc), **exc.extra} if exc.extra else str(exc)
    return HTTPException(exc.status, detail)


def _get(db: Session, inspection_id: uuid.UUID) -> Inspection:
    insp = db.get(Inspection, inspection_id)
    if insp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "inspection not found")
    return insp


def _locked(db: Session, inspection_id: uuid.UUID) -> Inspection:
    try:
        return live.lock(db, inspection_id)
    except live.InspectionError as exc:
        raise _http(exc) from exc


def _dataset(insp: Inspection) -> datasets.DatasetInfo | None:
    try:
        return datasets.get_dataset(insp.dataset_id) if insp.dataset_id else None
    except datasets.DatasetNotFound:
        return None


VIDEO_CHUNK = 3 * 1024 * 1024
"""Largest piece of a video in one response: serverless hosts cap a response at 4.5 MB."""


def _video(db: Session, info: datasets.DatasetInfo) -> tuple[str | None, str | None]:
    """URL and type of a roll's video: a file next to the roll's CSVs, or (cloud) a file in Supabase."""
    url = f"/api/v1/datasets/{info.id}/video"
    if info.video_file:
        return url, info.video_type
    if storage.blob_size(db, storage.video_key(info.id)):
        return url, "video/mp4"
    return None, None


# ------------------------------------------------------------------------------------------ views
def _snapshot(db: Session, insp: Inspection, session_id: uuid.UUID | None) -> InspectionSnapshot:
    roll = db.get(Roll, insp.roll_id)
    assert roll
    lot = db.get(Lot, roll.lot_id)
    assert lot
    supplier, buyer = db.get(Supplier, lot.supplier_id), db.get(Buyer, lot.buyer_id)
    profile = db.get(RuleProfileRow, insp.rule_profile_id)
    inspector = db.get(User, insp.inspector_id) if insp.inspector_id else None
    decider = db.get(User, insp.decision_by) if insp.decision_by else None
    info = _dataset(insp)
    track = datasets.track_source(info).track() if info else []
    cp = insp.checkpoint_frame
    score = live.latest_score(db, insp)
    status_now = live.effective_status(insp)
    holds = live.holds_lease(insp, session_id)
    snap = insp.provider_snapshot
    return InspectionSnapshot(
        id=insp.id,
        roll_id=insp.roll_id,
        roll_code=roll.roll_code,
        machine_id=insp.machine_id,
        status=status_now,
        mode=insp.mode,
        is_simulated=insp.is_simulated,
        clock=insp.clock,
        provider=ProviderInfoOut(**snap["info"], preset=snap.get("preset")),
        rule_profile_id=insp.rule_profile_id,
        checkpoint_frame=cp,
        checkpoint_yd=round(track[cp].bottom_yd, 3) if 0 <= cp < len(track) else 0.0,
        last_seq=insp.last_seq,
        driver_session=holds,
        lease_held_elsewhere=status_now == "running" and not holds,
        score=ScoreSummary(**score) if score else None,
        system_verdict=insp.system_verdict,
        final_verdict=insp.final_verdict,
        started_at=insp.started_at,
        completed_at=insp.completed_at,
        finalized_at=insp.finalized_at,
        points_total=insp.points_total,
        points_per_100=insp.points_per_100,
        yards_inspected=insp.yards_inspected,
        decision_reason=insp.decision_reason,
        decision_by=decider.display_name if decider else None,
        decision_at=insp.decision_at,
        inspector=inspector.display_name if inspector else None,
        dataset_id=insp.dataset_id,
        frame_count=len(track),
        roll=RollContext(
            roll_code=roll.roll_code,
            mill_roll_no=roll.mill_roll_no,
            declared_length_yd=roll.declared_length_yd,
            declared_width_in=roll.declared_width_in,
            lot_id=lot.id,
            challan_no=lot.challan_no,
            supplier=supplier.name if supplier else "",
            buyer=buyer.name if buyer else "",
            fabric_type=lot.fabric_type,
            rule_profile=f"{profile.name} v{profile.version}" if profile else "",
            threshold_per_100=float(profile.rules.get("threshold_per_100", 40.0)) if profile else 40.0,
        ),
    )


def _defect_out(d: DefectRow, crop: bool) -> DefectOut:
    return DefectOut(
        id=d.id,
        inspection_id=d.inspection_id,
        defect_no=d.defect_no,
        origin=d.origin,
        predicted_cls=d.predicted_cls,
        current_cls=d.current_cls,
        kind=d.kind,
        nondefect_category=d.nondefect_category,
        status=d.status,
        reject_reason=d.reject_reason,
        uncertain=d.uncertain,
        start_yd=d.start_yd,
        end_yd=d.end_yd,
        center_yd=d.center_yd,
        across_start_cm=d.across_start_cm,
        across_end_cm=d.across_end_cm,
        length_in=d.length_in,
        length_source=d.length_source,
        is_continuous=d.is_continuous,
        is_running=d.is_running,
        sightings=d.sightings,
        first_frame=d.first_frame,
        last_frame=d.last_frame,
        best_frame=d.best_frame,
        points=d.points,
        points_reason=d.points_reason,
        excluded_reason=d.excluded_reason,
        explanation=d.explanation,
        provider_label=d.provider,
        crop_url=f"/api/v1/defects/{d.id}/crop" if crop else None,
        decided_at=d.decided_at,
    )


def _defects_out(db: Session, insp: Inspection, rows: list[DefectRow]) -> list[DefectOut]:
    info = _dataset(insp)
    frames = live.captured_frames(db, insp)
    if info is None or not frames:
        return [_defect_out(d, False) for d in rows]
    source = datasets.track_source(info)
    track, calib = source.track(), source.calibration
    return [_defect_out(d, evidence.best_capture(d, frames, track, calib) is not None) for d in rows]


def _envelope(insp: Inspection, ev: InspectionEvent) -> EventEnvelope:
    snap = insp.provider_snapshot["info"]
    return EventEnvelope(
        inspection_id=insp.id,
        seq=ev.seq,
        type=ev.type,
        at=ev.occurred_at,
        actor=Actor(kind=ev.actor_kind, user_id=ev.actor_user_id),
        simulated=insp.is_simulated,
        provider=f"{snap['provider_id']}@{snap['version']}",
        payload=ev.payload,
    )


# ------------------------------------------------------------------------------------------ datasets
@datasets_router.get("/datasets", response_model=list[DatasetOut], dependencies=READ)
def list_datasets(db: Session = Depends(get_db)) -> list[DatasetOut]:
    out = []
    for d in datasets.list_datasets():
        url, _ = _video(db, d)
        out.append(
            DatasetOut(
                id=d.id,
                roll_length_yd=d.roll_length_yd,
                fabric_width_in=d.fabric_width_in,
                frames=d.frames,
                fps=d.fps,
                mode=d.mode,
                note=d.note,
                has_video=url is not None,
                video_url=url,
                is_simulated=d.is_simulated,
            )
        )
    return out


@datasets_router.get(
    "/datasets/{dataset_id}/video",
    response_class=Response,
    dependencies=READ,
    responses={
        200: {"content": {"video/webm": {}, "video/mp4": {}}, "description": "Roll video"},
        206: {"description": "Part of the roll video (Range requests)"},
    },
    description="The roll video. Range requests are supported; from Supabase it comes in pieces of at most 3 MB.",
)
def dataset_video(
    dataset_id: str, range_header: str | None = Header(None, alias="Range"), db: Session = Depends(get_db)
) -> Response:
    try:
        info = datasets.get_dataset(dataset_id)
    except datasets.DatasetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such roll") from exc
    cache = {"Cache-Control": "private, max-age=3600"}
    if info.video_path is not None:
        return FileResponse(info.video_path, media_type=info.video_type, headers=cache)
    key = storage.video_key(info.id)
    total = storage.blob_size(db, key)
    if not total:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this roll has no video")
    start, end = 0, total - 1
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", (range_header or "").strip())
    if m and m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else total - 1
    elif m and m.group(2):  # the last N bytes
        start = max(0, total - int(m.group(2)))
    if start >= total:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
    end = min(end, total - 1, start + VIDEO_CHUNK - 1)
    data = storage.read_range(db, key, start, end - start + 1)
    return Response(
        data,
        status_code=206,
        media_type="video/mp4",
        headers={**cache, "Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{total}"},
    )


# ------------------------------------------------------------------------------------------ lifecycle
@router.get("/inspections", response_model=list[InspectionListItem], dependencies=READ)
def list_inspections(
    roll_id: uuid.UUID | None = None,
    open_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[InspectionListItem]:
    q = select(Inspection, Roll.roll_code).join(Roll, Roll.id == Inspection.roll_id)
    if roll_id:
        q = q.where(Inspection.roll_id == roll_id)
    if open_only:
        q = q.where(Inspection.status.in_(live.OPEN))
    rows = db.execute(q.order_by(Inspection.created_at.desc()).limit(limit)).all()
    names = {u.id: u.display_name for u in db.scalars(select(User))}
    return [
        InspectionListItem(
            id=i.id,
            roll_id=i.roll_id,
            roll_code=code,
            status=live.effective_status(i),
            system_verdict=i.system_verdict,
            final_verdict=i.final_verdict,
            points_per_100=i.points_per_100,
            checkpoint_frame=i.checkpoint_frame,
            started_at=i.started_at,
            finalized_at=i.finalized_at,
            created_at=i.created_at,
            inspector=names.get(i.inspector_id) if i.inspector_id else None,
            is_simulated=i.is_simulated,
        )
        for i, code in rows
    ]


@router.post(
    "/inspections",
    response_model=InspectionSnapshot,
    status_code=status.HTTP_201_CREATED,
    description="Load a roll on a machine. 409 (with `inspection_id`) if the roll already has an open inspection.",
)
def create_inspection(
    body: InspectionCreate,
    request: Request,
    actor: User = Depends(require(Perm.INSPECTIONS_RUN)),
    session_id: uuid.UUID | None = Depends(current_session_id),
    db: Session = Depends(get_db),
) -> InspectionSnapshot:
    try:
        insp = live.create(
            db,
            roll_code=body.roll_code,
            machine_id=body.machine_id,
            dataset_id=body.source.dataset_id,
            preset=body.preset,
            actor=actor,
            ip=client_ip(request),
        )
    except live.InspectionError as exc:
        db.rollback()
        raise _http(exc) from exc
    db.commit()
    return _snapshot(db, insp, session_id)


@router.get("/inspections/{inspection_id}", response_model=InspectionSnapshot, dependencies=READ)
def get_inspection(
    inspection_id: uuid.UUID,
    session_id: uuid.UUID | None = Depends(current_session_id),
    db: Session = Depends(get_db),
) -> InspectionSnapshot:
    return _snapshot(db, _get(db, inspection_id), session_id)


def _command(action: str) -> None:
    @router.post(
        f"/inspections/{{inspection_id}}/{action}",
        response_model=InspectionSnapshot,
        operation_id=f"inspection_{action}",
        description=f"{action.capitalize()} the inspection. {IDEMPOTENCY_NOTE}",
    )
    def endpoint(
        inspection_id: uuid.UUID,
        request: Request,
        takeover: bool = Query(False, description="start/resume: take the lease from another device"),
        actor: User = Depends(require(Perm.INSPECTIONS_RUN)),
        session_id: uuid.UUID | None = Depends(current_session_id),
        idem: str = Depends(idempotency_key),
        db: Session = Depends(get_db),
    ) -> InspectionSnapshot:
        insp = _locked(db, inspection_id)
        ip = client_ip(request)
        try:
            if action in ("start", "resume"):
                live.start(db, insp, actor, session_id, idem, takeover=takeover)
            elif action == "pause":
                live.pause(db, insp, actor, idem)
            elif action == "complete":
                live.complete(db, insp, actor, idem, ip)
            elif action == "abort":
                live.abort(db, insp, actor, idem, ip)
        except live.InspectionError as exc:
            db.rollback()
            raise _http(exc) from exc
        db.commit()
        return _snapshot(db, insp, session_id)


for _action in ("start", "pause", "resume", "complete", "abort"):
    _command(_action)


@router.get("/inspections/{inspection_id}/plan", response_model=SamplingPlanOut, dependencies=READ)
def sampling_plan(inspection_id: uuid.UUID, db: Session = Depends(get_db)) -> SamplingPlanOut:
    insp = _get(db, inspection_id)
    try:
        runner = live.read_runner(db, insp)
    except live.InspectionError as exc:
        raise _http(exc) from exc
    p = runner.plan
    return SamplingPlanOut(
        inspection_id=insp.id,
        overlap=p.config.overlap,
        view_length_px=p.view_height_px,
        step_px=p.step_px,
        frames=[s.frame for s in p.samples],
    )


@router.get("/inspections/{inspection_id}/track", response_model=TrackOut, dependencies=READ)
def frame_track(inspection_id: uuid.UUID, db: Session = Depends(get_db)) -> TrackOut:
    insp = _get(db, inspection_id)
    info = _dataset(insp)
    if info is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the inspection's roll video is not available on this server")
    source = datasets.track_source(info)
    track, calib = source.track(), source.calibration
    video_url, video_type = _video(db, info)
    return TrackOut(
        dataset_id=info.id,
        fps=info.fps,
        frame_count=len(track),
        px_per_cm=calib.px_per_cm,
        view_region=calib.view_region,
        fabric_width_cm=calib.fabric_width_cm,
        selvage_band_px=calib.selvage_band_px,
        roll_length_yd=info.roll_length_yd,
        video_url=video_url,
        video_type=video_type,
        roll_y_top_px=[p.roll_y_top_px for p in track],
        top_yd=[p.top_yd for p in track],
        bottom_yd=[p.bottom_yd for p in track],
        speed_m_min=[p.speed_m_min or 0.0 for p in track],
        state=[p.state for p in track],
        fabric_x0_px=[p.fabric_x0_px or 0.0 for p in track],
        hand_visible=[bool(p.hand_visible) for p in track],
    )


@router.post(
    "/inspections/{inspection_id}/advance",
    response_model=AdvanceOut,
    description="Browser-clocked processing of frames (checkpoint, until_frame] in one transaction. "
    "Only the driver-lease holder may call it. Captures are evidence images of sampled frames. "
    "The response carries every event after `after_seq`.",
)
def advance(
    inspection_id: uuid.UUID,
    body: AdvanceIn,
    _: User = Depends(require(Perm.INSPECTIONS_RUN)),
    session_id: uuid.UUID | None = Depends(current_session_id),
    db: Session = Depends(get_db),
) -> AdvanceOut:
    insp = _locked(db, inspection_id)
    try:
        result = live.advance(
            db,
            insp,
            until_frame=body.until_frame,
            captures=[live.CaptureIn(c.frame, c.jpeg_b64, c.width, c.height) for c in body.captures],
            session_id=session_id,
        )
    except live.InspectionError as exc:
        db.rollback()
        raise _http(exc) from exc
    db.commit()
    events = events_after(db, insp.id, body.after_seq, 2000)
    return AdvanceOut(
        checkpoint_frame=result.checkpoint_frame,
        last_seq=result.last_seq,
        events=[_envelope(insp, e) for e in events],
        blocked_on_captures=[],
    )


# ------------------------------------------------------------------------------------------ events
@router.get("/inspections/{inspection_id}/events", response_model=EventsPage, dependencies=READ)
def list_events(
    inspection_id: uuid.UUID,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> EventsPage:
    insp = _get(db, inspection_id)
    rows = events_after(db, insp.id, after_seq, limit + 1)
    page = rows[:limit]
    return EventsPage(
        inspection_id=insp.id,
        events=[_envelope(insp, e) for e in page],
        last_seq=page[-1].seq if page else after_seq,
        has_more=len(rows) > limit,
    )


@router.get(
    "/inspections/{inspection_id}/stream",
    response_class=StreamingResponse,
    dependencies=READ,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE (edge profile)"}},
    description="Server-Sent Events. Resume with `Last-Event-ID` (= seq) or `?after_seq=`. "
    f"The stream closes after {SSE_SECONDS} s; EventSource reconnects by itself.",
)
def stream_events(
    inspection_id: uuid.UUID,
    after_seq: int = Query(0, ge=0),
    last_event_id: str | None = Header(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    insp = _get(db, inspection_id)
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after_seq
    db.close()

    def gen() -> Iterator[str]:
        seq, quiet = start, 0.0
        deadline = time.monotonic() + SSE_SECONDS
        yield "retry: 2000\n\n"
        while time.monotonic() < deadline:
            with get_sessionmaker()() as s:
                rows = events_after(s, insp.id, seq, 200)
                for e in rows:
                    data = _envelope(insp, e).model_dump_json()
                    yield f"id: {e.seq}\nevent: {e.type}\ndata: {data}\n\n"
                    seq = e.seq
            if rows:
                quiet = 0.0
                continue
            quiet += 0.5
            if quiet >= 15:
                yield ": heartbeat\n\n"
                quiet = 0.0
            time.sleep(0.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------------------------------ verdict
@router.get("/inspections/{inspection_id}/score", response_model=ScoreSummary, dependencies=READ)
def get_score(inspection_id: uuid.UUID, db: Session = Depends(get_db)) -> ScoreSummary:
    insp = _get(db, inspection_id)
    try:
        runner = live.read_runner(db, insp)
    except live.InspectionError as exc:
        raise _http(exc) from exc
    return ScoreSummary(**runner.score_payload())


@router.post(
    "/inspections/{inspection_id}/measurements",
    status_code=201,
    dependencies=[Depends(require(Perm.INSPECTIONS_RUN))],
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def add_measurement(inspection_id: uuid.UUID, body: MeasurementIn) -> None:
    not_implemented("M4")


@router.post(
    "/inspections/{inspection_id}/finalize",
    response_model=InspectionSnapshot,
    description="Compute the roll verdict from confirmed defects. 409 while any defect is pending.",
)
def finalize(
    inspection_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require(Perm.INSPECTIONS_RUN)),
    session_id: uuid.UUID | None = Depends(current_session_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> InspectionSnapshot:
    insp = _locked(db, inspection_id)
    try:
        live.finalize(db, insp, actor, idem, client_ip(request))
    except live.InspectionError as exc:
        db.rollback()
        raise _http(exc) from exc
    db.commit()
    return _snapshot(db, insp, session_id)


@router.post(
    "/inspections/{inspection_id}/decision",
    response_model=InspectionSnapshot,
    description="Supervisor decision on the roll (required for BORDERLINE; any override needs a reason).",
)
def decide(
    inspection_id: uuid.UUID,
    body: DecisionIn,
    request: Request,
    actor: User = Depends(require(Perm.VERDICT_DECIDE)),
    session_id: uuid.UUID | None = Depends(current_session_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> InspectionSnapshot:
    insp = _locked(db, inspection_id)
    try:
        live.decide_verdict(db, insp, body.final_verdict, body.reason, actor, idem, client_ip(request))
    except live.InspectionError as exc:
        db.rollback()
        raise _http(exc) from exc
    db.commit()
    return _snapshot(db, insp, session_id)


@router.get(
    "/inspections/{inspection_id}/report.pdf",
    response_class=Response,
    responses=PDF,
    dependencies=[Depends(require(Perm.REPORTS_READ))],
    description="Roll inspection report (PDF). Marked SIMULATED with the provider label when applicable.",
)
def roll_report(
    inspection_id: uuid.UUID,
    lang: str = Query("en", pattern="^(en|bn)$"),
    db: Session = Depends(get_db),
) -> Response:
    insp = _get(db, inspection_id)
    snapshot = _snapshot(db, insp, None)
    rows = live.defects(db, insp)
    info = _dataset(insp)
    crops: dict[str, bytes] = {}
    frames = live.captured_frames(db, insp)
    if info and frames:
        source = datasets.track_source(info)
        for d in rows:
            if d.kind != "defect" or d.status == "rejected":
                continue
            ev = evidence.best_capture(d, frames, source.track(), source.calibration)
            if ev and ev.frame.image_key:
                try:
                    crops[d.defect_no] = evidence.crop(
                        storage.get(db, ev.frame.image_key), ev.view_box, ev.frame.image_scale or 1.0, size=240
                    )
                except (OSError, ValueError):
                    continue
    content = build_roll_report(snapshot, [_defect_out(d, False) for d in rows], crops, lang=lang)
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="roll-report-{snapshot.roll_code}.pdf"',
            "Cache-Control": "no-store",
        },
    )


# ------------------------------------------------------------------------------------------ defects
@defects_router.get("/inspections/{inspection_id}/defects", response_model=list[DefectOut], dependencies=READ)
def list_defects(inspection_id: uuid.UUID, db: Session = Depends(get_db)) -> list[DefectOut]:
    insp = _get(db, inspection_id)
    return _defects_out(db, insp, live.defects(db, insp))


def _decide(
    db: Session,
    inspection_id: uuid.UUID,
    defect_no: str | None,
    decision: dict[str, Any],
    actor: User,
    idem: str,
    ip: str | None,
) -> DefectOut:
    insp = _locked(db, inspection_id)
    try:
        target = live.decide(db, insp, defect_no, decision, actor, idem, ip)
    except live.InspectionError as exc:
        db.rollback()
        raise _http(exc) from exc
    db.commit()
    db.expire_all()  # the projection was written with a Core upsert; reload rows the session already holds
    row = db.scalar(select(DefectRow).where(DefectRow.inspection_id == insp.id, DefectRow.defect_no == target))
    assert row
    return _defects_out(db, insp, [row])[0]


@defects_router.post(
    "/inspections/{inspection_id}/defects",
    response_model=DefectOut,
    status_code=201,
    description="Inspector adds a defect the detector missed. " + IDEMPOTENCY_NOTE,
)
def add_manual_defect(
    inspection_id: uuid.UUID,
    body: ManualDefectIn,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    decision = {"action": "manual", **body.model_dump()}
    return _decide(db, inspection_id, None, decision, actor, idem, client_ip(request))


def _row(db: Session, defect_id: uuid.UUID) -> DefectRow:
    row = db.get(DefectRow, defect_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "defect not found")
    return row


@defects_router.get("/defects/{defect_id}", response_model=DefectOut, dependencies=READ)
def get_defect(defect_id: uuid.UUID, db: Session = Depends(get_db)) -> DefectOut:
    row = _row(db, defect_id)
    return _defects_out(db, _get(db, row.inspection_id), [row])[0]


@defects_router.get("/defects/{defect_id}/crop", response_class=Response, responses=JPEG, dependencies=READ)
def defect_crop(
    defect_id: uuid.UUID,
    size: int = Query(360, ge=120, le=1000, description="Output side in pixels"),
    context: float = Query(2.2, ge=1.5, le=8.0, description="How much fabric around the defect"),
    db: Session = Depends(get_db),
) -> Response:
    row = _row(db, defect_id)
    insp = _get(db, row.inspection_id)
    info = _dataset(insp)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no evidence image")
    source = datasets.track_source(info)
    ev = evidence.best_capture(row, live.captured_frames(db, insp), source.track(), source.calibration)
    if ev is None or ev.frame.image_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no evidence image")
    try:
        content = evidence.crop(
            storage.get(db, ev.frame.image_key), ev.view_box, ev.frame.image_scale or 1.0, size=size, context=context
        )
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence image missing") from exc
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})


@defects_router.post("/defects/{defect_id}/confirm", response_model=DefectOut, description=IDEMPOTENCY_NOTE)
def confirm_defect(
    defect_id: uuid.UUID,
    body: ConfirmIn,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    row = _row(db, defect_id)
    decision = {"action": "confirm", "note": body.note}
    return _decide(db, row.inspection_id, row.defect_no, decision, actor, idem, client_ip(request))


@defects_router.post("/defects/{defect_id}/reject", response_model=DefectOut, description=IDEMPOTENCY_NOTE)
def reject_defect(
    defect_id: uuid.UUID,
    body: RejectIn,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    row = _row(db, defect_id)
    decision = {"action": "reject", "reason_category": body.reason_category, "note": body.note}
    return _decide(db, row.inspection_id, row.defect_no, decision, actor, idem, client_ip(request))


@defects_router.post("/defects/{defect_id}/reclassify", response_model=DefectOut, description=IDEMPOTENCY_NOTE)
def reclassify_defect(
    defect_id: uuid.UUID,
    body: ReclassifyIn,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    row = _row(db, defect_id)
    decision = {"action": "reclassify", "to_cls": body.to_cls}
    return _decide(db, row.inspection_id, row.defect_no, decision, actor, idem, client_ip(request))


@defects_router.post("/defects/{defect_id}/promote", response_model=DefectOut, description=IDEMPOTENCY_NOTE)
def promote_nondefect(
    defect_id: uuid.UUID,
    body: PromoteIn,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    row = _row(db, defect_id)
    decision = {"action": "promote", "to_cls": body.to_cls}
    return _decide(db, row.inspection_id, row.defect_no, decision, actor, idem, client_ip(request))


@defects_router.post("/defects/{defect_id}/length", response_model=DefectOut, description=IDEMPOTENCY_NOTE)
def edit_length(
    defect_id: uuid.UUID,
    body: LengthIn,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    row = _row(db, defect_id)
    decision = {"action": "length", "length_in": body.length_in}
    return _decide(db, row.inspection_id, row.defect_no, decision, actor, idem, client_ip(request))


@defects_router.post(
    "/defects/{defect_id}/reopen",
    response_model=DefectOut,
    description="Undo a confirm/reject: the defect is pending again. " + IDEMPOTENCY_NOTE,
)
def reopen_defect(
    defect_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require(Perm.DEFECTS_CONFIRM)),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> DefectOut:
    row = _row(db, defect_id)
    return _decide(db, row.inspection_id, row.defect_no, {"action": "reopen"}, actor, idem, client_ip(request))
