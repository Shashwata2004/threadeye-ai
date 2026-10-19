from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from threadeye.api.deps import current_user, require
from threadeye.api.schemas.system import (
    AuditEntryOut,
    AuditVerifyOut,
    ModelEvaluationOut,
    ProviderAvailabilityOut,
    SystemStatusOut,
    WorkerStatus,
)
from threadeye.db.audit import verify_chain
from threadeye.db.models import AuditLog, ComponentHeartbeat, User
from threadeye.db.session import get_db, ping
from threadeye.providers.registry import REGISTRY, ProviderSpec
from threadeye.security.rbac import Perm
from threadeye.services import model_card
from threadeye.settings import get_settings

router = APIRouter(tags=["system"])

WORKER_STALE_AFTER = timedelta(seconds=30)


def _provider_out(spec: ProviderSpec, active_id: str) -> ProviderAvailabilityOut:
    return ProviderAvailabilityOut(
        provider_id=spec.provider_id,
        display_name=spec.display_name,
        kind=spec.kind,
        is_simulated=spec.is_simulated,
        availability=spec.availability,
        milestone=spec.milestone,
        note=spec.note,
        active=spec.provider_id == active_id,
    )


@router.get("/system/status", response_model=SystemStatusOut)
def system_status(_: User = Depends(current_user), db: Session = Depends(get_db)) -> SystemStatusOut:
    s = get_settings()
    hb = db.get(ComponentHeartbeat, "worker")
    alive = hb is not None and datetime.now(UTC) - hb.last_seen_at < WORKER_STALE_AFTER
    active = REGISTRY.get(s.detector_provider, REGISTRY["simulated"])
    return SystemStatusOut(
        profile=s.deploy_profile,
        version=s.version,
        db="ok" if ping() else "error",
        worker=WorkerStatus(alive=alive, last_seen_at=hb.last_seen_at if hb else None),
        active_provider=_provider_out(active, active.provider_id),
        simulated_mode=active.is_simulated,
        sample_data_present=False,
    )


@router.get("/providers", response_model=list[ProviderAvailabilityOut])
def list_providers(_: User = Depends(current_user)) -> list[ProviderAvailabilityOut]:
    active_id = get_settings().detector_provider
    return [_provider_out(spec, active_id) for spec in REGISTRY.values()]


@router.get(
    "/model/evaluation", response_model=ModelEvaluationOut, responses={404: {"description": "no evaluated model"}}
)
def model_evaluation(_: User = Depends(current_user)) -> dict[str, Any]:
    """The trained detector's test-split results (Benchmark screen)."""
    ev = model_card.load_evaluation(get_settings().model_dir)
    if ev is None:
        raise HTTPException(404, "no evaluated model yet")
    return ev


@router.get("/audit", response_model=list[AuditEntryOut], tags=["audit"])
def list_audit(
    _: User = Depends(require(Perm.AUDIT_READ)),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = Query(None, ge=1),
    action: str | None = Query(None, max_length=64),
    entity_type: str | None = Query(None, max_length=64),
) -> list[AuditLog]:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if before_id is not None:
        q = q.where(AuditLog.id < before_id)
    if action:
        q = q.where(AuditLog.action == action)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    return list(db.scalars(q))


@router.get("/audit/verify", response_model=AuditVerifyOut, tags=["audit"])
def verify_audit(_: User = Depends(require(Perm.AUDIT_READ)), db: Session = Depends(get_db)) -> AuditVerifyOut:
    r = verify_chain(db)
    return AuditVerifyOut(ok=r.ok, checked=r.checked, first_bad_id=r.first_bad_id, reason=r.reason)
