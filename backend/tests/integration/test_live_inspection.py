"""M2 acceptance (API side): the core flow on a simulated roll, driven through the HTTP API.

load roll → start → advance (browser-clocked, with evidence captures) → confirm/reject/change type →
finish → verdict → report. With the perfect preset and the simulator-parity profile the verdict must
equal ``roll_meta.expected_score`` of the micro-fixture exactly (7 points, 142.24, FAIL).
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from tests.conftest import MICRO_ROLL, SAMPLE_ROLL, TEST_PASSWORD, login
from threadeye.api.app import create_app
from threadeye.db.models import AuditLog, InspectionEvent
from threadeye.db.session import get_sessionmaker
from threadeye.services import datasets, live

pytestmark = pytest.mark.integration

META = json.loads((MICRO_ROLL / "roll_meta.json").read_text())


def _lot_with_roll(client: TestClient, *, profile: str = "Simulator parity", width_in: float | None = None) -> str:
    login(client, "store")
    supplier = client.get("/api/v1/suppliers").json()[0]["id"]
    buyer = client.get("/api/v1/buyers").json()[0]["id"]
    profile_id = next(p["id"] for p in client.get("/api/v1/rule-profiles").json() if p["name"] == profile)
    lot = client.post(
        "/api/v1/lots",
        json={
            "challan_no": f"CH-LIVE-{profile[:3]}",
            "supplier_id": supplier,
            "buyer_id": buyer,
            "fabric_type": "Cotton twill",
            "received_at": "2026-10-05",
            "declared_rolls": 1,
            "rule_profile_id": profile_id,
        },
    ).json()
    rolls = client.post(
        f"/api/v1/lots/{lot['id']}/rolls",
        json={
            "rolls": [
                {
                    "mill_roll_no": "R01",
                    "declared_length_yd": 100,
                    "declared_width_in": width_in or META["fabric_width_in"],
                }
            ]
        },
    ).json()
    return str(rolls[0]["roll_code"])


def _start(client: TestClient, roll_code: str, preset: str = "perfect") -> dict[str, Any]:
    login(client, "inspector")
    machine = client.get("/api/v1/machines").json()[0]["id"]
    r = client.post(
        "/api/v1/inspections",
        json={"roll_code": roll_code, "machine_id": machine, "source": {"dataset_id": "micro_roll"}, "preset": preset},
    )
    assert r.status_code == 201, r.text
    insp = r.json()
    r = client.post(f"/api/v1/inspections/{insp['id']}/start")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _jpeg(w: int = 960, h: int = 504) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 190, 170)).save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _run_to_end(client: TestClient, insp_id: str, cuts: tuple[int, ...] = (40, 120, 204)) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    after = 0
    for until in cuts:
        captures = [{"frame": 110, "jpeg_b64": _jpeg(), "width": 960, "height": 504}] if until == 120 else []
        r = client.post(
            f"/api/v1/inspections/{insp_id}/advance",
            json={"until_frame": until, "after_seq": after, "captures": captures},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        seen += body["events"]
        after = body["last_seq"]
        assert body["checkpoint_frame"] == until
    return seen


def test_core_flow_reproduces_the_expected_score(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    snap = _start(client, roll_code)
    insp_id = snap["id"]
    assert snap["status"] == "running" and snap["driver_session"] is True
    assert snap["is_simulated"] is True and snap["provider"]["provider_id"] == "simulated"

    track = client.get(f"/api/v1/inspections/{insp_id}/track").json()
    assert track["frame_count"] == META["frames"] and len(track["roll_y_top_px"]) == META["frames"]
    plan = client.get(f"/api/v1/inspections/{insp_id}/plan").json()
    assert plan["frames"] and plan["frames"][-1] == META["frames"] - 1

    events = _run_to_end(client, insp_id)
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # gap-free, in order
    assert all(e["simulated"] is True for e in events)
    assert {"frame.sampled", "detection.batch", "defect.upserted", "score.updated"} <= {e["type"] for e in events}

    # Re-sending the same advance writes nothing (idempotent; e.g. a retry after a dropped response).
    again = client.post(f"/api/v1/inspections/{insp_id}/advance", json={"until_frame": 204, "after_seq": seqs[-1]})
    assert again.status_code == 200 and again.json()["events"] == []

    defects = client.get(f"/api/v1/inspections/{insp_id}/defects").json()
    real = [d for d in defects if d["kind"] == "defect"]
    assert len(real) == 3 and all(d["status"] == "pending" for d in real)
    assert {d["nondefect_category"] for d in defects if d["kind"] == "nondefect"} >= {"loose_thread"}

    # Evidence photo: the stain (D2, ~1.6 yd) is in view in the captured frame 110.
    stain = next(d for d in real if d["current_cls"] == "stain")
    assert stain["crop_url"]
    crop = client.get(stain["crop_url"])
    assert crop.status_code == 200 and crop.content.startswith(b"\xff\xd8")

    # The verdict is blocked while defects are pending.
    assert client.post(f"/api/v1/inspections/{insp_id}/complete").status_code == 200
    blocked = client.post(f"/api/v1/inspections/{insp_id}/finalize")
    assert blocked.status_code == 409 and blocked.json()["detail"]["pending"] == 3

    for d in real:
        r = client.post(f"/api/v1/defects/{d['id']}/confirm", json={}, headers={"Idempotency-Key": f"k-{d['id']}"})
        assert r.status_code == 200 and r.json()["status"] == "confirmed"
    with get_sessionmaker()() as db:
        n_events = db.scalar(select(func.count()).select_from(InspectionEvent))
    retry = client.post(
        f"/api/v1/defects/{real[0]['id']}/confirm", json={}, headers={"Idempotency-Key": f"k-{real[0]['id']}"}
    )
    assert retry.status_code == 200
    with get_sessionmaker()() as db:
        assert db.scalar(select(func.count()).select_from(InspectionEvent)) == n_events  # retry wrote nothing

    final = client.post(f"/api/v1/inspections/{insp_id}/finalize")
    assert final.status_code == 200, final.text
    v = final.json()
    expected = META["expected_score"]
    assert v["system_verdict"] == expected["verdict"]
    assert v["points_total"] == expected["total_points"]
    assert v["points_per_100"] == pytest.approx(expected["points_per_100_sq_yd"], abs=0.005)
    assert v["status"] == "completed" and v["finalized_at"]

    # A supervisor records the decision; the change ledger has every step.
    login(client, "supervisor")
    d = client.post(
        f"/api/v1/inspections/{insp_id}/decision", json={"final_verdict": "REJECT", "reason": "fails 4-point"}
    )
    assert d.status_code == 200 and d.json()["final_verdict"] == "REJECT"
    signed = d.json()
    with get_sessionmaker()() as db:
        signed_events = db.scalar(select(func.count()).select_from(InspectionEvent))
    retry = client.post(
        f"/api/v1/inspections/{insp_id}/decision", json={"final_verdict": "REJECT", "reason": "fails 4-point"}
    )
    assert retry.status_code == 200 and retry.json()["decision_at"] == signed["decision_at"]
    for changed in [
        {"final_verdict": "ACCEPT", "reason": "accept it instead"},
        {"final_verdict": "REJECT", "reason": "a different reason"},
    ]:
        assert client.post(f"/api/v1/inspections/{insp_id}/decision", json=changed).status_code == 409
    persisted = client.get(f"/api/v1/inspections/{insp_id}").json()
    assert persisted["final_verdict"] == "REJECT" and persisted["decision_reason"] == "fails 4-point"
    assert persisted["decision_at"] == signed["decision_at"]
    with get_sessionmaker()() as db:
        assert db.scalar(select(func.count()).select_from(InspectionEvent)) == signed_events
    with get_sessionmaker()() as db:
        actions = set(db.scalars(select(AuditLog.action)).all())
    assert {"inspection.create", "defect.confirm", "inspection.complete", "inspection.finalize"} <= actions
    assert "inspection.decision" in actions

    report = client.get(f"/api/v1/inspections/{insp_id}/report.pdf")
    assert report.status_code == 200 and report.content.startswith(b"%PDF-")
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-", "-"], input=report.content, capture_output=True, check=True)  # noqa: S607
        text = out.stdout.decode()
        assert "SIMULATED" in text and "simulated@" in text and "FAIL" in text


def test_decisions_rescore_and_survive_a_restart(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    insp_id = _start(client, roll_code)["id"]
    _run_to_end(client, insp_id)
    real = [d for d in client.get(f"/api/v1/inspections/{insp_id}/defects").json() if d["kind"] == "defect"]
    hole = next(d for d in real if d["current_cls"] == "hole")
    slub = next(d for d in real if d["current_cls"] == "slub")
    stain = next(d for d in real if d["current_cls"] == "stain")

    r = client.post(f"/api/v1/defects/{hole['id']}/reject", json={"reason_category": "pin_hole"})
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["reject_reason"] == "pin_hole"
    r = client.post(f"/api/v1/defects/{slub['id']}/reclassify", json={"to_cls": "hole"})
    assert r.status_code == 200 and r.json()["current_cls"] == "hole" and r.json()["status"] == "confirmed"
    r = client.post(f"/api/v1/defects/{stain['id']}/length", json={"length_in": 10})
    assert r.status_code == 200 and r.json()["length_source"] == "inspector" and r.json()["points"] == 4
    client.post(f"/api/v1/defects/{stain['id']}/confirm", json={})
    manual = client.post(
        f"/api/v1/inspections/{insp_id}/defects", json={"cls": "knot", "center_yd": 0.8, "length_in": 0.5}
    )
    assert manual.status_code == 201, manual.text
    assert manual.json()["origin"] == "manual" and manual.json()["status"] == "confirmed"
    bad = client.post(f"/api/v1/defects/{stain['id']}/reclassify", json={"to_cls": "sticker"})
    assert bad.status_code == 409  # a non-defect class is not a defect type

    before = client.get(f"/api/v1/inspections/{insp_id}/score").json()
    # slub (7.87 in) reclassified as hole → >1 in hole → 4; stain edited to 10 in → 4; knot 0.5 in → 1
    assert before["confirmed_points"] == 9 and before["pending"] == 0 and before["rejected"] == 1

    live.clear_cache()  # as after a restart: the runner is rebuilt from the stored events
    after = client.get(f"/api/v1/inspections/{insp_id}/score").json()
    assert after == before
    rebuilt = client.get(f"/api/v1/inspections/{insp_id}/defects").json()
    assert {(d["defect_no"], d["status"], d["current_cls"], d["points"]) for d in rebuilt} == {
        (d["defect_no"], d["status"], d["current_cls"], d["points"])
        for d in client.get(f"/api/v1/inspections/{insp_id}/defects").json()
    }


def test_one_driver_at_a_time_and_permissions(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    insp_id = _start(client, roll_code)["id"]

    with TestClient(create_app()) as other:
        login(other, "supervisor", TEST_PASSWORD)
        assert other.get(f"/api/v1/inspections/{insp_id}").json()["lease_held_elsewhere"] is True
        r = other.post(f"/api/v1/inspections/{insp_id}/advance", json={"until_frame": 10, "after_seq": 0})
        assert r.status_code == 409 and r.json()["detail"]["lease_lost"] is True
        assert other.post(f"/api/v1/inspections/{insp_id}/start").status_code == 409
        took = other.post(f"/api/v1/inspections/{insp_id}/start?takeover=true")
        assert took.status_code == 200 and took.json()["driver_session"] is True

    # The first browser lost the lease.
    r = client.post(f"/api/v1/inspections/{insp_id}/advance", json={"until_frame": 10, "after_seq": 0})
    assert r.status_code == 409

    # A second open inspection of the same roll is refused, with a pointer to the open one.
    machine = client.get("/api/v1/machines").json()[0]["id"]
    dup = client.post(
        "/api/v1/inspections",
        json={"roll_code": roll_code, "machine_id": machine, "source": {"dataset_id": "micro_roll"}},
    )
    assert dup.status_code == 409 and dup.json()["detail"]["inspection_id"] == insp_id

    login(client, "store")
    assert client.post(f"/api/v1/inspections/{insp_id}/start").status_code == 403
    assert client.get(f"/api/v1/inspections/{insp_id}").status_code == 200

    datasets = client.get("/api/v1/datasets").json()
    assert [d["id"] for d in datasets] == ["micro_roll"] and datasets[0]["has_video"] is False
    assert "ground_truth" not in json.dumps(datasets)


def test_bad_captures_are_refused(client: TestClient, tmp_path: Path) -> None:
    roll_code = _lot_with_roll(client)
    insp_id = _start(client, roll_code)["id"]
    png = io.BytesIO()
    Image.new("RGB", (10, 10)).save(png, "PNG")
    for b64 in (base64.b64encode(png.getvalue()).decode(), "not base64!!", base64.b64encode(b"\xff\xd8junk").decode()):
        r = client.post(
            f"/api/v1/inspections/{insp_id}/advance",
            json={
                "until_frame": 5,
                "after_seq": 0,
                "captures": [{"frame": 1, "jpeg_b64": b64, "width": 10, "height": 10}],
            },
        )
        assert r.status_code == 422, r.text
    snap = client.get(f"/api/v1/inspections/{insp_id}").json()
    assert snap["checkpoint_frame"] == -1  # nothing was processed by the refused calls


@pytest.mark.skipif(not (SAMPLE_ROLL / "frames.csv").exists(), reason="sample roll not in repo")
def test_sample_roll_through_the_api_matches_roll_meta(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """PLAN.md §11 test_sample_roll_e2e_api: perfect preset + simulator-parity profile → 10 / 46.45 / FAIL."""
    monkeypatch.setattr(datasets, "root", lambda: SAMPLE_ROLL.parent)
    meta = json.loads((SAMPLE_ROLL / "roll_meta.json").read_text())
    roll_code = _lot_with_roll(client, width_in=meta["fabric_width_in"])
    login(client, "inspector")
    machine = client.get("/api/v1/machines").json()[0]["id"]
    insp = client.post(
        "/api/v1/inspections",
        json={
            "roll_code": roll_code,
            "machine_id": machine,
            "source": {"dataset_id": "sample_roll"},
            "preset": "perfect",
        },
    ).json()
    assert client.post(f"/api/v1/inspections/{insp['id']}/start").status_code == 200
    after, last = 0, meta["frames"] - 1
    for until in (*range(150, last, 150), last):  # ~5 s of video per call, like the browser
        r = client.post(f"/api/v1/inspections/{insp['id']}/advance", json={"until_frame": until, "after_seq": after})
        assert r.status_code == 200, r.text
        after = r.json()["last_seq"]
    assert client.post(f"/api/v1/inspections/{insp['id']}/complete").status_code == 200
    for d in client.get(f"/api/v1/inspections/{insp['id']}/defects").json():
        if d["kind"] == "defect":
            assert client.post(f"/api/v1/defects/{d['id']}/confirm", json={}).status_code == 200
    v = client.post(f"/api/v1/inspections/{insp['id']}/finalize").json()
    es = meta["expected_score"]
    assert (v["points_total"], v["points_per_100"], v["system_verdict"]) == (
        es["total_points"],
        es["points_per_100_sq_yd"],
        es["verdict"],
    )


def test_drawn_missed_defect_bulk_confirm_and_a_verdict_with_unreviewed_defects(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    insp_id = _start(client, roll_code)["id"]
    _run_to_end(client, insp_id)
    real = [d for d in client.get(f"/api/v1/inspections/{insp_id}/defects").json() if d["kind"] == "defect"]

    # A missed defect drawn on frame 150, with a photo of that frame: it gets an evidence photo.
    capture = {"frame": 150, "jpeg_b64": _jpeg(), "width": 960, "height": 504}
    body = {"cls": "knot", "frame": 150, "bbox_px": [600, 300, 660, 340], "capture": capture}
    r = client.post(f"/api/v1/inspections/{insp_id}/defects", json=body)
    assert r.status_code == 201, r.text
    drawn = r.json()
    assert drawn["origin"] == "manual" and drawn["length_source"] == "pixels" and drawn["best_frame"] == 150
    assert drawn["crop_url"] and client.get(drawn["crop_url"]).content.startswith(b"\xff\xd8")
    bad = client.post(f"/api/v1/inspections/{insp_id}/defects", json={"cls": "knot", "bbox_px": [1, 2, 30, 40]})
    assert bad.status_code == 422  # a box needs the frame it was drawn on

    # Confirm every pending defect up to the first one's yard, then the rest.
    first = min(real, key=lambda d: d["center_yd"])
    r = client.post(f"/api/v1/inspections/{insp_id}/defects/confirm-pending", json={"up_to_yd": first["center_yd"]})
    assert r.status_code == 200 and r.json()["confirmed"] == [first["defect_no"]]
    with get_sessionmaker()() as db:
        assert "defect.confirm_bulk" in set(db.scalars(select(AuditLog.action)).all())

    # The slub alone fails the roll (3 points = 60.96 > 40): once it is confirmed, the defects still
    # pending cannot change the verdict, and the verdict may be computed with them not reviewed.
    client.post(f"/api/v1/defects/{first['id']}/reopen")
    slub = next(d for d in real if d["current_cls"] == "slub")
    client.post(f"/api/v1/defects/{slub['id']}/confirm", json={})
    score = client.get(f"/api/v1/inspections/{insp_id}/score").json()
    assert score["pending"] == 2 and score["verdict_settled"] is True
    assert client.post(f"/api/v1/inspections/{insp_id}/complete").status_code == 200
    final = client.post(f"/api/v1/inspections/{insp_id}/finalize")
    assert final.status_code == 200, final.text
    v = final.json()
    assert v["system_verdict"] == "FAIL" and v["unreviewed"] == 2
    assert v["points_total"] < v["points_if_all_confirmed"]
    assert sum(v["verdict_cells"].values()) == v["points_total"]  # the per-yard table matches the verdict
    report = client.get(f"/api/v1/inspections/{insp_id}/report.pdf")
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-", "-"], input=report.content, capture_output=True, check=True)  # noqa: S607
        assert "2 defect(s) were not reviewed" in out.stdout.decode()
    after = client.post(f"/api/v1/inspections/{insp_id}/defects/confirm-pending", json={})
    assert after.status_code == 409  # nothing changes after the verdict


def test_the_verdict_waits_while_pending_defects_could_change_it(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    insp_id = _start(client, roll_code)["id"]
    _run_to_end(client, insp_id)
    assert client.post(f"/api/v1/inspections/{insp_id}/complete").status_code == 200
    blocked = client.post(f"/api/v1/inspections/{insp_id}/finalize")
    assert blocked.status_code == 409 and "could change the verdict" in blocked.json()["detail"]["message"]
    r = client.post(f"/api/v1/inspections/{insp_id}/defects/confirm-pending", json={})
    assert r.status_code == 200 and len(r.json()["confirmed"]) == 3
    final = client.post(f"/api/v1/inspections/{insp_id}/finalize").json()
    assert final["unreviewed"] == 0 and final["points_total"] == META["expected_score"]["total_points"]


def test_advance_can_start_the_inspection_in_the_same_request(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    login(client, "inspector")
    machine = client.get("/api/v1/machines").json()[0]["id"]
    source = {"dataset_id": "micro_roll"}
    create = {"roll_code": roll_code, "machine_id": machine, "source": source, "preset": "perfect"}
    insp = client.post("/api/v1/inspections", json=create).json()
    body = {"until_frame": 120, "after_seq": 0, "start_key": "start-0001"}
    r = client.post(f"/api/v1/inspections/{insp['id']}/advance", json=body)
    assert r.status_code == 200, r.text
    types = [e["type"] for e in r.json()["events"]]
    assert types[0] == "session.started" and "detection.batch" in types and r.json()["checkpoint_frame"] == 120
    score = next(e for e in reversed(r.json()["events"]) if e["type"] == "score.updated")
    assert score["payload"]["at_frame"] == 120
    snap = client.get(f"/api/v1/inspections/{insp['id']}").json()
    assert snap["status"] == "running" and snap["driver_session"] is True


def test_an_inspection_whose_detector_is_gone_says_so_and_can_be_aborted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new model replaced the one an open inspection started with: a clear 409, not a server error."""
    from threadeye.core.providers import ProviderNotConfigured

    insp_id = _start(client, _lot_with_roll(client))["id"]
    live._cache.clear()  # the next request rebuilds the runner, as after a restart

    def gone(*_: Any, **__: Any) -> Any:
        raise ProviderNotConfigured("LocalModelDetector: threadeye_s.onnx SHA-256 601ba676a688… != 243d6e4ddc6f…")

    monkeypatch.setattr(live.Runner, "__init__", gone)
    r = client.post(f"/api/v1/inspections/{insp_id}/advance", json={"until_frame": 40, "after_seq": 0})
    assert r.status_code == 409 and "abort it and inspect the roll again" in r.text
    r = client.post(f"/api/v1/inspections/{insp_id}/abort", headers={"Idempotency-Key": "abort-0001"})
    assert r.status_code == 200 and r.json()["status"] == "aborted"


def test_an_open_inspection_on_a_replaced_model_is_flagged(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The list and the live page show "restart on the new model" instead of a resume that cannot work."""
    from types import SimpleNamespace

    monkeypatch.setattr(live, "_local_model_config", lambda: {"sha256": "new"})

    def insp(status: str, provider: str, sha: str) -> Any:
        return SimpleNamespace(status=status, provider_snapshot={"provider_id": provider, "config": {"sha256": sha}})

    assert live.model_outdated(insp("paused", "local_model", "old"))
    assert not live.model_outdated(insp("paused", "local_model", "new"))
    assert not live.model_outdated(insp("finalized", "local_model", "old"))  # a closed one keeps its model
    assert not live.model_outdated(insp("paused", "simulated", "old"))
    insp_id = _start(client, _lot_with_roll(client))["id"]  # the simulated detector
    assert client.get(f"/api/v1/inspections/{insp_id}").json()["model_outdated"] is False
    assert all(i["model_outdated"] is False for i in client.get("/api/v1/inspections?open_only=true").json())


def test_the_servers_larger_photo_of_a_frame_is_not_replaced_by_a_smaller_capture(client: TestClient) -> None:
    import uuid

    from threadeye.core.frames import FrameImage
    from threadeye.db.models import Inspection, InspectionFrame

    insp_id = uuid.UUID(_start(client, _lot_with_roll(client))["id"])

    def jpeg(w: int, h: int) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (200, 190, 170)).save(buf, "JPEG")
        return buf.getvalue()

    with get_sessionmaker()() as db:
        insp = db.get(Inspection, insp_id)
        assert insp is not None
        runner = live.runner_for(db, insp)
        # The server's own picture of a 3840-px view is kept at 1920 px; the browser sends 960 px.
        server = live._evidence_photo(10, FrameImage(jpeg(3840, 248), 3840, 248, 1.0))
        assert server[2:] == (1920, 124)
        live.store_frame_photos(db, insp, runner, [server])
        live.store_frame_photos(db, insp, runner, [(10, jpeg(960, 62), 960, 62)])
        db.commit()
        where = (InspectionFrame.inspection_id == insp_id, InspectionFrame.frame == 10)
        assert db.scalars(select(InspectionFrame).where(*where)).one().width == 1920


def test_abort_preserves_defects_and_allows_a_new_inspection_of_the_same_roll(client: TestClient) -> None:
    roll_code = _lot_with_roll(client)
    old = _start(client, roll_code)
    id_ = old["id"]
    _run_to_end(client, id_)
    before = client.get(f"/api/v1/inspections/{id_}/defects").json()
    assert before
    aborted = client.post(f"/api/v1/inspections/{id_}/abort", headers={"Idempotency-Key": "list-abort"})
    assert aborted.status_code == 200 and aborted.json()["status"] == "aborted"
    after = client.get(f"/api/v1/inspections/{id_}/defects").json()
    assert [d["id"] for d in after] == [d["id"] for d in before]
    response = client.post(
        "/api/v1/inspections",
        json={
            "roll_code": roll_code,
            "machine_id": old["machine_id"],
            "source": {"dataset_id": "micro_roll"},
            "preset": "perfect",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["id"] != id_
    assert response.json()["status"] == "created"
    assert client.get(f"/api/v1/inspections/{id_}").json()["status"] == "aborted"
