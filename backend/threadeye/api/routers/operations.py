from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from threadeye.api.deps import require
from threadeye.api.schemas.operations import (
    CuttingPolicyIn,
    DemoScheduleIn,
    EvaluationIn,
    MachineDetail,
    MachineIn,
    PreviewIn,
    ProfileIn,
    ProfileOut,
    ProviderIn,
    RunOut,
    ScheduleIn,
)
from threadeye.core.cutting import CutDefect, cutting_sheet
from threadeye.core.scoring.four_point import RollGeometry, ScorableDefect, score_roll
from threadeye.core.scoring.profile import RuleProfile
from threadeye.core.taxonomy import load_default_taxonomy
from threadeye.db import audit
from threadeye.db.models import (
    Buyer,
    CuttingPlan,
    DefectRow,
    Inspection,
    InspectionEvent,
    InspectionFrame,
    Lot,
    Machine,
    OperationRun,
    Roll,
    RuleProfileRow,
    Setting,
    Supplier,
    User,
)
from threadeye.db.session import get_db
from threadeye.reports.pdf import ThreadEyePDF
from threadeye.security.rbac import Perm, has_perm
from threadeye.services import datasets, demo_archive, live, operations, roll_image, storage
from threadeye.services.provider_config import provider_key
from threadeye.settings import get_settings

router = APIRouter(tags=["operations"])


@router.post("/admin/demo-archive")
def archive_samples(
    actor: User = Depends(require(Perm.SETTINGS_MANAGE)), db: Session = Depends(get_db)
) -> dict[str, int]:
    count = demo_archive.archive(db, actor)
    db.commit()
    return {"archived_deliveries": count}


@router.get("/admin/demo-archive/schedule")
def archive_schedule(_: User = Depends(require(Perm.SETTINGS_MANAGE)), db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(Setting, "demo_archive_schedule")
    return dict(row.value) if row else {"enabled": False}


@router.put("/admin/demo-archive/schedule")
def configure_archive(
    body: DemoScheduleIn, actor: User = Depends(require(Perm.SETTINGS_MANAGE)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    payload = {
        "enabled": body.enabled,
        "start_date": str(datetime.now(ZoneInfo("Asia/Dhaka")).date() + timedelta(days=1)),
    }
    row = db.get(Setting, "demo_archive_schedule")
    if row is None:
        row = Setting(key="demo_archive_schedule", value=payload, updated_by=actor.id)
        db.add(row)
    row.value, row.updated_by = payload, actor.id
    record(db, actor, "demo.archive_schedule", "setting", "demo_archive_schedule", **payload)
    db.commit()
    return payload


@router.put("/admin/provider")
def select_provider(
    body: ProviderIn, actor: User = Depends(require(Perm.PROVIDERS_MANAGE)), db: Session = Depends(get_db)
) -> dict[str, str]:
    if body.provider_id == "local_model":
        if get_settings().is_serverless:
            raise HTTPException(409, "the real model runs on the edge laptop")
        try:
            live._local_model_config()
        except live.InspectionError as exc:
            raise HTTPException(409, str(exc)) from exc
    key = provider_key()
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=body.provider_id, updated_by=actor.id)
        db.add(row)
    row.value, row.updated_by = body.provider_id, actor.id
    record(db, actor, "provider.default", "setting", key, provider_id=body.provider_id)
    db.commit()
    return {"provider_id": body.provider_id}


def record(db: Session, actor: User, action: str, entity: str, entity_id: str, **after: Any) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type=entity,
        entity_id=entity_id,
        after=after,
    )


def machine_exists(db: Session, machine_id: uuid.UUID | None) -> None:
    if machine_id is not None:
        machine = db.get(Machine, machine_id)
        if machine is None:
            raise HTTPException(404, "machine not found")
        if not machine.active:
            raise HTTPException(409, "machine is disabled")


def start_run(kind: str, body: EvaluationIn, actor: User, db: Session, tasks: BackgroundTasks) -> OperationRun:
    machine_exists(db, body.machine_id)
    if kind == "verification" and body.machine_id is None:
        raise HTTPException(422, "select the machine being verified")
    inputs = body.model_dump(mode="json")
    try:
        operations.validate_inputs(inputs, benchmark_run=kind == "benchmark")
    except (ValueError, datasets.DatasetNotFound, RuntimeError, live.InspectionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.provider_id == "local_model":
        inputs["provider_config"] = live._local_model_config()
    run = OperationRun(kind=kind, status="queued", actor_id=actor.id, machine_id=body.machine_id, inputs=inputs)
    db.add(run)
    db.flush()
    record(db, actor, f"{kind}.requested", "operation_run", str(run.id), inputs=inputs)
    db.commit()
    tasks.add_task(operations.execute, run.id)
    return run


@router.get("/verification/schedules")
def schedules(
    _: User = Depends(require(Perm.VERIFICATION_READ)), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    return [dict(row.value) for row in db.scalars(select(Setting).where(Setting.key.like("verification:%")))]


@router.put("/verification/schedules")
def save_schedule(
    body: ScheduleIn, actor: User = Depends(require(Perm.VERIFICATION_RUN)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    machine_exists(db, body.machine_id)
    if body.machine_id is None:
        raise HTTPException(422, "select a machine")
    payload = body.model_dump(mode="json")
    try:
        operations.validate_inputs(payload, benchmark_run=False)
    except (ValueError, datasets.DatasetNotFound, RuntimeError, live.InspectionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    key = f"verification:{body.machine_id}"
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=payload, updated_by=actor.id)
        db.add(row)
    row.value, row.updated_by = payload, actor.id
    record(db, actor, "verification.schedule", "machine", str(body.machine_id), **payload)
    db.commit()
    return payload


@router.post("/verification/runs", response_model=RunOut, status_code=202)
def verify(
    body: EvaluationIn,
    tasks: BackgroundTasks,
    actor: User = Depends(require(Perm.VERIFICATION_RUN)),
    db: Session = Depends(get_db),
) -> OperationRun:
    return start_run("verification", body, actor, db, tasks)


@router.post("/benchmark/runs", response_model=RunOut, status_code=202)
def benchmark(
    body: EvaluationIn,
    tasks: BackgroundTasks,
    actor: User = Depends(require(Perm.BENCHMARK_RUN)),
    db: Session = Depends(get_db),
) -> OperationRun:
    return start_run("benchmark", body, actor, db, tasks)


@router.get("/verification/runs", response_model=list[RunOut])
def verification_history(
    machine_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require(Perm.VERIFICATION_READ)),
    db: Session = Depends(get_db),
) -> list[OperationRun]:
    query = select(OperationRun).where(OperationRun.kind == "verification")
    if machine_id:
        query = query.where(OperationRun.machine_id == machine_id)
    return list(db.scalars(query.order_by(OperationRun.created_at.desc()).limit(limit)))


@router.get("/benchmark/runs", response_model=list[RunOut])
def benchmark_history(
    limit: int = Query(50, ge=1, le=200), _: User = Depends(require(Perm.BENCHMARK_READ)), db: Session = Depends(get_db)
) -> list[OperationRun]:
    return list(
        db.scalars(
            select(OperationRun)
            .where(OperationRun.kind == "benchmark")
            .order_by(OperationRun.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/dashboard")
def dashboard(
    actor: User = Depends(require(Perm.DASHBOARD_OWN_SHIFT)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    today = datetime.now(ZoneInfo("Asia/Dhaka")).date()
    start = datetime.combine(today, time.min, tzinfo=ZoneInfo("Asia/Dhaka"))
    query = (
        select(Inspection)
        .join(Roll, Roll.id == Inspection.roll_id)
        .join(Lot, Lot.id == Roll.lot_id)
        .where(
            Lot.status != "archived",
            Inspection.finalized_at >= start,
            Inspection.finalized_at < start + timedelta(days=1),
        )
    )
    if not has_perm(actor.role, Perm.DASHBOARD_READ):
        query = query.where(Inspection.inspector_id == actor.id)
    inspections = list(db.scalars(query.order_by(Inspection.finalized_at)))
    latest = {row.roll_id: row for row in inspections}
    values = list(latest.values())
    ids = [row.id for row in values]
    defects = list(db.scalars(select(DefectRow).where(DefectRow.inspection_id.in_(ids)))) if ids else []
    reviewed = [d for d in defects if d.origin != "manual" and d.status in {"confirmed", "rejected"}]
    points = [row.points_per_100 for row in values if row.points_per_100 is not None]
    coverage_latest = (
        select(
            InspectionEvent.payload,
            func.row_number()
            .over(partition_by=InspectionEvent.inspection_id, order_by=InspectionEvent.seq.desc())
            .label("rank"),
        )
        .where(InspectionEvent.inspection_id.in_(ids), InspectionEvent.type == "score.updated")
        .subquery()
    )
    coverage_rows = (
        list(db.scalars(select(coverage_latest.c.payload).where(coverage_latest.c.rank == 1))) if ids else []
    )
    coverage = [float(row["coverage_pct"]) for row in coverage_rows if row.get("coverage_pct") is not None]
    machine_names = {m.id: m.name for m in db.scalars(select(Machine))}
    suppliers = (
        {
            roll_id: name
            for roll_id, name in db.execute(
                select(Roll.id, Supplier.name)
                .join(Lot, Lot.id == Roll.lot_id)
                .join(Supplier, Supplier.id == Lot.supplier_id)
                .where(Roll.id.in_(list(latest)))
            )
        }
        if latest
        else {}
    )
    runs = list(
        db.scalars(
            select(OperationRun)
            .where(OperationRun.kind == "verification", OperationRun.created_at >= start)
            .order_by(OperationRun.created_at.desc())
        )
    )
    machines: dict[str, dict[str, Any]] = {}
    for run in runs:
        key = str(run.machine_id)
        if key not in machines:
            machines[key] = {
                "run_id": str(run.id),
                "status": run.status,
                "passed": (run.result or {}).get("passed"),
                "at": run.created_at.isoformat(),
            }
    return {
        "date": str(today),
        "scope": "all" if has_perm(actor.role, Perm.DASHBOARD_READ) else "own",
        "rolls": len(values),
        "verdicts": dict(Counter(row.system_verdict for row in values)),
        "avg_per_100": round(sum(points) / len(points), 2) if points else None,
        "false_alarm_share": sum(d.status == "rejected" for d in reviewed) / len(reviewed) if reviewed else None,
        "reviewed_detections": len(reviewed),
        "coverage_pct": round(sum(coverage) / len(coverage), 1) if coverage else None,
        "by_machine": dict(
            Counter(machine_names.get(row.machine_id, "—") if row.machine_id else "—" for row in values)
        ),
        "by_supplier": dict(Counter(suppliers.get(row.roll_id, "—") for row in values)),
        "simulated_rolls": sum(row.is_simulated for row in values),
        "defect_mix": dict(Counter(d.current_cls for d in defects if d.status == "confirmed" and d.kind == "defect")),
        "verification": machines,
        "active": [
            {"id": str(row.id), "roll_id": str(row.roll_id), "status": row.status}
            for row in db.scalars(
                select(Inspection).where(
                    Inspection.status.in_(["created", "running", "paused", "interrupted"]),
                    true() if has_perm(actor.role, Perm.DASHBOARD_READ) else Inspection.inspector_id == actor.id,
                )
            )
        ],
    }


@router.get("/admin/machines", response_model=list[MachineDetail])
def machines(_: User = Depends(require(Perm.MACHINES_MANAGE)), db: Session = Depends(get_db)) -> list[Machine]:
    return list(db.scalars(select(Machine).order_by(Machine.code)))


@router.post("/admin/machines", response_model=MachineDetail, status_code=201)
def add_machine(
    body: MachineIn, actor: User = Depends(require(Perm.MACHINES_MANAGE)), db: Session = Depends(get_db)
) -> Machine:
    if db.scalar(select(Machine.id).where(Machine.code == body.code)):
        raise HTTPException(409, "machine code already exists")
    row = Machine(**body.model_dump(mode="json"))
    db.add(row)
    db.flush()
    record(db, actor, "machine.create", "machine", str(row.id), **body.model_dump(mode="json"))
    db.commit()
    return row


@router.patch("/admin/machines/{machine_id}", response_model=MachineDetail)
def edit_machine(
    machine_id: uuid.UUID,
    body: MachineIn,
    actor: User = Depends(require(Perm.MACHINES_MANAGE)),
    db: Session = Depends(get_db),
) -> Machine:
    row = db.scalar(select(Machine).where(Machine.id == machine_id).with_for_update())
    if row is None:
        raise HTTPException(404, "machine not found")
    if db.scalar(select(Machine.id).where(Machine.code == body.code, Machine.id != machine_id)):
        raise HTTPException(409, "machine code already exists")
    for key, value in body.model_dump(mode="json").items():
        setattr(row, key, value)
    record(db, actor, "machine.update", "machine", str(row.id), **body.model_dump(mode="json"))
    db.commit()
    return row


@router.get("/admin/rule-profiles", response_model=list[ProfileOut])
def profiles(_: User = Depends(require(Perm.PROFILES_READ)), db: Session = Depends(get_db)) -> list[RuleProfileRow]:
    return list(db.scalars(select(RuleProfileRow).order_by(RuleProfileRow.name, RuleProfileRow.version.desc())))


@router.post("/admin/rule-profiles", response_model=ProfileOut, status_code=201)
def save_profile(
    body: ProfileIn, actor: User = Depends(require(Perm.PROFILES_WRITE)), db: Session = Depends(get_db)
) -> RuleProfileRow:
    if body.buyer_id and db.get(Buyer, body.buyer_id) is None:
        raise HTTPException(422, "buyer not found")
    # Transaction advisory lock serializes concurrent version creation for this profile name.
    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": body.rules.name})
    prior = list(db.scalars(select(RuleProfileRow).where(RuleProfileRow.name == body.rules.name).with_for_update()))
    if any(p.buyer_id != body.buyer_id for p in prior):
        raise HTTPException(409, "use a distinct profile name for a different buyer")
    for previous in prior:
        previous.status = "retired"
    row = RuleProfileRow(
        name=body.rules.name,
        buyer_id=body.buyer_id,
        version=max((p.version for p in prior), default=0) + 1,
        status="active",
        rules=body.rules.model_dump(mode="json"),
        rules_hash=body.rules.rules_hash(),
        created_by=actor.id,
    )
    db.add(row)
    db.flush()
    record(db, actor, "profile.version", "rule_profile", str(row.id), version=row.version, hash=row.rules_hash)
    db.commit()
    return row


@router.post("/admin/rule-profiles/preview")
def preview(body: PreviewIn, _: User = Depends(require(Perm.PROFILES_READ))) -> dict[str, Any]:
    taxonomy = load_default_taxonomy()
    defects = []
    for index, item in enumerate(body.defects):
        if item.end_yd < item.start_yd or item.end_yd > body.length_yd:
            raise HTTPException(422, "defect positions must lie within the roll")
        if item.across_end_cm < item.across_start_cm or item.across_end_cm > body.width_in * 2.54:
            raise HTTPException(422, "defect across positions must lie within the roll")
        if item.cls not in taxonomy.classes:
            raise HTTPException(422, "unknown defect class")
        defects.append(
            ScorableDefect(
                defect_id=str(index),
                is_hole=taxonomy.classes[item.cls].is_hole,
                kind="nondefect" if taxonomy.is_nondefect(item.cls) else "defect",
                center_yd=(item.start_yd + item.end_yd) / 2,
                **item.model_dump(),
            )
        )
    score = score_roll(defects, RollGeometry(body.length_yd, body.width_in, body.width_in * 2.54), body.rules)
    return {
        "points": score.total_points,
        "per_100": score.per_100,
        "verdict": score.verdict,
        "explanation": score.explanation,
        "cells": score.cells,
    }


def cutting_data(db: Session, inspection_id: uuid.UUID) -> tuple[Inspection, dict[str, Any], str]:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(404, "inspection not found")
    if inspection.finalized_at is None or inspection.yards_inspected is None:
        raise HTTPException(409, "finalize the inspection before creating cutting instructions")
    profile = db.get(RuleProfileRow, inspection.rule_profile_id)
    assert profile
    saved = db.scalar(select(CuttingPlan).where(CuttingPlan.inspection_id == inspection_id))
    selection = saved.plan.get("policy_selection", "buyer") if saved else "buyer"
    policy = RuleProfile(**profile.rules).cutting
    thresholds = {"all": 1, "two_plus": 2, "three_plus": 3, "four_plus": 4}
    if selection in thresholds:
        policy = policy.model_copy(update={"min_points_to_cut": thresholds[selection]})
    defects = list(
        db.scalars(
            select(DefectRow)
            .where(
                DefectRow.inspection_id == inspection.id, DefectRow.status == "confirmed", DefectRow.kind == "defect"
            )
            .order_by(DefectRow.defect_no)
        )
    )
    source: dict[str, Any] = {
        "inspection_id": str(inspection.id),
        "profile_hash": profile.rules_hash,
        "length": inspection.measured_length_yd or inspection.yards_inspected,
        "defects": [
            {"id": str(d.id), "start": d.start_yd, "end": d.end_yd, "points": d.points, "excluded": d.excluded_reason}
            for d in defects
        ],
    }
    # Preserve existing buyer-default hashes/approvals. An explicit override is
    # inspection-specific and never changes the buyer's scoring profile.
    if selection != "buyer":
        source["cutting_policy_selection"] = selection
    fingerprint = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    plan = cutting_sheet(
        float(source["length"]),
        [CutDefect(d.start_yd, d.end_yd, d.points or 0) for d in defects if not d.excluded_reason],
        policy,
    )
    plan["policy_selection"] = selection
    return inspection, plan, fingerprint


def cutting_out(db: Session, inspection_id: uuid.UUID) -> dict[str, Any]:
    inspection, calculated, fingerprint = cutting_data(db, inspection_id)
    saved = db.scalar(select(CuttingPlan).where(CuttingPlan.inspection_id == inspection_id))
    valid = saved is not None and saved.source_hash == fingerprint
    try:
        info = datasets.get_dataset(inspection.dataset_id) if inspection.dataset_id else None
    except datasets.DatasetNotFound:
        info = None
    return {
        "inspection_id": str(inspection_id),
        "source_hash": fingerprint,
        "policy_selection": calculated["policy_selection"],
        "policy_locked": bool(saved and saved.approved_at),
        "plan": saved.plan if valid and saved else calculated,
        "simulated": inspection.is_simulated,
        "fabric": {
            "image_url": f"/api/v1/inspections/{inspection_id}/cutting/fabric.jpg",
            "length_yd": info.roll_length_yd,
            "width_cm": info.fabric_width_cm,
        }
        if info and (info.path / "roll_video.mp4").is_file()
        else None,
        "defects": [
            {
                "id": str(d.id),
                "number": d.defect_no,
                "cls": d.current_cls,
                "start_yd": d.start_yd,
                "end_yd": d.end_yd,
                "across_start_cm": d.across_start_cm,
                "across_end_cm": d.across_end_cm,
            }
            for d in db.scalars(
                select(DefectRow)
                .where(
                    DefectRow.inspection_id == inspection_id,
                    DefectRow.status == "confirmed",
                    DefectRow.kind == "defect",
                    DefectRow.excluded_reason.is_(None),
                )
                .order_by(DefectRow.defect_no)
            )
        ],
        "status": "acknowledged"
        if valid and saved and saved.acknowledged_at
        else "approved"
        if valid and saved and saved.approved_at
        else "draft",
        "approved_at": saved.approved_at.isoformat() if valid and saved and saved.approved_at else None,
        "acknowledged_at": saved.acknowledged_at.isoformat() if valid and saved and saved.acknowledged_at else None,
    }


@router.get("/cutting")
def cutting_queue(_: User = Depends(require(Perm.CUTTING_READ)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Discover approved instructions; drafts and invalidated approvals are not work orders."""
    rows = db.execute(
        select(CuttingPlan, Roll.roll_code, Lot.challan_no)
        .join(Inspection, Inspection.id == CuttingPlan.inspection_id)
        .join(Roll, Roll.id == Inspection.roll_id)
        .join(Lot, Lot.id == Roll.lot_id)
        .where(CuttingPlan.approved_at.is_not(None), Inspection.finalized_at.is_not(None), Lot.status != "archived")
        .order_by(CuttingPlan.acknowledged_at.is_not(None), CuttingPlan.approved_at.desc())
    )
    result = []
    for saved, roll_code, challan in rows:
        fingerprint = cutting_data(db, saved.inspection_id)[2]
        if saved.source_hash != fingerprint or saved.approved_at is None:
            continue
        result.append(
            {
                "inspection_id": str(saved.inspection_id),
                "roll_code": roll_code,
                "challan": challan,
                "status": "acknowledged" if saved.acknowledged_at else "approved",
                "approved_at": saved.approved_at.isoformat(),
                "acknowledged_at": saved.acknowledged_at.isoformat() if saved.acknowledged_at else None,
                "usable_yd": saved.plan["usable_yd"],
                "skipped_yd": saved.plan["skipped_yd"],
            }
        )
    return result


@router.get("/inspections/{inspection_id}/cutting")
def get_cutting(
    inspection_id: uuid.UUID, _: User = Depends(require(Perm.CUTTING_READ)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return cutting_out(db, inspection_id)


@router.put("/inspections/{inspection_id}/cutting/policy")
def select_cutting_policy(
    inspection_id: uuid.UUID,
    body: CuttingPolicyIn,
    actor: User = Depends(require(Perm.CUTTING_APPROVE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    db.scalar(select(Inspection).where(Inspection.id == inspection_id).with_for_update())
    _, _, _ = cutting_data(db, inspection_id)
    row = db.scalar(select(CuttingPlan).where(CuttingPlan.inspection_id == inspection_id))
    if row and row.approved_at:
        raise HTTPException(409, "the approved cutting policy is locked")
    if row is None:
        row = CuttingPlan(inspection_id=inspection_id, source_hash="", plan={})
        db.add(row)
    previous = row.plan.get("policy_selection", "buyer")
    row.plan = {**row.plan, "policy_selection": body.selection}
    db.flush()
    _, plan, fingerprint = cutting_data(db, inspection_id)
    row.plan, row.source_hash = plan, fingerprint
    if previous != body.selection:
        record(
            db,
            actor,
            "cutting.policy",
            "inspection",
            str(inspection_id),
            previous=previous,
            selection=body.selection,
            source_hash=fingerprint,
        )
    db.commit()
    return cutting_out(db, inspection_id)


@router.get(
    "/inspections/{inspection_id}/cutting/fabric.jpg",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def cutting_fabric(
    inspection_id: uuid.UUID, _: User = Depends(require(Perm.CUTTING_READ)), db: Session = Depends(get_db)
) -> Response:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(404, "inspection not found")
    try:
        info = datasets.get_dataset(inspection.dataset_id or "")
        data = roll_image.image_bytes(info.path)
    except (datasets.DatasetNotFound, OSError, ValueError, ImportError) as exc:
        raise HTTPException(404, "fabric image is unavailable on this server") from exc
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.post("/inspections/{inspection_id}/cutting/approve")
def approve_cutting(
    inspection_id: uuid.UUID, actor: User = Depends(require(Perm.CUTTING_APPROVE)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    db.scalar(select(Inspection).where(Inspection.id == inspection_id).with_for_update())
    _, plan, fingerprint = cutting_data(db, inspection_id)
    row = db.scalar(select(CuttingPlan).where(CuttingPlan.inspection_id == inspection_id))
    if row and row.source_hash == fingerprint and row.approved_at:
        return cutting_out(db, inspection_id)
    if row is None:
        row = CuttingPlan(inspection_id=inspection_id, source_hash=fingerprint, plan=plan)
        db.add(row)
    row.source_hash, row.plan = fingerprint, plan
    row.approved_by, row.approved_at = actor.id, datetime.now(UTC)
    row.acknowledged_by, row.acknowledged_at = None, None
    record(db, actor, "cutting.approve", "inspection", str(inspection_id), source_hash=fingerprint)
    db.commit()
    return cutting_out(db, inspection_id)


@router.post("/inspections/{inspection_id}/cutting/acknowledge")
def acknowledge_cutting(
    inspection_id: uuid.UUID, actor: User = Depends(require(Perm.CUTTING_ACKNOWLEDGE)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    db.scalar(select(Inspection).where(Inspection.id == inspection_id).with_for_update())
    _, _, fingerprint = cutting_data(db, inspection_id)
    row = db.scalar(select(CuttingPlan).where(CuttingPlan.inspection_id == inspection_id).with_for_update())
    if row is None or row.approved_at is None or row.source_hash != fingerprint:
        raise HTTPException(409, "a current supervisor approval is required")
    if row.acknowledged_at is None:
        row.acknowledged_by, row.acknowledged_at = actor.id, datetime.now(UTC)
        record(db, actor, "cutting.acknowledge", "inspection", str(inspection_id), source_hash=fingerprint)
        db.commit()
    return cutting_out(db, inspection_id)


@router.get("/inspections/{inspection_id}/cutting.pdf")
def cutting_pdf(
    inspection_id: uuid.UUID,
    lang: str = Query("en", pattern="^(en|bn)$"),
    _: User = Depends(require(Perm.CUTTING_READ)),
    db: Session = Depends(get_db),
) -> Response:
    data = cutting_out(db, inspection_id)
    inspection = db.get(Inspection, inspection_id)
    assert inspection
    pdf = ThreadEyePDF(
        simulated=inspection.is_simulated,
        title="Cutting sheet / কাটিং নির্দেশনা",
        provider_label=inspection.provider_snapshot["info"]["display_name"],
        detections_simulated=inspection.provider_snapshot["info"]["is_simulated"],
    )
    pdf.add_page()
    pdf.multi_cell(
        0, 7, text=f"{inspection_id}\n{data['status']}\nSHA256: {data['source_hash']}", new_x="LMARGIN", new_y="NEXT"
    )
    saved = db.scalar(select(CuttingPlan).where(CuttingPlan.inspection_id == inspection_id))
    for action, label in (
        ("approved", "অনুমোদন করেছেন" if lang == "bn" else "Approved by"),
        ("acknowledged", "নির্দেশনা গ্রহণ করেছেন" if lang == "bn" else "Acknowledged by"),
    ):
        at = data[f"{action}_at"]
        actor_id = getattr(saved, f"{action}_by") if saved and at else None
        actor = db.get(User, actor_id) if actor_id else None
        if at:
            name = f"{actor.display_name} ({actor.username})" if actor else str(actor_id or "Unknown")
            local_time = datetime.fromisoformat(at).astimezone(ZoneInfo("Asia/Dhaka")).isoformat(timespec="seconds")
            text = f"{label}: {name}\n{local_time} (Asia/Dhaka)"
        else:
            pending = "এখনও হয়নি" if lang == "bn" else "Not yet recorded"
            text = f"{label}: {pending}"
        pdf.multi_cell(0, 7, text=text, new_x="LMARGIN", new_y="NEXT")
    plan = data["plan"]
    pdf.multi_cell(
        0,
        7,
        text=f"Usable / ব্যবহারযোগ্য: {plan['usable_yd']} yd\nSkip / বাদ: {plan['skipped_yd']} yd",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    for segment in plan["segments"]:
        action = ("রাখুন" if segment["action"] == "keep" else "বাদ দিন") if lang == "bn" else segment["action"]
        pdf.cell(
            0,
            7,
            text=f"{segment['start_yd']:.3f} - {segment['end_yd']:.3f} yd: {action}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    return Response(bytes(pdf.output()), media_type="application/pdf")


@router.post("/inspections/{inspection_id}/defects/{defect_id}/clip", response_model=RunOut, status_code=202)
def export_clip(
    inspection_id: uuid.UUID,
    defect_id: uuid.UUID,
    tasks: BackgroundTasks,
    actor: User = Depends(require(Perm.REPORTS_GENERATE)),
    db: Session = Depends(get_db),
) -> OperationRun:
    if get_settings().is_serverless:
        raise HTTPException(409, "MP4 export runs on the edge laptop; use source-video playback on the cloud demo")
    defect = db.get(DefectRow, defect_id)
    if defect is None or defect.inspection_id != inspection_id:
        raise HTTPException(404, "defect not found in inspection")
    run = OperationRun(
        kind="clip",
        status="queued",
        actor_id=actor.id,
        inspection_id=inspection_id,
        inputs={"defect_id": str(defect_id)},
    )
    db.add(run)
    db.flush()
    record(db, actor, "clip.requested", "operation_run", str(run.id), defect_id=str(defect_id))
    db.commit()
    tasks.add_task(operations.execute, run.id)
    return run


@router.get("/inspections/{inspection_id}/clips", response_model=list[RunOut])
def list_clips(
    inspection_id: uuid.UUID, _: User = Depends(require(Perm.REPORTS_READ)), db: Session = Depends(get_db)
) -> list[OperationRun]:
    return list(
        db.scalars(
            select(OperationRun)
            .where(OperationRun.inspection_id == inspection_id, OperationRun.kind == "clip")
            .order_by(OperationRun.created_at.desc())
        )
    )


@router.get("/inspections/{inspection_id}/clips/{run_id}.mp4")
def download_clip(
    inspection_id: uuid.UUID,
    run_id: uuid.UUID,
    _: User = Depends(require(Perm.REPORTS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    run = db.get(OperationRun, run_id)
    if (
        not run
        or run.kind != "clip"
        or run.inspection_id != inspection_id
        or run.status != "completed"
        or not run.result
    ):
        raise HTTPException(404, "clip is not ready")
    return Response(storage.get(db, run.result["storage_key"]), media_type="video/mp4")


@router.get("/inspections/{inspection_id}/labels.zip")
def labels(
    inspection_id: uuid.UUID, actor: User = Depends(require(Perm.LABEL_DATA_EXPORT)), db: Session = Depends(get_db)
) -> Response:
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(404, "inspection not found")
    taxonomy = load_default_taxonomy()
    categories = [{"id": index + 1, "name": name} for index, name in enumerate(sorted(taxonomy.classes))]
    category_ids = {c["name"]: c["id"] for c in categories}
    defects = list(
        db.scalars(
            select(DefectRow).where(
                DefectRow.inspection_id == inspection_id, DefectRow.status.in_(["confirmed", "rejected"])
            )
        )
    )
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    simulated_detector = bool((inspection.provider_snapshot.get("info") or {}).get("is_simulated"))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for frame in db.scalars(
            select(InspectionFrame).where(
                InspectionFrame.inspection_id == inspection_id, InspectionFrame.image_key.is_not(None)
            )
        ):
            relevant = [d for d in defects if d.best_frame == frame.frame]
            if not relevant or not frame.image_key:
                continue
            image_id = len(images) + 1
            filename = f"images/{frame.frame}.jpg"
            archive.writestr(filename, storage.get(db, frame.image_key))
            images.append(
                {
                    "id": image_id,
                    "file_name": filename,
                    "width": frame.width,
                    "height": frame.height,
                    "source_group": inspection.dataset_id,
                    "split": "unassigned",
                    "sha256": frame.image_sha256,
                }
            )
            for defect in relevant:
                decisions.append(
                    {
                        "image_id": image_id,
                        "defect_id": str(defect.id),
                        "status": defect.status,
                        "reason": defect.reject_reason,
                        "label_source": "inspector",
                        "source": "answer_key" if simulated_detector and defect.origin == "detector" else "human",
                    }
                )
                if defect.status != "confirmed" or defect.kind != "defect" or not defect.best_bbox_px:
                    continue
                x0, y0, x1, y1 = defect.best_bbox_px
                scale = frame.image_scale or 1
                x, y = max(0.0, x0 * scale), max(0.0, y0 * scale)
                width = max(0.0, min(x1 * scale, float(frame.width or 0)) - x)
                height = max(0.0, min(y1 * scale, float(frame.height or 0)) - y)
                if not width or not height:
                    continue
                annotations.append(
                    {
                        "id": len(annotations) + 1,
                        "image_id": image_id,
                        "category_id": category_ids[defect.current_cls],
                        "bbox": [x, y, width, height],
                        "area": width * height,
                        "iscrowd": 0,
                        "label_source": "inspector",
                        "source": "answer_key" if simulated_detector and defect.origin == "detector" else "human",
                    }
                )
        archive.writestr(
            "annotations.json",
            json.dumps(
                {
                    "images": images,
                    "annotations": annotations,
                    "categories": categories,
                    "decisions": decisions,
                    "info": {
                        "simulated_video": inspection.is_simulated,
                        "detector_provider": inspection.provider_snapshot.get("provider_id"),
                        "not_training_ready": "review labels, deduplicate source groups, and assign splits first",
                    },
                }
            ),
        )
    record(
        db, actor, "labels.export", "inspection", str(inspection_id), images=len(images), annotations=len(annotations)
    )
    db.commit()
    return Response(
        stream.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="labels-{inspection_id}.zip"'},
    )
