"""Evidence images: a local volume on the edge box, the shared database on the cloud profile."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login
from threadeye.db.models import Blob
from threadeye.db.session import get_sessionmaker
from threadeye.services import storage
from threadeye.settings import get_settings

pytestmark = pytest.mark.integration

KEY = "inspections/test/frames/000001.jpg"


def test_cloud_profile_keeps_images_in_the_shared_database(clean_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = get_settings().model_copy(update={"deploy_profile": "cloud_demo"})
    monkeypatch.setattr(storage, "get_settings", lambda: cloud)
    with get_sessionmaker()() as db:
        sha = storage.put(db, KEY, b"first")
        storage.put(db, KEY, b"second")  # same key: replaced, not duplicated
        db.commit()
        assert storage.get(db, KEY) == b"second"
        row = db.get(Blob, KEY)
        assert row is not None and row.size == 6 and row.sha256 != sha
        with pytest.raises(FileNotFoundError):
            storage.get(db, "inspections/test/frames/000002.jpg")
        with pytest.raises(storage.StorageError):
            storage.put(db, "../escape.jpg", b"x")


def test_edge_profile_keeps_images_on_the_volume(clean_db: None) -> None:
    with get_sessionmaker()() as db:
        storage.put(db, KEY, b"local")
        assert storage.get(db, KEY) == b"local"
        assert db.get(Blob, KEY) is None


def test_cloud_video_is_served_in_pieces(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A serverless host caps a response at 4.5 MB: the video comes in Range pieces of at most 3 MB."""
    cloud = get_settings().model_copy(update={"deploy_profile": "cloud_demo"})
    monkeypatch.setattr(storage, "get_settings", lambda: cloud)
    video = bytes(range(256)) * (7 * 4096)  # 7 MiB, recognisable bytes
    with get_sessionmaker()() as db:
        storage.put(db, storage.video_key("micro_roll"), video, content_type="video/mp4")
        db.commit()
    login(client, "inspector")
    assert client.get("/api/v1/datasets").json()[0]["has_video"] is True

    first = client.get("/api/v1/datasets/micro_roll/video", headers={"Range": "bytes=0-"})
    assert first.status_code == 206 and len(first.content) == 3 * 1024 * 1024
    assert first.headers["content-range"] == f"bytes 0-{3 * 1024 * 1024 - 1}/{len(video)}"
    assert first.content == video[: 3 * 1024 * 1024]
    tail = client.get("/api/v1/datasets/micro_roll/video", headers={"Range": f"bytes={6 * 1024 * 1024}-"})
    assert tail.status_code == 206 and tail.content == video[6 * 1024 * 1024 :]
    small = client.get("/api/v1/datasets/micro_roll/video", headers={"Range": "bytes=10-19"})
    assert small.content == video[10:20]
    assert client.get("/api/v1/datasets/micro_roll/video", headers={"Range": f"bytes={len(video)}-"}).status_code == 416
