"""Evidence images: a local volume on the edge box, the shared database on the cloud profile."""

from __future__ import annotations

import pytest

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
