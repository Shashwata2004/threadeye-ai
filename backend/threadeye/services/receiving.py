"""Receiving: register deliveries (lots) and rolls, suggest how many rolls to inspect.

Every mutation writes an audit row in the same transaction; the caller commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from threadeye.core.scoring.lot import LotResult, lot_verdict, required_sample
from threadeye.core.scoring.profile import LotRules, RuleProfile, default_profile, simulator_parity_profile
from threadeye.db import audit
from threadeye.db.models import (
    ROLL_CODE_SEQ,
    Buyer,
    Inspection,
    Lot,
    Machine,
    Roll,
    RuleProfileRow,
    Supplier,
    User,
)

DEFAULT_PROFILE_NAME = "Default 4-point"
PARITY_PROFILE_NAME = "Simulator parity"


class ReceivingError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------- profiles
def profile_of(row: RuleProfileRow) -> RuleProfile:
    return RuleProfile.model_validate(row.rules)


def resolve_profile(db: Session, buyer_id: uuid.UUID, profile_id: uuid.UUID | None) -> RuleProfileRow:
    if profile_id is not None:
        row = db.get(RuleProfileRow, profile_id)
        if row is None or row.status != "active":
            raise ReceivingError(422, "rule profile not found or not active")
        return row
    for_buyer = db.scalars(
        select(RuleProfileRow)
        .where(RuleProfileRow.buyer_id == buyer_id, RuleProfileRow.status == "active")
        .order_by(RuleProfileRow.version.desc())
    ).first()
    if for_buyer:
        return for_buyer
    default = db.scalars(
        select(RuleProfileRow)
        .where(
            RuleProfileRow.buyer_id.is_(None),
            RuleProfileRow.name == DEFAULT_PROFILE_NAME,
            RuleProfileRow.status == "active",
        )
        .order_by(RuleProfileRow.version.desc())
    ).first()
    if default is None:
        raise ReceivingError(422, "no active rule profile: run `threadeye seed-sample-data`")
    return default


# ------------------------------------------------------------------------------------------- lots
@dataclass(frozen=True)
class NewLot:
    challan_no: str
    supplier_id: uuid.UUID
    buyer_id: uuid.UUID
    order_ref: str | None
    fabric_type: str
    colour: str | None
    received_at: date
    declared_rolls: int
    declared_total_yd: float | None
    rule_profile_id: uuid.UUID | None
    sampling_pct: float | None


def create_lot(db: Session, new: NewLot, actor: User, *, ip: str | None = None) -> Lot:
    supplier = db.get(Supplier, new.supplier_id)
    buyer = db.get(Buyer, new.buyer_id)
    if supplier is None:
        raise ReceivingError(422, "unknown supplier (mill)")
    if buyer is None:
        raise ReceivingError(422, "unknown buyer")
    exists = db.scalar(select(Lot.id).where(Lot.supplier_id == supplier.id, Lot.challan_no == new.challan_no.strip()))
    if exists:
        raise ReceivingError(409, "this challan is already registered for this mill")
    profile_row = resolve_profile(db, buyer.id, new.rule_profile_id)
    sampling = new.sampling_pct if new.sampling_pct is not None else profile_of(profile_row).lot.min_sample_pct
    lot = Lot(
        challan_no=new.challan_no.strip(),
        supplier_id=supplier.id,
        buyer_id=buyer.id,
        order_ref=new.order_ref,
        fabric_type=new.fabric_type.strip(),
        colour=new.colour,
        received_at=new.received_at,
        declared_rolls=new.declared_rolls,
        declared_total_yd=new.declared_total_yd,
        rule_profile_id=profile_row.id,
        sampling_pct=sampling,
        is_sample_data=supplier.is_sample_data or buyer.is_sample_data,
        created_by=actor.id,
    )
    db.add(lot)
    db.flush()
    audit.record(
        db,
        action="lot.create",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="lot",
        entity_id=str(lot.id),
        after={"challan_no": lot.challan_no, "supplier": supplier.name, "declared_rolls": lot.declared_rolls},
        ip=ip,
    )
    return lot


@dataclass(frozen=True)
class NewRoll:
    mill_roll_no: str
    dye_lot: str | None
    declared_length_yd: float
    declared_width_in: float
    gsm: float | None


def next_roll_code(db: Session) -> str:
    n = db.scalar(select(ROLL_CODE_SEQ.next_value()))
    if n is None:
        raise RuntimeError("roll code sequence returned nothing")
    return f"TE-{int(n):06d}"


def add_rolls(db: Session, lot: Lot, rolls: Sequence[NewRoll], actor: User, *, ip: str | None = None) -> list[Roll]:
    numbers = [r.mill_roll_no.strip() for r in rolls]
    if len(set(numbers)) != len(numbers):
        raise ReceivingError(409, "the same mill roll number appears twice in this batch")
    clash = db.scalars(select(Roll.mill_roll_no).where(Roll.lot_id == lot.id, Roll.mill_roll_no.in_(numbers))).all()
    if clash:
        raise ReceivingError(409, f"already registered in this lot: {', '.join(sorted(clash))}")
    created = []
    for r, number in zip(rolls, numbers, strict=True):
        roll = Roll(
            lot_id=lot.id,
            roll_code=next_roll_code(db),
            mill_roll_no=number,
            dye_lot=r.dye_lot,
            declared_length_yd=r.declared_length_yd,
            declared_width_in=r.declared_width_in,
            gsm=r.gsm,
            is_sample_data=lot.is_sample_data,
        )
        db.add(roll)
        created.append(roll)
    db.flush()
    audit.record(
        db,
        action="rolls.create",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="lot",
        entity_id=str(lot.id),
        after={"roll_codes": [r.roll_code for r in created]},
        ip=ip,
    )
    return created


def roll_count(db: Session, lot_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.count()).select_from(Roll).where(Roll.lot_id == lot_id)) or 0)


@dataclass(frozen=True)
class SamplingSuggestion:
    total_rolls: int
    registered_rolls: int
    suggested_count: int
    sampling_pct: float
    mill_recent_fail_rate: float | None
    mill_recent_rolls: int


def sampling_suggestion(db: Session, lot: Lot) -> SamplingSuggestion:
    profile_row = db.get(RuleProfileRow, lot.rule_profile_id)
    rules = profile_of(profile_row).lot if profile_row else default_profile().lot
    rules = rules.model_copy(update={"min_sample_pct": lot.sampling_pct})
    total = max(lot.declared_rolls, roll_count(db, lot.id))
    # Mill history: completed inspections of this mill's rolls (verdicts arrive in M2).
    recent = db.scalar(
        select(func.count())
        .select_from(Inspection)
        .join(Roll, Roll.id == Inspection.roll_id)
        .join(Lot, Lot.id == Roll.lot_id)
        .where(Lot.supplier_id == lot.supplier_id, Inspection.status == "completed")
    )
    return SamplingSuggestion(
        total_rolls=total,
        registered_rolls=roll_count(db, lot.id),
        suggested_count=required_sample(total, rules),
        sampling_pct=lot.sampling_pct,
        mill_recent_fail_rate=None,
        mill_recent_rolls=int(recent or 0),
    )


def mark_labels_printed(db: Session, rolls: Sequence[Roll], actor: User, *, ip: str | None = None) -> None:
    now = datetime.now(UTC)
    for r in rolls:
        r.label_printed_at = now
    audit.record(
        db,
        action="labels.print",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="roll",
        entity_id=",".join(r.roll_code for r in rolls)[:128],
        after={"count": len(rolls)},
        ip=ip,
    )


# ------------------------------------------------------------------------------------------- lot verdict
ROLL_FAILED_DECISIONS = frozenset({"REJECT", "ACCEPT_WITH_CLAIM"})
"""A supervisor's roll decisions that count as a failed roll for the lot: accepted with a claim is still a roll
the mill delivered below standard."""
LOT_DECISIONS = ("ACCEPT", "ACCEPT_WITH_REJECTS", "REJECT", "INSPECT_ALL")


def roll_verdict(insp: Inspection) -> str | None:
    """PASS | FAIL | BORDERLINE of a finalized inspection: the supervisor's decision when there is one."""
    if insp.final_verdict:
        return "FAIL" if insp.final_verdict in ROLL_FAILED_DECISIONS else "PASS"
    return insp.system_verdict


@dataclass(frozen=True)
class LotRoll:
    roll: Roll
    inspection: Inspection | None
    """The roll's latest finalized inspection."""
    verdict: str | None


@dataclass(frozen=True)
class LotSummary:
    result: LotResult
    total_rolls: int
    rules: LotRules
    rolls: list[LotRoll]


def lot_summary(db: Session, lot: Lot) -> LotSummary:
    """The lot verdict from the verdicts of its rolls (each roll's latest finalized inspection), under the lot's
    rule profile. The delivery counts as many rolls as declared, or as registered if more."""
    rolls = list(db.scalars(select(Roll).where(Roll.lot_id == lot.id).order_by(Roll.roll_code)))
    latest: dict[uuid.UUID, Inspection] = {}
    if rolls:
        done = db.scalars(
            select(Inspection)
            .where(Inspection.roll_id.in_([r.id for r in rolls]), Inspection.finalized_at.is_not(None))
            .order_by(Inspection.finalized_at)
        )
        for insp in done:
            latest[insp.roll_id] = insp
    items = [LotRoll(r, latest.get(r.id), roll_verdict(latest[r.id]) if r.id in latest else None) for r in rolls]
    row = db.get(RuleProfileRow, lot.rule_profile_id)
    rules = profile_of(row).lot if row else default_profile().lot
    total = max(lot.declared_rolls, len(rolls))
    result = lot_verdict(total, [i.verdict for i in items if i.verdict], rules)
    return LotSummary(result, total, rules, items)


def decide_lot(db: Session, lot: Lot, decision: str, reason: str, actor: User, *, ip: str | None = None) -> LotSummary:
    """The supervisor's decision on the delivery. Not before the sample is inspected; the verdict it was taken
    on is kept with it."""
    if decision not in LOT_DECISIONS:
        raise ReceivingError(422, f"unknown lot decision {decision!r}")
    summary = lot_summary(db, lot)
    if summary.result.status == "PENDING_SAMPLE":
        raise ReceivingError(
            409, f"inspect the sample first: {summary.result.inspected} of {summary.result.required_sample} rolls"
        )
    before = {"decision": lot.decision, "lot_verdict": lot.lot_verdict}
    lot.decision = decision
    lot.decision_reason = reason
    lot.decision_by = actor.id
    lot.decision_at = datetime.now(UTC)
    lot.lot_verdict = summary.result.status
    audit.record(
        db,
        action="lot.decision",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="lot",
        entity_id=str(lot.id),
        before=before,
        after={"decision": decision, "reason": reason, "lot_verdict": summary.result.status,
               "inspected": summary.result.inspected, "failed": summary.result.failed},
        ip=ip,
    )
    return summary


# ------------------------------------------------------------------------------------------- seed
SAMPLE_SUPPLIERS = (
    ("Sample Mill A, Shaoxing (fictional)", "China"),
    ("Sample Mill B, Narayanganj (fictional)", "Bangladesh"),
)
SAMPLE_BUYERS = ("Sample Buyer (fictional brand)",)


def seed_sample_data(db: Session) -> list[str]:
    """Rule profiles, one machine and clearly fictional mills/buyers. Safe to run again."""
    created: list[str] = []
    for profile in (default_profile(), simulator_parity_profile()):
        if not db.scalar(select(RuleProfileRow.id).where(RuleProfileRow.name == profile.name)):
            db.add(
                RuleProfileRow(
                    name=profile.name,
                    version=1,
                    status="active",
                    rules=profile.model_dump(mode="json"),
                    rules_hash=profile.rules_hash(),
                )
            )
            created.append(f"profile:{profile.name}")
    if not db.scalar(select(Machine.id).where(Machine.code == "M-01")):
        db.add(Machine(code="M-01", name="Inspection machine 1"))
        created.append("machine:M-01")
    for name, country in SAMPLE_SUPPLIERS:
        if not db.scalar(select(Supplier.id).where(Supplier.name == name)):
            db.add(Supplier(name=name, country=country, is_sample_data=True))
            created.append(f"supplier:{name}")
    for name in SAMPLE_BUYERS:
        if not db.scalar(select(Buyer.id).where(Buyer.name == name)):
            db.add(Buyer(name=name, is_sample_data=True))
            created.append(f"buyer:{name}")
    if created:
        db.flush()
        audit.record(db, action="system.seed_sample_data", entity_type="seed", after={"created": created})
    db.commit()
    return created
