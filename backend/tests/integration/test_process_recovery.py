"""SIGKILL before/after committing real inspection transactions at five reproducible frame cuts."""

import json
import random
import signal
import subprocess
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import MICRO_ROLL
from tests.integration.test_live_inspection import _lot_with_roll, _start
from threadeye.db.models import Inspection, InspectionEvent
from threadeye.db.session import get_sessionmaker
from threadeye.services import live

pytestmark = pytest.mark.integration

CHILD = """
import os, signal, sys, uuid
from threadeye.db.session import get_sessionmaker
from threadeye.db.models import Inspection
from threadeye.services import live
with get_sessionmaker()() as db:
    inspection = live.lock(db, uuid.UUID(sys.argv[1]))
    live.advance(db, inspection, until_frame=int(sys.argv[2]), captures=[], session_id=inspection.driver_session_id)
    if sys.argv[3] == 'commit':
        db.commit()
    else:
        db.flush()
    os.kill(os.getpid(), signal.SIGKILL)
"""


@pytest.mark.parametrize("frame", random.Random(42).sample(range(5, 200), 5))
@pytest.mark.parametrize("mode", ["commit", "rollback"])
def test_sigkill_recovery_preserves_score_events_and_checkpoint(client: TestClient, frame: int, mode: str) -> None:
    id_ = _start(client, _lot_with_roll(client))["id"]
    result = subprocess.run(  # noqa: S603 -- controlled test child, no shell
        [sys.executable, "-c", CHILD, id_, str(frame), mode],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == -signal.SIGKILL, result.stderr.decode()
    live.clear_cache()
    with get_sessionmaker()() as db:
        inspection = db.get(Inspection, uuid.UUID(id_))
        assert inspection and inspection.checkpoint_frame == (frame if mode == "commit" else -1)
    assert (
        client.post(f"/api/v1/inspections/{id_}/advance", json={"until_frame": 204, "after_seq": 0}).status_code == 200
    )
    assert client.post(f"/api/v1/inspections/{id_}/complete").status_code == 200
    assert client.post(f"/api/v1/inspections/{id_}/defects/confirm-pending", json={}).status_code == 200
    response = client.post(f"/api/v1/inspections/{id_}/finalize")
    assert response.status_code == 200, response.text
    expected = json.loads((MICRO_ROLL / "roll_meta.json").read_text())["expected_score"]
    snapshot = response.json()
    assert snapshot["points_total"] == expected["total_points"]
    assert snapshot["points_per_100"] == pytest.approx(expected["points_per_100_sq_yd"], abs=0.01)
    assert snapshot["system_verdict"] == expected["verdict"]
    with get_sessionmaker()() as db:
        rows = list(
            db.scalars(
                select(InspectionEvent)
                .where(InspectionEvent.inspection_id == uuid.UUID(id_))
                .order_by(InspectionEvent.seq)
            )
        )
        assert [r.seq for r in rows] == list(range(1, len(rows) + 1))
        keys = [r.idempotency_key for r in rows]
        assert len(keys) == len(set(keys))
