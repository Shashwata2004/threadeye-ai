"""Event store: one-transaction projections, gap-free seq, idempotent re-processing, append-only."""

from __future__ import annotations

import psycopg
import pytest
import sqlalchemy.exc
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tests.conftest import MICRO_ROLL
from threadeye.core.providers import ProviderContext
from threadeye.core.runner import RollSpec, Runner
from threadeye.core.scoring.profile import simulator_parity_profile
from threadeye.datasets.answer_key import load_answer_key
from threadeye.db.models import DefectRow, Inspection, InspectionEvent, Lot, Roll, RuleProfileRow, Supplier
from threadeye.db.session import get_engine, get_sessionmaker
from threadeye.providers.simulated import PERFECT, SimulatedDetector
from threadeye.services.inspection_store import append_events, events_after
from threadeye.sources.simulated_roll import TrackFrameSource

pytestmark = pytest.mark.integration


def make_inspection(db: Session) -> Inspection:
    supplier = db.scalars(select(Supplier)).first()
    profile = db.scalars(select(RuleProfileRow).where(RuleProfileRow.name == "Simulator parity")).one()
    assert supplier
    from threadeye.db.models import Buyer

    buyer = db.scalars(select(Buyer)).first()
    assert buyer
    lot = Lot(
        challan_no="EV-1",
        supplier_id=supplier.id,
        buyer_id=buyer.id,
        fabric_type="twill",
        received_at=__import__("datetime").date(2026, 10, 4),
        declared_rolls=1,
        rule_profile_id=profile.id,
        sampling_pct=10,
    )
    db.add(lot)
    db.flush()
    roll = Roll(
        lot_id=lot.id, roll_code="TE-990001", mill_roll_no="R1", declared_length_yd=3.0, declared_width_in=59.06
    )
    db.add(roll)
    db.flush()
    insp = Inspection(
        roll_id=roll.id,
        rule_profile_id=profile.id,
        provider_snapshot={"provider": "simulated@1.0.0"},
        source_descriptor={"dataset": "micro_roll"},
    )
    db.add(insp)
    db.commit()
    return insp


def runner(inspection_id: str) -> Runner:
    key = load_answer_key(MICRO_ROLL, require_media=False)
    src = TrackFrameSource(MICRO_ROLL)
    m = src.parsed.meta
    return Runner(
        src,
        SimulatedDetector(PERFECT, ProviderContext(answer_key=key)),
        simulator_parity_profile(),
        RollSpec(width_in=m.fabric_width_in, declared_length_yd=m.roll_length_yd),
        inspection_id=inspection_id,
    )


def test_events_and_projection_in_one_transaction(seeded: None) -> None:
    with get_sessionmaker()() as db:
        insp = make_inspection(db)
        r = runner(str(insp.id))
        events = r.run_to_end()
        result = append_events(db, insp.id, events, checkpoint_frame=r.checkpoint)
        db.commit()
        assert result.written == len(events) and result.skipped == 0

        seqs = db.scalars(select(InspectionEvent.seq).where(InspectionEvent.inspection_id == insp.id)).all()
        assert sorted(seqs) == list(range(1, len(events) + 1))  # gap-free
        defects = db.scalars(select(DefectRow).where(DefectRow.inspection_id == insp.id)).all()
        assert sorted((d.defect_no, d.kind) for d in defects) == [
            ("D-01", "defect"),
            ("D-02", "defect"),
            ("D-03", "nondefect"),
            ("D-04", "defect"),
        ]
        db.refresh(insp)
        assert insp.last_seq == len(events) and insp.checkpoint_frame == 204

        # Re-processing the same frames (e.g. after a crash) writes nothing new.
        again = append_events(db, insp.id, runner(str(insp.id)).run_to_end())
        db.commit()
        assert again.written == 0 and again.skipped == len(events)
        assert len(events_after(db, insp.id, after_seq=len(events) - 3)) == 3


def test_a_failed_transaction_leaves_nothing_behind(seeded: None) -> None:
    with get_sessionmaker()() as db:
        insp = make_inspection(db)
        append_events(db, insp.id, runner(str(insp.id)).run_to_end())
        db.rollback()  # the power cut happens before commit
        n_events = db.scalar(select(func.count()).select_from(InspectionEvent))
        n_defects = db.scalar(select(func.count()).select_from(DefectRow))
        db.refresh(insp)
        assert (n_events, n_defects, insp.last_seq) == (0, 0, 0)


def test_inspection_events_are_append_only(seeded: None) -> None:
    with get_sessionmaker()() as db:
        insp = make_inspection(db)
        append_events(db, insp.id, runner(str(insp.id)).run_to_end())
        db.commit()
    for sql in (
        "UPDATE threadeye.inspection_events SET type = 'x'",
        "DELETE FROM threadeye.inspection_events",
        "TRUNCATE threadeye.inspection_events CASCADE",
    ):
        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc, get_engine().begin() as conn:
            conn.execute(text(sql))
        assert isinstance(exc.value.orig, psycopg.errors.InsufficientPrivilege)
