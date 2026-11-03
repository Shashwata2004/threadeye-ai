from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import MICRO_ROLL, login
from tests.integration.test_live_inspection import _lot_with_roll, _run_to_end, _start
from threadeye.db.models import DefectRow, Inspection, InspectionFrame, Lot, Setting, User
from threadeye.db.session import get_sessionmaker
from threadeye.services import datasets, demo_archive, operations

pytestmark = pytest.mark.integration


def evaluation_body(client: TestClient) -> dict:
    machine = client.get("/api/v1/machines").json()[0]["id"]
    return {
        "dataset_ids": ["micro_roll"],
        "machine_id": machine,
        "provider_id": "simulated",
        "preset": "perfect",
        "min_recall": 1,
        "max_false_alarms": 0,
        "max_score_delta": 0.01,
    }


def test_verification_green_red_history_and_machine_warning_data(client: TestClient) -> None:
    login(client, "supervisor")
    body = evaluation_body(client)
    response = client.post("/api/v1/verification/runs", json=body)
    assert response.status_code == 202, response.text
    green = client.get("/api/v1/verification/runs").json()[0]
    assert green["status"] == "completed" and green["result"]["passed"] is True
    assert green["result"]["rolls"][0]["funnel"]["raw_mapped"] > 0
    assert client.post("/api/v1/verification/runs", json={**body, "preset": "realistic"}).status_code == 202
    red = client.get("/api/v1/verification/runs").json()[0]
    assert red["result"]["passed"] is False
    dash = client.get("/api/v1/dashboard").json()
    assert dash["verification"][body["machine_id"]]["passed"] is False
    login(client, "inspector")
    assert client.post("/api/v1/verification/runs", json=body).status_code == 403
    assert client.get("/api/v1/verification/runs").status_code == 200


def test_benchmark_requires_test_manifest_and_rejects_training(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    shutil.copytree(MICRO_ROLL, tmp_path / "micro_roll")
    monkeypatch.setattr(datasets, "root", lambda: tmp_path)
    login(client, "supervisor")
    body = evaluation_body(client)
    assert client.post("/api/v1/benchmark/runs", json=body).status_code == 422
    manifest = tmp_path / "micro_roll/evaluation_manifest.json"
    manifest.write_text(json.dumps({"split": "train", "training_excluded": True}))
    assert client.post("/api/v1/benchmark/runs", json=body).status_code == 422
    manifest.write_text(json.dumps({"split": "test", "training_excluded": True}))
    response = client.post("/api/v1/benchmark/runs", json=body)
    assert response.status_code == 202, response.text
    history = client.get("/api/v1/benchmark/runs").json()
    assert history[0]["status"] == "completed"
    assert history[0]["result"]["rolls"][0]["evaluation"]["fn"] == 0


def test_schedule_runs_once_per_machine_per_day(client: TestClient) -> None:
    login(client, "supervisor")
    body = evaluation_body(client)
    assert client.put("/api/v1/verification/schedules", json={**body, "enabled": True}).status_code == 200
    operations.schedule_daily()
    operations.schedule_daily()
    history = client.get("/api/v1/verification/runs").json()
    assert len(history) == 1 and history[0]["status"] == "queued"
    assert operations.work_once() is True
    assert operations.work_once() is False
    assert client.get("/api/v1/verification/runs").json()[0]["status"] == "completed"


def test_revoked_permission_disables_a_recurring_verification(client: TestClient) -> None:
    login(client, "supervisor")
    assert (
        client.put("/api/v1/verification/schedules", json={**evaluation_body(client), "enabled": True}).status_code
        == 200
    )
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.username == "supervisor"))
        assert user
        user.role = "inspector"
        db.commit()
    operations.schedule_daily()
    assert client.get("/api/v1/verification/runs").json() == []


def test_job_failure_is_persisted_and_does_not_expose_exception(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> dict:
        raise ValueError("private runtime detail")

    monkeypatch.setattr(operations, "evaluate", fail)
    login(client, "supervisor")
    assert client.post("/api/v1/verification/runs", json=evaluation_body(client)).status_code == 202
    run = client.get("/api/v1/verification/runs").json()[0]
    assert run["status"] == "failed" and "private" not in run["error"]


def finalized(client: TestClient) -> str:
    code = _lot_with_roll(client)
    inspection = _start(client, code)
    id_ = inspection["id"]
    _run_to_end(client, id_)
    assert client.post(f"/api/v1/inspections/{id_}/complete").status_code == 200
    assert client.post(f"/api/v1/inspections/{id_}/defects/confirm-pending", json={}).status_code == 200
    response = client.post(f"/api/v1/inspections/{id_}/finalize")
    assert response.status_code == 200, response.text
    return str(id_)


def test_cutting_policy_defaults_persists_and_locks_without_changing_score(client: TestClient) -> None:
    id_ = finalized(client)
    login(client, "supervisor")
    url = f"/api/v1/inspections/{id_}/cutting"
    original = client.get(url).json()
    score = client.get(f"/api/v1/inspections/{id_}").json()
    assert original["policy_selection"] == "buyer" and original["policy_locked"] is False
    assert original["plan"]["policy"]["min_points_to_cut"] == 2
    for selection, points in [("all", 1), ("three_plus", 3), ("four_plus", 4), ("two_plus", 2), ("buyer", 2)]:
        response = client.put(url + "/policy", json={"selection": selection})
        assert response.status_code == 200, response.text
        assert response.json()["policy_selection"] == selection
        assert response.json()["plan"]["policy"]["min_points_to_cut"] == points
        assert client.get(url).json()["source_hash"] == response.json()["source_hash"]
    assert client.get(url).json()["source_hash"] == original["source_hash"]
    all_defects = client.put(url + "/policy", json={"selection": "all"}).json()
    assert all_defects["plan"]["skipped_yd"] >= original["plan"]["skipped_yd"]
    assert client.put(url + "/policy", json={"selection": "invalid"}).status_code == 422
    login(client, "cutting")
    assert client.put(url + "/policy", json={"selection": "buyer"}).status_code == 403
    login(client, "supervisor")
    assert client.post(url + "/approve").json()["policy_locked"] is True
    assert client.put(url + "/policy", json={"selection": "buyer"}).status_code == 409
    persisted = client.get(url).json()
    assert persisted["policy_selection"] == "all" and persisted["status"] == "approved"
    assert persisted["source_hash"] == all_defects["source_hash"]
    after = client.get(f"/api/v1/inspections/{id_}").json()
    for field in ("points_total", "points_per_100", "system_verdict", "rule_profile_id"):
        assert after[field] == score[field]


def test_cutting_approval_acknowledgment_pdf_and_labels(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    id_ = finalized(client)
    login(client, "supervisor")
    plan = client.get(f"/api/v1/inspections/{id_}/cutting").json()
    assert plan["status"] == "draft"
    with get_sessionmaker()() as db:
        confirmed = list(
            db.scalars(
                select(DefectRow).where(
                    DefectRow.inspection_id == uuid.UUID(id_),
                    DefectRow.status == "confirmed",
                    DefectRow.kind == "defect",
                    DefectRow.excluded_reason.is_(None),
                )
            )
        )
        assert {d["id"] for d in plan["defects"]} == {str(d.id) for d in confirmed}
    from threadeye.services import roll_image

    monkeypatch.setattr(roll_image, "image_bytes", lambda _: b"fabric-jpeg")
    image = client.get(f"/api/v1/inspections/{id_}/cutting/fabric.jpg")
    assert image.status_code == 200 and image.content == b"fabric-jpeg"
    assert image.headers["content-type"] == "image/jpeg"
    assert image.headers["cache-control"].startswith("private")
    login(client, "inspector")
    assert client.get(f"/api/v1/inspections/{id_}/cutting/fabric.jpg").status_code == 403
    login(client, "supervisor")
    assert plan["plan"]["usable_yd"] + plan["plan"]["skipped_yd"] == pytest.approx(
        plan["plan"]["length_yd"], abs=0.0001
    )
    login(client, "cutting")
    assert client.post(f"/api/v1/inspections/{id_}/cutting/acknowledge").status_code == 409
    assert client.post(f"/api/v1/inspections/{id_}/cutting/approve").status_code == 403
    login(client, "supervisor")
    assert client.post(f"/api/v1/inspections/{id_}/cutting/approve").json()["status"] == "approved"
    assert client.post(f"/api/v1/inspections/{id_}/cutting/approve").status_code == 200
    login(client, "cutting")
    assert client.post(f"/api/v1/inspections/{id_}/cutting/acknowledge").json()["status"] == "acknowledged"
    pdf = client.get(f"/api/v1/inspections/{id_}/cutting.pdf?lang=bn")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    login(client, "admin")
    result = client.get(f"/api/v1/inspections/{id_}/labels.zip")
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        exported = json.loads(archive.read("annotations.json"))
        assert exported["info"]["simulated_video"] is True
        assert "not_training_ready" in exported["info"]


def test_measurements_rescore_are_idempotent_and_lock_after_finalize(client: TestClient) -> None:
    login(client, "admin")
    original = client.get("/api/v1/admin/rule-profiles").json()[0]["rules"]
    rules = {**original, "name": "Measured width test", "width_basis": "measured"}
    assert client.post("/api/v1/admin/rule-profiles", json={"rules": rules}).status_code == 201
    code = _lot_with_roll(client, profile="Measured width test")
    inspection = _start(client, code)
    id_ = inspection["id"]
    _run_to_end(client, id_)
    before = client.get(f"/api/v1/inspections/{id_}/score").json()["per_100_provisional"]
    width = inspection["roll"]["declared_width_in"] / 2
    body = {"kind": "width", "value": width, "unit": "in"}
    response = client.post(
        f"/api/v1/inspections/{id_}/measurements", json=body, headers={"Idempotency-Key": "measure1"}
    )
    assert response.status_code == 201, response.text
    after = client.get(f"/api/v1/inspections/{id_}/score").json()["per_100_provisional"]
    assert after == pytest.approx(before * 2, abs=0.02)
    assert (
        client.post(
            f"/api/v1/inspections/{id_}/measurements", json=body, headers={"Idempotency-Key": "measure1"}
        ).status_code
        == 201
    )
    assert client.post(f"/api/v1/inspections/{id_}/measurements", json={**body, "unit": "yd"}).status_code == 422
    assert client.post(f"/api/v1/inspections/{id_}/complete").status_code == 200
    assert client.post(f"/api/v1/inspections/{id_}/defects/confirm-pending", json={}).status_code == 200
    assert client.post(f"/api/v1/inspections/{id_}/finalize").status_code == 200
    assert client.post(f"/api/v1/inspections/{id_}/measurements", json=body).status_code == 409
    report = client.get(f"/api/v1/inspections/{id_}/report.pdf?lang=bn")
    assert report.status_code == 200 and report.content.startswith(b"%PDF-")


def test_profiles_version_without_changing_existing_lot_and_preview_uses_engine(client: TestClient) -> None:
    code = _lot_with_roll(client)
    inspection = _start(client, code)
    login(client, "admin")
    profiles = client.get("/api/v1/admin/rule-profiles").json()
    old = next(p for p in profiles if p["id"] == inspection["rule_profile_id"])
    rules = {**old["rules"], "threshold_per_100": 15}
    response = client.post("/api/v1/admin/rule-profiles", json={"buyer_id": old["buyer_id"], "rules": rules})
    assert response.status_code == 201, response.text
    assert response.json()["version"] == old["version"] + 1
    assert client.get(f"/api/v1/inspections/{inspection['id']}").json()["rule_profile_id"] == old["id"]
    preview = client.post(
        "/api/v1/admin/rule-profiles/preview",
        json={
            "rules": rules,
            "length_yd": 10,
            "width_in": 60,
            "defects": [{"cls": "stain", "start_yd": 2, "end_yd": 2.1, "length_in": 4}],
        },
    ).json()
    assert preview["points"] == 2 and preview["per_100"] == 12


def test_machine_edit_persists_and_dashboard_scope(client: TestClient) -> None:
    login(client, "admin")
    response = client.post(
        "/api/v1/admin/machines",
        json={"code": "M-NEW", "name": "New machine", "calibration": {"px_per_cm": 24, "view_width_px": 1920}},
    )
    assert response.status_code == 201, response.text
    id_ = response.json()["id"]
    assert (
        client.patch(
            f"/api/v1/admin/machines/{id_}", json={"code": "M-NEW", "name": "Renamed", "active": False}
        ).status_code
        == 200
    )
    assert next(m for m in client.get("/api/v1/admin/machines").json() if m["id"] == id_)["name"] == "Renamed"
    login(client, "inspector")
    assert client.get("/api/v1/dashboard").json()["scope"] == "own"
    login(client, "management")
    assert client.get("/api/v1/dashboard").json()["scope"] == "all"


def test_provider_default_is_deployment_scoped(client: TestClient) -> None:
    login(client, "admin")
    assert client.put("/api/v1/admin/provider", json={"provider_id": "simulated"}).status_code == 200
    assert client.get("/health").json()["simulated_mode"] is True
    with get_sessionmaker()() as db:
        assert db.get(Setting, "detector_provider:edge").value == "simulated"
        assert db.get(Setting, "detector_provider:serverless") is None


def test_dashboard_counts_finalized_roll_and_honest_sample_label(client: TestClient) -> None:
    id_ = finalized(client)
    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["rolls"] == 1 and dashboard["simulated_rolls"] == 1
    with get_sessionmaker()() as db:
        inspection = db.get(Inspection, uuid.UUID(id_))
        assert inspection
        assert dashboard["avg_per_100"] == inspection.points_per_100
    assert not list(client.get("/api/v1/verification/runs").json())


def test_coco_export_uses_saved_image_scale_and_preserves_source_group(client: TestClient) -> None:
    id_ = finalized(client)
    with get_sessionmaker()() as db:
        frame = db.scalar(
            select(InspectionFrame).where(
                InspectionFrame.inspection_id == uuid.UUID(id_), InspectionFrame.image_key.is_not(None)
            )
        )
        defect = db.scalar(
            select(DefectRow).where(DefectRow.inspection_id == uuid.UUID(id_), DefectRow.status == "confirmed")
        )
        assert frame and defect
        defect.best_frame, defect.best_bbox_px = frame.frame, [20, 20, 100, 100]
        expected_scale = frame.image_scale or 1
        db.commit()
    login(client, "admin")
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/inspections/{id_}/labels.zip").content)) as archive:
        exported = json.loads(archive.read("annotations.json"))
        assert exported["images"][0]["source_group"] == "micro_roll"
        assert exported["annotations"][0]["bbox"] == pytest.approx(
            [20 * expected_scale, 20 * expected_scale, 80 * expected_scale, 80 * expected_scale]
        )
        assert exported["annotations"][0]["label_source"] == "inspector"
        assert exported["annotations"][0]["source"] == "answer_key"


def test_clip_job_encodes_a_real_mp4(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import subprocess

    executable = shutil.which("ffmpeg")
    if not executable:
        pytest.skip("ffmpeg is required for the edge clip export test")
    shutil.copytree(MICRO_ROLL, tmp_path / "micro_roll")
    video = tmp_path / "micro_roll/roll_video.mp4"
    subprocess.run(  # noqa: S603 -- local encoder, fixed synthetic input
        [
            executable,
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=320x160:r=30",
            "-t",
            "10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    monkeypatch.setattr(datasets, "root", lambda: tmp_path)
    id_ = finalized(client)
    defect = client.get(f"/api/v1/inspections/{id_}/defects").json()[0]
    login(client, "supervisor")
    response = client.post(f"/api/v1/inspections/{id_}/defects/{defect['id']}/clip")
    assert response.status_code == 202, response.text
    clips = client.get(f"/api/v1/inspections/{id_}/clips").json()
    assert clips[0]["status"] == "completed", clips
    content = client.get(f"/api/v1/inspections/{id_}/clips/{clips[0]['id']}.mp4")
    assert content.status_code == 200 and b"ftyp" in content.content[:32]


def test_demo_archive_preserves_evidence_and_never_archives_unmarked_lots(client: TestClient) -> None:
    id_ = finalized(client)
    login(client, "admin")
    assert client.get("/api/v1/admin/demo-archive/schedule").json()["enabled"] is False
    response = client.post("/api/v1/admin/demo-archive")
    assert response.status_code == 200 and response.json()["archived_deliveries"] == 1
    assert client.get("/api/v1/lots").json() == []
    assert len(client.get("/api/v1/lots?include_archived=true").json()) == 1
    assert client.get(f"/api/v1/inspections/{id_}/report.pdf").status_code == 200
    with get_sessionmaker()() as db:
        lot = db.scalar(select(Lot))
        assert lot
        lot.status, lot.is_sample_data = "registered", False
        db.commit()
    assert client.post("/api/v1/admin/demo-archive").json()["archived_deliveries"] == 0


def test_nightly_demo_archive_is_explicit_and_starts_tomorrow(client: TestClient) -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    finalized(client)
    login(client, "admin")
    response = client.put("/api/v1/admin/demo-archive/schedule", json={"enabled": True})
    assert response.status_code == 200
    now = datetime.now(ZoneInfo("Asia/Dhaka"))
    demo_archive.scheduled(now)
    assert len(client.get("/api/v1/lots").json()) == 1
    demo_archive.scheduled((now + timedelta(days=1)).replace(hour=4))
    assert client.get("/api/v1/lots").json() == []
