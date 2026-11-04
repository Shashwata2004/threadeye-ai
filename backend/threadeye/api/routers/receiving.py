"""Receiving: master data, deliveries (lots), rolls and QR labels (M1)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from threadeye.api.deps import client_ip, require
from threadeye.api.schemas.receiving import (
    BuyerOut,
    LotCreate,
    LotDecisionIn,
    LotDecisionOut,
    LotOut,
    LotRollVerdict,
    LotRulesOut,
    LotVerdictOut,
    MachineOut,
    MillScorecard,
    NamedRef,
    RollOut,
    RollsBulkCreate,
    RuleProfileSummary,
    SamplingSuggestionOut,
    ScorecardDelivery,
    ScorecardMonth,
    ScorecardShare,
    SupplierIn,
    SupplierOut,
)
from threadeye.db import audit
from threadeye.db.models import Buyer, Lot, Machine, Roll, RuleProfileRow, Supplier, User
from threadeye.db.session import get_db
from threadeye.reports.labels import LabelData, build_labels_pdf
from threadeye.security.rbac import Perm
from threadeye.services import receiving as svc
from threadeye.services import scorecard as sc

router = APIRouter(tags=["receiving"])
PDF: dict[int | str, dict[str, Any]] = {200: {"content": {"application/pdf": {}}, "description": "PDF document"}}


def _fail(exc: svc.ReceivingError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _profile_summary(row: RuleProfileRow) -> RuleProfileSummary:
    return RuleProfileSummary(
        id=row.id,
        buyer_id=row.buyer_id,
        name=row.name,
        version=row.version,
        status=row.status,
        threshold_per_100=float(row.rules.get("threshold_per_100", 40.0)),
    )


def _lot_out(db: Session, lot: Lot) -> LotOut:
    supplier = db.get(Supplier, lot.supplier_id)
    buyer = db.get(Buyer, lot.buyer_id)
    profile = db.get(RuleProfileRow, lot.rule_profile_id)
    assert supplier and buyer
    return LotOut(
        id=lot.id,
        challan_no=lot.challan_no,
        supplier=NamedRef(id=supplier.id, name=supplier.name, is_sample_data=supplier.is_sample_data),
        buyer=NamedRef(id=buyer.id, name=buyer.name, is_sample_data=buyer.is_sample_data),
        order_ref=lot.order_ref,
        fabric_type=lot.fabric_type,
        colour=lot.colour,
        received_at=lot.received_at,
        declared_rolls=lot.declared_rolls,
        declared_total_yd=lot.declared_total_yd,
        rule_profile=_profile_summary(profile) if profile else None,
        sampling_pct=lot.sampling_pct,
        status=lot.status,
        lot_verdict=lot.lot_verdict,
        rolls_registered=svc.roll_count(db, lot.id),
        is_sample_data=lot.is_sample_data,
        created_at=lot.created_at,
    )


def _get_lot(db: Session, lot_id: uuid.UUID) -> Lot:
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot not found")
    return lot


def _labels(db: Session, rolls: Sequence[Roll]) -> list[LabelData]:
    out = []
    for r in rolls:
        lot = db.get(Lot, r.lot_id)
        assert lot
        supplier, buyer = db.get(Supplier, lot.supplier_id), db.get(Buyer, lot.buyer_id)
        out.append(
            LabelData(
                roll_code=r.roll_code,
                mill_roll_no=r.mill_roll_no,
                challan_no=lot.challan_no,
                supplier=supplier.name if supplier else "",
                buyer=buyer.name if buyer else "",
                fabric_type=lot.fabric_type,
                declared_length_yd=r.declared_length_yd,
                declared_width_in=r.declared_width_in,
                dye_lot=r.dye_lot,
                is_sample_data=r.is_sample_data,
            )
        )
    return out


def _pdf(content: bytes, filename: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"},
    )


# ------------------------------------------------------------------------------------------- master data
@router.get("/suppliers", response_model=list[SupplierOut], dependencies=[Depends(require(Perm.MASTER_DATA_READ))])
def list_suppliers(db: Session = Depends(get_db)) -> list[Supplier]:
    return list(db.scalars(select(Supplier).order_by(Supplier.name)))


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(
    body: SupplierIn,
    request: Request,
    actor: User = Depends(require(Perm.MASTER_DATA_WRITE)),
    db: Session = Depends(get_db),
) -> Supplier:
    name = body.name.strip()
    if db.scalar(select(Supplier.id).where(func.lower(Supplier.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "a mill with this name exists")
    supplier = Supplier(name=name, country=body.country)
    db.add(supplier)
    db.flush()
    audit.record(
        db,
        action="supplier.create",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="supplier",
        entity_id=str(supplier.id),
        after={"name": name, "country": body.country},
        ip=client_ip(request),
    )
    db.commit()
    return supplier


@router.get("/buyers", response_model=list[BuyerOut], dependencies=[Depends(require(Perm.MASTER_DATA_READ))])
def list_buyers(db: Session = Depends(get_db)) -> list[Buyer]:
    return list(db.scalars(select(Buyer).order_by(Buyer.name)))


@router.get("/machines", response_model=list[MachineOut], dependencies=[Depends(require(Perm.MASTER_DATA_READ))])
def list_machines(db: Session = Depends(get_db)) -> list[Machine]:
    return list(db.scalars(select(Machine).where(Machine.active.is_(True)).order_by(Machine.code)))


@router.get(
    "/rule-profiles", response_model=list[RuleProfileSummary], dependencies=[Depends(require(Perm.PROFILES_READ))]
)
def list_rule_profiles(buyer_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> list[RuleProfileSummary]:
    q = select(RuleProfileRow).where(RuleProfileRow.status == "active").order_by(RuleProfileRow.name)
    if buyer_id:
        q = q.where((RuleProfileRow.buyer_id == buyer_id) | RuleProfileRow.buyer_id.is_(None))
    return [_profile_summary(r) for r in db.scalars(q)]


# ------------------------------------------------------------------------------------------- lots
@router.get("/lots", response_model=list[LotOut], dependencies=[Depends(require(Perm.LOTS_READ))])
def list_lots(include_archived: bool = False, db: Session = Depends(get_db)) -> list[LotOut]:
    query = select(Lot)
    if not include_archived:
        query = query.where(Lot.status != "archived")
    lots = db.scalars(query.order_by(Lot.created_at.desc()).limit(200))
    return [_lot_out(db, lot) for lot in lots]


@router.post("/lots", response_model=LotOut, status_code=status.HTTP_201_CREATED)
def create_lot(
    body: LotCreate,
    request: Request,
    actor: User = Depends(require(Perm.LOTS_WRITE)),
    db: Session = Depends(get_db),
) -> LotOut:
    try:
        lot = svc.create_lot(db, svc.NewLot(**body.model_dump()), actor, ip=client_ip(request))
    except svc.ReceivingError as exc:
        raise _fail(exc) from exc
    db.commit()
    return _lot_out(db, lot)


@router.get("/lots/{lot_id}", response_model=LotOut, dependencies=[Depends(require(Perm.LOTS_READ))])
def get_lot(lot_id: uuid.UUID, db: Session = Depends(get_db)) -> LotOut:
    return _lot_out(db, _get_lot(db, lot_id))


def _verdict_out(db: Session, lot: Lot, summary: svc.LotSummary) -> LotVerdictOut:
    r = summary.result
    decision = None
    if lot.decision:
        by = db.get(User, lot.decision_by) if lot.decision_by else None
        decision = LotDecisionOut(
            decision=lot.decision,
            reason=lot.decision_reason,
            decided_by=by.display_name if by else None,
            decided_at=lot.decision_at,
            lot_verdict=lot.lot_verdict,
        )
    return LotVerdictOut(
        status=r.status,
        required_sample=r.required_sample,
        inspected=r.inspected,
        failed=r.failed,
        fail_pct=r.fail_pct,
        total_rolls=summary.total_rolls,
        rules=LotRulesOut(**summary.rules.model_dump()),
        rolls=[
            LotRollVerdict(
                roll_id=i.roll.id,
                roll_code=i.roll.roll_code,
                inspection_id=i.inspection.id if i.inspection else None,
                verdict=i.verdict,
                system_verdict=i.inspection.system_verdict if i.inspection else None,
                final_verdict=i.inspection.final_verdict if i.inspection else None,
                points_per_100=i.inspection.points_per_100 if i.inspection else None,
            )
            for i in summary.rolls
        ],
        decision=decision,
        claim_eligible=svc.claim_block_reason(
            lot.decision,
            sum(
                i.inspection is not None and i.inspection.final_verdict in svc.ROLL_FAILED_DECISIONS
                for i in summary.rolls
            ),
        )
        is None,
    )


@router.get(
    "/suppliers/scorecard",
    response_model=list[MillScorecard],
    dependencies=[Depends(require(Perm.SUPPLIERS_SCORECARD))],
)
def supplier_scorecards(db: Session = Depends(get_db)) -> list[MillScorecard]:
    """Every mill's record from its finalized inspections (each roll's latest): acceptance, points, claims,
    yardage shortage, a six-month trend, the defect mix and the deliveries."""
    months = sc.months_back(datetime.now(UTC).date())
    out = []
    for m in sc.scorecards(db):
        total = sum(m.mix.values())
        out.append(
            MillScorecard(
                id=m.id,
                name=m.name,
                country=m.country,
                rolls_inspected=m.rolls,
                acceptance=m.acceptance,
                avg_points_per_100=m.avg_points,
                claims=m.claims,
                shortage=m.shortage,
                trend=[
                    ScorecardMonth(
                        month=mo,
                        avg_points_per_100=m.month_avg(mo),
                        rolls=len(m.by_month[mo]),
                    )
                    for mo in months
                ],
                mix=[ScorecardShare(cls=c, share=round(100 * n / total, 1)) for c, n in m.mix.most_common()],
                deliveries=[
                    ScorecardDelivery(
                        lot_id=d.lot_id,
                        challan=d.challan,
                        received=d.received,
                        fabric=d.fabric,
                        passed=d.passed,
                        review=d.review,
                        failed=d.failed,
                        avg_points_per_100=d.avg_points,
                        shortage_yd=d.shortage_yd,
                        claims=d.claims,
                        status=d.status,
                        lot_decision=d.lot_decision,
                        claim_eligible=d.claim_eligible,
                    )
                    for d in m.deliveries
                ],
            )
        )
    return out


@router.get("/lots/{lot_id}/verdict", response_model=LotVerdictOut, dependencies=[Depends(require(Perm.LOTS_READ))])
def get_lot_verdict(lot_id: uuid.UUID, db: Session = Depends(get_db)) -> LotVerdictOut:
    """The lot verdict from the rolls inspected so far (each roll's latest finalized inspection; a supervisor's
    roll decision counts over the system verdict), and the supervisor's decision on the lot, if taken."""
    lot = _get_lot(db, lot_id)
    return _verdict_out(db, lot, svc.lot_summary(db, lot))


@router.post("/lots/{lot_id}/decision", response_model=LotVerdictOut)
def decide_lot(
    lot_id: uuid.UUID,
    body: LotDecisionIn,
    request: Request,
    actor: User = Depends(require(Perm.VERDICT_DECIDE)),
    db: Session = Depends(get_db),
) -> LotVerdictOut:
    """The supervisor's decision on the delivery (409 until the sample is inspected); audited."""
    lot = _get_lot(db, lot_id)
    try:
        summary = svc.decide_lot(db, lot, body.decision, body.reason, actor, ip=client_ip(request))
    except svc.ReceivingError as exc:
        raise _fail(exc) from exc
    db.commit()
    return _verdict_out(db, lot, summary)


@router.post("/lots/{lot_id}/rolls", response_model=list[RollOut], status_code=status.HTTP_201_CREATED)
def add_rolls(
    lot_id: uuid.UUID,
    body: RollsBulkCreate,
    request: Request,
    actor: User = Depends(require(Perm.ROLLS_WRITE)),
    db: Session = Depends(get_db),
) -> list[Roll]:
    lot = _get_lot(db, lot_id)
    try:
        rolls = svc.add_rolls(
            db, lot, [svc.NewRoll(**r.model_dump()) for r in body.rolls], actor, ip=client_ip(request)
        )
    except svc.ReceivingError as exc:
        raise _fail(exc) from exc
    db.commit()
    return rolls


@router.get(
    "/lots/{lot_id}/sampling-suggestion",
    response_model=SamplingSuggestionOut,
    dependencies=[Depends(require(Perm.LOTS_READ))],
)
def sampling_suggestion(lot_id: uuid.UUID, db: Session = Depends(get_db)) -> SamplingSuggestionOut:
    s = svc.sampling_suggestion(db, _get_lot(db, lot_id))
    return SamplingSuggestionOut(
        total_rolls=s.total_rolls,
        registered_rolls=s.registered_rolls,
        suggested_count=s.suggested_count,
        sampling_pct=s.sampling_pct,
        basis="profile",
        mill_recent_fail_rate=s.mill_recent_fail_rate,
        mill_recent_rolls=s.mill_recent_rolls,
    )


@router.get("/lots/{lot_id}/labels.pdf", response_class=Response, responses=PDF)
def lot_labels_pdf(
    lot_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require(Perm.LABELS_PRINT)),
    db: Session = Depends(get_db),
) -> Response:
    lot = _get_lot(db, lot_id)
    rolls = list(db.scalars(select(Roll).where(Roll.lot_id == lot.id).order_by(Roll.roll_code)))
    if not rolls:
        raise HTTPException(status.HTTP_409_CONFLICT, "this lot has no rolls yet")
    content = build_labels_pdf(_labels(db, rolls))
    svc.mark_labels_printed(db, rolls, actor, ip=client_ip(request))
    db.commit()
    return _pdf(content, f"labels-{lot.challan_no}.pdf")


# ------------------------------------------------------------------------------------------- rolls
@router.get("/rolls", response_model=list[RollOut], dependencies=[Depends(require(Perm.ROLLS_READ))])
def list_rolls(
    lot_id: uuid.UUID | None = None, status_filter: str | None = None, db: Session = Depends(get_db)
) -> list[Roll]:
    q = select(Roll).order_by(Roll.roll_code).limit(1000)
    if lot_id:
        q = q.where(Roll.lot_id == lot_id)
    if status_filter:
        q = q.where(Roll.status == status_filter)
    return list(db.scalars(q))


@router.get("/rolls/by-code/{roll_code}", response_model=RollOut, dependencies=[Depends(require(Perm.ROLLS_READ))])
def roll_by_code(roll_code: str, db: Session = Depends(get_db)) -> Roll:
    roll = db.scalar(select(Roll).where(Roll.roll_code == roll_code.strip().upper()))
    if roll is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no roll with this code")
    return roll


@router.get("/rolls/{roll_id}", response_model=RollOut, dependencies=[Depends(require(Perm.ROLLS_READ))])
def get_roll(roll_id: uuid.UUID, db: Session = Depends(get_db)) -> Roll:
    roll = db.get(Roll, roll_id)
    if roll is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "roll not found")
    return roll


@router.get("/rolls/{roll_id}/label.pdf", response_class=Response, responses=PDF)
def roll_label_pdf(
    roll_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require(Perm.LABELS_PRINT)),
    db: Session = Depends(get_db),
) -> Response:
    roll = get_roll(roll_id, db)
    content = build_labels_pdf(_labels(db, [roll]))
    svc.mark_labels_printed(db, [roll], actor, ip=client_ip(request))
    db.commit()
    return _pdf(content, f"label-{roll.roll_code}.pdf")
