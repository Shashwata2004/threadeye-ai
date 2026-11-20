"""Real CPU inference survives request-boundary cache loss on a serverless deployment."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import REPO_ROOT, login
from tests.integration.test_live_inspection import _lot_with_roll
from threadeye.db.models import Setting
from threadeye.db.session import get_sessionmaker
from threadeye.providers.prefetch import PrefetchingDetector
from threadeye.services import datasets, live
from threadeye.settings import get_settings

pytestmark = pytest.mark.integration


def test_real_model_on_serverless_after_cold_requests(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("onnxruntime")
    pytest.importorskip("cv2")
    model = REPO_ROOT / "data/model/threadeye_s.onnx"
    if not model.is_file():
        pytest.skip("bundled trained model missing")
    code = _lot_with_roll(client, profile="Default 4-point", width_in=59.06)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(get_settings(), "model_dir", str(model.parent))
    monkeypatch.setattr(datasets, "root", lambda: REPO_ROOT / "data")
    login(client, "admin")
    selected = client.put("/api/v1/admin/provider", json={"provider_id": "local_model"})
    assert selected.status_code == 200, selected.text
    with get_sessionmaker()() as db:
        assert db.get(Setting, "detector_provider:serverless").value == "local_model"
        assert db.get(Setting, "detector_provider:edge") is None
    assert client.get("/health").json()["simulated_mode"] is False
    checked = client.post("/api/v1/model/runtime-check")
    assert checked.status_code == 200, checked.text
    assert checked.json()["is_simulated"] is False
    assert len(checked.json()["model_sha256"]) == 64
    assert any(d["class"] == "slub" for d in checked.json()["detections"])
    login(client, "inspector")
    machine = client.get("/api/v1/machines").json()[0]["id"]
    loaded = client.post(
        "/api/v1/inspections",
        json={
            "roll_code": code,
            "machine_id": machine,
            "source": {"dataset_id": "linescan_roll"},
        },
    )
    assert loaded.status_code == 201, loaded.text
    snap = loaded.json()
    assert snap["provider"]["provider_id"] == "local_model"
    assert snap["provider"]["is_simulated"] is False
    path = f"/api/v1/inspections/{snap['id']}"
    previous = -1
    for n in range(8):
        body = {"until_frame": 22, "after_seq": 0}
        if n == 0:
            body["start_key"] = str(uuid.uuid4())
        response = client.post(path + "/advance", json=body)
        assert response.status_code == 200, response.text
        checkpoint = response.json()["checkpoint_frame"]
        assert previous < checkpoint <= previous + live.MIN_STEP_FRAMES
        assert not any(isinstance(e.runner.provider, PrefetchingDetector) for e in live._cache.values())
        previous = checkpoint
        live.clear_cache()  # Simulate a different/fresh function instance on the next request.
        if checkpoint == 22:
            break
    assert previous == 22
    found = client.get(path + "/defects").json()
    assert any(d["current_cls"] == "slub" and "ThreadEye model:" in d["explanation"] for d in found)
    assert all("SIMULATED" not in d["explanation"] for d in found)
    monkeypatch.setattr(get_settings(), "model_dir", str(model.parent / "missing"))
    login(client, "admin")
    assert client.put("/api/v1/admin/provider", json={"provider_id": "local_model"}).status_code == 409


def test_bundled_video_ranges_stay_below_serverless_payload_limit(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from tests.conftest import MICRO_ROLL
    from threadeye.api.routers.inspections import VIDEO_CHUNK

    root = tmp_path / "micro_roll"
    shutil.copytree(MICRO_ROLL, root)
    content = b"A" * VIDEO_CHUNK + b"B" * 1024
    (root / "roll_video.mp4").write_bytes(content)
    monkeypatch.setattr(datasets, "root", lambda: tmp_path)
    monkeypatch.setenv("VERCEL", "1")
    login(client, "inspector")
    path = "/api/v1/datasets/micro_roll/video"
    first = client.get(path, headers={"Range": "bytes=0-"})
    assert first.status_code == 206
    assert len(first.content) == VIDEO_CHUNK
    assert first.headers["content-range"] == f"bytes 0-{VIDEO_CHUNK - 1}/{len(content)}"
    second = client.get(path, headers={"Range": f"bytes={VIDEO_CHUNK}-"})
    assert second.status_code == 206 and second.content == b"B" * 1024
    assert first.content + second.content == content
    assert client.get(path, headers={"Range": f"bytes={len(content)}-"}).status_code == 416
