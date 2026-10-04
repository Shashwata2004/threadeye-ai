"""M1 acceptance (backend side): register a delivery with 5 rolls and print their QR labels."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import login
from threadeye.db.models import AuditLog, Roll
from threadeye.db.session import get_sessionmaker

pytestmark = pytest.mark.integration


def refs(client: TestClient) -> tuple[str, str]:
    supplier = client.get("/api/v1/suppliers").json()[0]["id"]
    buyer = client.get("/api/v1/buyers").json()[0]["id"]
    return supplier, buyer


def new_lot(client: TestClient, challan: str = "CH-2026-0042", rolls: int = 5) -> dict:  # type: ignore[type-arg]
    supplier, buyer = refs(client)
    r = client.post(
        "/api/v1/lots",
        json={
            "challan_no": challan,
            "supplier_id": supplier,
            "buyer_id": buyer,
            "fabric_type": "Cotton twill 3/1",
            "colour": "Navy",
            "received_at": "2026-10-04",
            "declared_rolls": rolls,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


ROLLS = [
    {"mill_roll_no": f"R{i:02d}", "declared_length_yd": 100 + i, "declared_width_in": 58, "dye_lot": "DL7"}
    for i in range(1, 6)
]


def test_register_a_five_roll_lot_and_print_labels(client: TestClient) -> None:
    login(client, "store")
    lot = new_lot(client)
    assert lot["rule_profile"]["name"] == "Default 4-point"
    assert lot["sampling_pct"] == 10.0
    assert lot["is_sample_data"] is True  # fictional mill and buyer propagate the flag
    assert lot["status"] == "registered"

    r = client.post(f"/api/v1/lots/{lot['id']}/rolls", json={"rolls": ROLLS})
    assert r.status_code == 201, r.text
    rolls = r.json()
    codes = [x["roll_code"] for x in rolls]
    assert len(set(codes)) == 5 and all(c.startswith("TE-") and len(c) == 9 for c in codes)
    assert client.get(f"/api/v1/lots/{lot['id']}").json()["rolls_registered"] == 5

    s = client.get(f"/api/v1/lots/{lot['id']}/sampling-suggestion").json()
    assert (s["total_rolls"], s["suggested_count"], s["registered_rolls"]) == (5, 1, 5)

    pdf = client.get(f"/api/v1/lots/{lot['id']}/labels.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
    assert pdf.content.count(b"/Type /Page\n") == 5 or pdf.content.count(b"/Type /Page") >= 5
    one = client.get(f"/api/v1/rolls/{rolls[0]['id']}/label.pdf")
    assert one.status_code == 200 and one.content.startswith(b"%PDF-")

    found = client.get(f"/api/v1/rolls/by-code/{codes[2].lower()}")
    assert found.status_code == 200 and found.json()["mill_roll_no"] == "R03"

    with get_sessionmaker()() as db:
        printed = db.scalars(select(Roll.label_printed_at).where(Roll.lot_id == lot["id"])).all()
        actions = set(db.scalars(select(AuditLog.action)).all())
    assert all(printed)
    assert {"lot.create", "rolls.create", "labels.print"} <= actions


def test_receiving_rejects_duplicates_and_bad_references(client: TestClient) -> None:
    login(client, "store")
    lot = new_lot(client, "CH-DUP")
    supplier, buyer = refs(client)
    again = client.post(
        "/api/v1/lots",
        json={
            "challan_no": "CH-DUP",
            "supplier_id": supplier,
            "buyer_id": buyer,
            "fabric_type": "x",
            "received_at": "2026-10-04",
            "declared_rolls": 1,
        },
    )
    assert again.status_code == 409
    bad = client.post(
        "/api/v1/lots",
        json={
            "challan_no": "CH-X",
            "supplier_id": buyer,
            "buyer_id": buyer,
            "fabric_type": "x",
            "received_at": "2026-10-04",
            "declared_rolls": 1,
        },
    )
    assert bad.status_code == 422
    assert client.post(f"/api/v1/lots/{lot['id']}/rolls", json={"rolls": ROLLS[:2]}).status_code == 201
    assert client.post(f"/api/v1/lots/{lot['id']}/rolls", json={"rolls": ROLLS[1:3]}).status_code == 409
    twice = [ROLLS[3], ROLLS[3]]
    assert client.post(f"/api/v1/lots/{lot['id']}/rolls", json={"rolls": twice}).status_code == 409
    assert client.get(f"/api/v1/lots/{lot['id']}/labels.pdf").status_code == 200


def test_labels_need_rolls_and_permissions(client: TestClient) -> None:
    login(client, "store")
    lot = new_lot(client, "CH-EMPTY", rolls=3)
    assert client.get(f"/api/v1/lots/{lot['id']}/labels.pdf").status_code == 409
    login(client, "inspector")
    assert client.get("/api/v1/lots").status_code == 200  # read
    assert client.get(f"/api/v1/lots/{lot['id']}/labels.pdf").status_code == 403
    supplier, buyer = refs(client)
    r = client.post(
        "/api/v1/lots",
        json={
            "challan_no": "CH-NO",
            "supplier_id": supplier,
            "buyer_id": buyer,
            "fabric_type": "x",
            "received_at": "2026-10-04",
            "declared_rolls": 1,
        },
    )
    assert r.status_code == 403


def test_master_data_endpoints(client: TestClient) -> None:
    login(client, "merchandiser")
    assert any("fictional" in s["name"] for s in client.get("/api/v1/suppliers").json())
    r = client.post("/api/v1/suppliers", json={"name": "Real Mill Ltd", "country": "China"})
    assert r.status_code == 201 and r.json()["is_sample_data"] is False
    assert client.post("/api/v1/suppliers", json={"name": "real mill ltd"}).status_code == 409
    assert [m["code"] for m in client.get("/api/v1/machines").json()] == ["M-01"]
    names = {p["name"] for p in client.get("/api/v1/rule-profiles").json()}
    assert {"Default 4-point", "Simulator parity"} <= names
