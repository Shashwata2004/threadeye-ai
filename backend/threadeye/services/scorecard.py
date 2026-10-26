"""Supplier (mill) scorecards (M5): how each mill's deliveries fared, from the finalized inspections.

Per mill: the share of inspected rolls that passed, the mean points per 100 sq yd, the rolls the supervisor
accepted with a claim or rejected (the claims raised against the mill), the yardage shortage (declared length
against the yards inspected), a monthly trend, the mix of confirmed defect classes and every delivery. Only
each roll's latest finalized inspection counts.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from threadeye.db.models import DefectRow, Inspection, Lot, Roll, Supplier
from threadeye.services.receiving import roll_verdict

CLAIM_DECISIONS = frozenset({"ACCEPT_WITH_CLAIM", "REJECT"})
TREND_MONTHS = 6


@dataclass
class DeliveryCard:
    lot_id: uuid.UUID
    challan: str
    received: date
    fabric: str
    passed: int = 0
    review: int = 0
    failed: int = 0
    points: list[float] = field(default_factory=list)
    shortage_yd: float = 0.0
    claims: int = 0
    status: str = "review"
    """accepted | review | rejected: from the supervisor's lot decision (review until there is one)."""

    @property
    def avg_points(self) -> float | None:
        return round(sum(self.points) / len(self.points), 2) if self.points else None


@dataclass
class MillCard:
    id: uuid.UUID
    name: str
    country: str | None
    deliveries: list[DeliveryCard] = field(default_factory=list)
    by_month: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    mix: Counter[str] = field(default_factory=Counter)
    declared_yd: float = 0.0
    short_yd: float = 0.0

    @property
    def rolls(self) -> int:
        return sum(d.passed + d.review + d.failed for d in self.deliveries)

    @property
    def acceptance(self) -> float | None:
        return round(sum(d.passed for d in self.deliveries) / self.rolls, 4) if self.rolls else None

    @property
    def avg_points(self) -> float | None:
        pts = [p for d in self.deliveries for p in d.points]
        return round(sum(pts) / len(pts), 2) if pts else None

    @property
    def claims(self) -> int:
        return sum(d.claims for d in self.deliveries)

    def month_avg(self, month: str) -> float | None:
        pts = self.by_month.get(month, [])
        return round(sum(pts) / len(pts), 2) if pts else None

    @property
    def shortage(self) -> float | None:
        return round(self.short_yd / self.declared_yd, 4) if self.declared_yd else None


def _status(lot: Lot) -> str:
    if lot.decision in ("ACCEPT", "ACCEPT_WITH_REJECTS"):
        return "accepted"
    if lot.decision == "REJECT":
        return "rejected"
    return "review"


def months_back(today: date, n: int = TREND_MONTHS) -> list[str]:
    """The last ``n`` months as YYYY-MM, oldest first, ending with this month."""
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def scorecards(db: Session) -> list[MillCard]:
    mills = {s.id: MillCard(s.id, s.name, s.country) for s in db.scalars(select(Supplier).order_by(Supplier.name))}
    lots = {lot.id: lot for lot in db.scalars(select(Lot))}
    rolls = {r.id: r for r in db.scalars(select(Roll))}
    latest: dict[uuid.UUID, Inspection] = {}
    done = select(Inspection).where(Inspection.finalized_at.is_not(None)).order_by(Inspection.finalized_at)
    for insp in db.scalars(done):
        latest[insp.roll_id] = insp
    cards: dict[uuid.UUID, DeliveryCard] = {}
    for roll_id, insp in latest.items():
        roll = rolls.get(roll_id)
        lot = lots.get(roll.lot_id) if roll else None
        mill = mills.get(lot.supplier_id) if lot else None
        if roll is None or lot is None or mill is None:
            continue
        card = cards.get(lot.id)
        if card is None:
            card = cards[lot.id] = DeliveryCard(lot.id, lot.challan_no, lot.received_at, lot.fabric_type,
                                                status=_status(lot))
            mill.deliveries.append(card)
        verdict = roll_verdict(insp)
        if verdict == "PASS":
            card.passed += 1
        elif verdict == "FAIL":
            card.failed += 1
        else:
            card.review += 1
        if insp.points_per_100 is not None:
            card.points.append(float(insp.points_per_100))
            assert insp.finalized_at is not None
            mill.by_month[insp.finalized_at.strftime("%Y-%m")].append(float(insp.points_per_100))
        if insp.final_verdict in CLAIM_DECISIONS:
            card.claims += 1
        if insp.yards_inspected is not None:
            short = max(0.0, roll.declared_length_yd - float(insp.yards_inspected))
            card.shortage_yd = round(card.shortage_yd + short, 2)
            mill.declared_yd += roll.declared_length_yd
            mill.short_yd += short
    if latest:
        for cls, roll_id in db.execute(
            select(DefectRow.current_cls, Inspection.roll_id)
            .join(Inspection, Inspection.id == DefectRow.inspection_id)
            .where(
                DefectRow.inspection_id.in_([i.id for i in latest.values()]),
                DefectRow.kind == "defect",
                DefectRow.status == "confirmed",
            )
        ).all():
            lot = lots[rolls[roll_id].lot_id]
            mills[lot.supplier_id].mix[cls] += 1
    for mill in mills.values():
        mill.deliveries.sort(key=lambda d: d.received, reverse=True)
    return list(mills.values())
