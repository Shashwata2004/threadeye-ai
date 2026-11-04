"""Register the three generated videos as sample rolls through the audited receiving API.

Idempotent by challan/mill-roll number. Requires the existing demo password in the
environment; never prints it or the session cookie. Does not run any inspection.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["demo_basic_roll", "demo_mixed_roll", "demo_challenge_roll"]
CHALLAN = "CH-DEMO-LINESCAN-20261104"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8099/api/v1")
    args = parser.parse_args()
    metas = {n: json.loads((ROOT / "data" / n / "roll_meta.json").read_text()) for n in NAMES}
    assert all(m["simulated"] for m in metas.values())
    with httpx.Client(base_url=args.api, timeout=30) as client:
        def get(path: str, **kwargs: object) -> object:
            response = client.get(path, **kwargs)
            response.raise_for_status()
            return response.json()

        def post(path: str, payload: dict) -> object:
            response = client.post(path, json=payload)
            response.raise_for_status()
            return response.json()

        post("/auth/login", {"username": "admin", "password": os.environ["THREADEYE_DEMO_PASSWORD"]})
        lot = next((v for v in get("/lots") if v["challan_no"] == CHALLAN), None)
        if lot is None:
            buyer = next(v for v in get("/buyers") if v["is_sample_data"])
            supplier = next(v for v in get("/suppliers") if v["is_sample_data"])
            lot = post("/lots", {"challan_no": CHALLAN, "supplier_id": supplier["id"], "buyer_id": buyer["id"],
                                "order_ref": "SIMULATED-DEMO-20261104", "fabric_type": "Simulated AITEX line-scan demo rolls",
                                "colour": "Greyscale demo", "received_at": "2026-11-04", "declared_rolls": 3,
                                "declared_total_yd": sum(m["roll_length_yd"] for m in metas.values()), "sampling_pct": 100})
        assert lot["is_sample_data"], "refusing to add simulated rolls to a non-sample challan"
        existing = {v["mill_roll_no"]: v for v in get("/rolls", params={"lot_id": lot["id"]})}
        missing = [{"mill_roll_no": n, "declared_length_yd": metas[n]["roll_length_yd"],
                    "declared_width_in": metas[n]["fabric_width_in"], "dye_lot": "SIMULATED"}
                   for n in NAMES if n not in existing]
        if missing:
            existing.update({v["mill_roll_no"]: v for v in post(f"/lots/{lot['id']}/rolls", {"rolls": missing})})
        result = {"challan": CHALLAN, "lot_id": lot["id"], "sample_data": True,
                  "rolls": [{"roll_code": existing[n]["roll_code"], "dataset_id": n,
                             "length_yd": metas[n]["roll_length_yd"], "width_in": metas[n]["fabric_width_in"]} for n in NAMES]}
        out = ROOT / "docs/model/demo-challan.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
