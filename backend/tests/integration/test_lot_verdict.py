"""Lot verdict (PLAN.md §7.2 step 10) through the API: computed from the rolls' finalized verdicts, decided by a
supervisor, audited."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import login
from tests.integration.test_live_inspection import META, _run_to_end, _start
from threadeye.db.models import AuditLog
from threadeye.db.session import get_sessionmaker


def _lot(client: TestClient, challan: str, rolls: int) -> tuple[str, list[str]]:
    login(client, "store")
    supplier = client.get("/api/v1/suppliers").json()[0]["id"]
    buyer = client.get("/api/v1/buyers").json()[0]["id"]
    profile = next(p["id"] for p in client.get("/api/v1/rule-profiles").json() if p["name"] == "Simulator parity")
    lot = client.post(
        "/api/v1/lots",
        json={
            "challan_no": challan,
            "supplier_id": supplier,
            "buyer_id": buyer,
            "fabric_type": "Cotton twill",
            "received_at": "2026-10-26",
            "declared_rolls": rolls,
            "rule_profile_id": profile,
        },
    ).json()
    created = client.post(
        f"/api/v1/lots/{lot['id']}/rolls",
        json={
            "rolls": [
                {"mill_roll_no": f"R{i}", "declared_length_yd": 100, "declared_width_in": META["fabric_width_in"]}
                for i in range(rolls)
            ]
        },
    ).json()
    return lot["id"], [r["roll_code"] for r in created]


def _inspect_to_verdict(client: TestClient, roll_code: str) -> str:
    insp_id = _start(client, roll_code)["id"]
    _run_to_end(client, insp_id)
    assert client.post(f"/api/v1/inspections/{insp_id}/complete").status_code == 200
    defects: list[dict[str, Any]] = client.get(f"/api/v1/inspections/{insp_id}/defects").json()
    for d in defects:
        if d["kind"] == "defect" and d["status"] == "pending":
            client.post(f"/api/v1/defects/{d['id']}/confirm", json={}, headers={"Idempotency-Key": f"k-{d['id']}"})
    final = client.post(f"/api/v1/inspections/{insp_id}/finalize")
    assert final.status_code == 200, final.text
    assert final.json()["system_verdict"] == META["expected_score"]["verdict"] == "FAIL"
    return str(insp_id)


def test_lot_verdict_follows_the_rolls_and_a_supervisor_decides(client: TestClient) -> None:
    lot_id, codes = _lot(client, "CH-LOT-1", 2)

    # Nothing inspected yet: the sample is pending and no decision can be taken.
    login(client, "supervisor")
    v = client.get(f"/api/v1/lots/{lot_id}/verdict").json()
    assert (v["status"], v["required_sample"], v["inspected"], v["total_rolls"]) == ("PENDING_SAMPLE", 1, 0, 2)
    early = client.post(f"/api/v1/lots/{lot_id}/decision", json={"decision": "ACCEPT", "reason": "looks fine"})
    assert early.status_code == 409

    # One of two rolls fails: above the 20 % hold limit while rolls remain, so every roll must be inspected.
    insp_id = _inspect_to_verdict(client, codes[0])
    login(client, "supervisor")
    v = client.get(f"/api/v1/lots/{lot_id}/verdict").json()
    assert (v["status"], v["inspected"], v["failed"], v["fail_pct"]) == ("HOLD_INSPECT_ALL", 1, 1, 100.0)
    assert [(r["roll_code"], r["verdict"]) for r in v["rolls"]] == [(codes[0], "FAIL"), (codes[1], None)]

    # The supervisor's roll decision counts over the system verdict.
    client.post(f"/api/v1/inspections/{insp_id}/decision", json={"final_verdict": "ACCEPT", "reason": "minor, ok"})
    v = client.get(f"/api/v1/lots/{lot_id}/verdict").json()
    assert (v["status"], v["failed"]) == ("ACCEPT", 0) and v["rolls"][0]["verdict"] == "PASS"

    # Only a role that decides verdicts may decide the lot; the decision is kept with its verdict and audited.
    login(client, "store")
    denied = client.post(f"/api/v1/lots/{lot_id}/decision", json={"decision": "ACCEPT", "reason": "x" * 5})
    assert denied.status_code == 403
    login(client, "supervisor")
    r = client.post(f"/api/v1/lots/{lot_id}/decision", json={"decision": "ACCEPT", "reason": "sample passed"})
    assert r.status_code == 200, r.text
    d = r.json()["decision"]
    assert (d["decision"], d["reason"], d["lot_verdict"]) == ("ACCEPT", "sample passed", "ACCEPT")
    assert d["decided_by"] and d["decided_at"]
    assert client.get(f"/api/v1/lots/{lot_id}/verdict").json()["decision"]["decision"] == "ACCEPT"
    with get_sessionmaker()() as db:
        assert "lot.decision" in set(db.scalars(select(AuditLog.action)).all())


def test_a_failed_roll_counts_as_failed_when_accepted_with_a_claim(client: TestClient) -> None:
    lot_id, codes = _lot(client, "CH-LOT-2", 1)
    insp_id = _inspect_to_verdict(client, codes[0])
    login(client, "supervisor")
    claim = {"final_verdict": "ACCEPT_WITH_CLAIM", "reason": "claim"}
    assert client.post(f"/api/v1/inspections/{insp_id}/decision", json=claim).status_code == 200
    v = client.get(f"/api/v1/lots/{lot_id}/verdict").json()
    # Every roll inspected, the only one failed: above the 50 % reject limit.
    assert (v["status"], v["failed"], v["rolls"][0]["verdict"]) == ("REJECT", 1, "FAIL")


def test_supplier_scorecard_from_finalized_rolls(client: TestClient) -> None:
    _, codes = _lot(client, "CH-SCORE-1", 2)
    insp_id = _inspect_to_verdict(client, codes[0])  # FAIL, 46.45 points per 100 sq yd
    login(client, "supervisor")
    claim = {"final_verdict": "ACCEPT_WITH_CLAIM", "reason": "claim the mill"}
    assert client.post(f"/api/v1/inspections/{insp_id}/decision", json=claim).status_code == 200

    login(client, "store")
    assert client.get("/api/v1/suppliers/scorecard").status_code == 403  # not the store's business
    login(client, "merchandiser")
    cards = client.get("/api/v1/suppliers/scorecard").json()
    mill = next(m for m in cards if m["rolls_inspected"])
    assert (mill["rolls_inspected"], mill["acceptance"], mill["claims"]) == (1, 0.0, 1)
    assert mill["avg_points_per_100"] == META["expected_score"]["points_per_100_sq_yd"]
    assert len(mill["trend"]) == 6 and mill["trend"][-1]["rolls"] == 1  # this month
    assert mill["mix"] and abs(sum(x["share"] for x in mill["mix"]) - 100) < 0.5
    (delivery,) = mill["deliveries"]
    summary = (delivery["challan"], delivery["failed"], delivery["claims"], delivery["status"])
    assert summary == ("CH-SCORE-1", 1, 1, "review")
    assert delivery["claim_eligible"] is False and delivery["lot_decision"] is None
    # The roll covers less than the declared 100 yd: the gap is the shortage.
    assert delivery["shortage_yd"] > 0 and 0 < mill["shortage"] <= 1


def test_claim_pack_holds_the_letter_reports_photos_and_their_checksums(client: TestClient) -> None:
    import hashlib
    import io
    import json
    import zipfile

    lot_id, codes = _lot(client, "CH-CLAIM-1", 2)
    login(client, "merchandiser")
    assert client.get(f"/api/v1/lots/{lot_id}/claim-pack.zip").status_code == 409  # nothing failed yet
    insp_id = _inspect_to_verdict(client, codes[0])  # FAIL; its run captured frame 110 (the stain's photo)

    # Neither an automatic FAIL nor a signed roll claim bypasses the delivery decision.
    login(client, "merchandiser")
    assert client.get(f"/api/v1/lots/{lot_id}/claim-pack.zip").status_code == 409
    login(client, "supervisor")
    assert (
        client.post(
            f"/api/v1/lots/{lot_id}/decision", json={"decision": "REJECT", "reason": "bad delivery"}
        ).status_code
        == 200
    )
    login(client, "merchandiser")
    assert client.get(f"/api/v1/lots/{lot_id}/claim-pack.zip").status_code == 409
    login(client, "supervisor")
    assert (
        client.post(
            f"/api/v1/inspections/{insp_id}/decision", json={"final_verdict": "REJECT", "reason": "bad roll"}
        ).status_code
        == 200
    )
    for decision in ("ACCEPT", "INSPECT_ALL"):
        assert (
            client.post(
                f"/api/v1/lots/{lot_id}/decision", json={"decision": decision, "reason": "delivery review"}
            ).status_code
            == 200
        )
        login(client, "merchandiser")
        assert client.get(f"/api/v1/lots/{lot_id}/claim-pack.zip").status_code == 409
        login(client, "supervisor")
    decided = client.post(
        f"/api/v1/lots/{lot_id}/decision", json={"decision": "ACCEPT_WITH_REJECTS", "reason": "exclude bad roll"}
    )
    assert decided.json()["claim_eligible"] is True

    login(client, "store")
    assert client.get(f"/api/v1/lots/{lot_id}/claim-pack.zip").status_code == 403
    login(client, "merchandiser")
    cards = client.get("/api/v1/suppliers/scorecard").json()
    delivery = next(d for m in cards for d in m["deliveries"] if d["lot_id"] == lot_id)
    assert delivery["claim_eligible"] is True and delivery["lot_decision"] == "ACCEPT_WITH_REJECTS"
    r = client.get(f"/api/v1/lots/{lot_id}/claim-pack.zip")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert "claim-pack-CH-CLAIM-1.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"claim_letter.pdf", f"rolls/{codes[0]}/report.pdf", "manifest.json", "SHA256SUMS.txt"} <= names
    assert any(n.startswith(f"photos/{codes[0]}/") and n.endswith(".jpg") for n in names)
    assert z.read("claim_letter.pdf").startswith(b"%PDF")
    # Every checksum holds: the manifest's for every other file, SHA256SUMS for every file but itself.
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["audit_chain_head"] and manifest["inspections"].keys() == {codes[0]}
    for f in manifest["files"]:
        assert hashlib.sha256(z.read(f["path"])).hexdigest() == f["sha256"]
    sums = dict(reversed(line.split("  ")) for line in z.read("SHA256SUMS.txt").decode().splitlines())
    assert set(sums) == names - {"SHA256SUMS.txt"}
    assert all(hashlib.sha256(z.read(n)).hexdigest() == h for n, h in sums.items())
    with get_sessionmaker()() as db:
        assert "claim.pack" in set(db.scalars(select(AuditLog.action)).all())
