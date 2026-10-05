"""Storage for evidence images.

edge:       the local volume (the box works offline). Power-loss safety (PLAN.md §12): write to a temp
            file, fsync, rename, and only then commit the row that points at it.
cloud_demo: the ``blobs`` table in the shared Supabase database, written in the same transaction as
            the rows that point at it, so every teammate sees the same photos.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from pathlib import Path

from PIL import Image
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from threadeye.db.models import Blob
from threadeye.settings import get_settings

KEY = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-.]+)*$")
MAX_UPLOAD_BYTES = 1_500_000
MAX_SIDE_PX = 4096


class StorageError(ValueError):
    pass


def _check_key(key: str) -> None:
    if not KEY.match(key) or ".." in key:
        raise StorageError(f"bad storage key {key!r}")


def _path(key: str) -> Path:
    _check_key(key)
    return Path(get_settings().storage_dir) / key


def put(db: Session, key: str, data: bytes) -> str:
    """Store ``data`` under ``key`` durably; returns its SHA-256."""
    sha = hashlib.sha256(data).hexdigest()
    if get_settings().is_cloud:
        _check_key(key)
        stmt = insert(Blob).values(key=key, data=data, sha256=sha, size=len(data))
        db.execute(
            stmt.on_conflict_do_update(index_elements=[Blob.key], set_={"data": data, "sha256": sha, "size": len(data)})
        )
        return sha
    target = _path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(target)
    return sha


def get(db: Session, key: str) -> bytes:
    if get_settings().is_cloud:
        _check_key(key)
        data = db.get(Blob, key)
        if data is None:
            raise FileNotFoundError(key)
        return data.data
    path = _path(key)
    if not path.is_file():
        raise FileNotFoundError(key)
    return path.read_bytes()


def clean_jpeg(data: bytes) -> tuple[bytes, int, int]:
    """Validate an uploaded image and re-encode it as a plain JPEG (drops metadata and anything odd)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise StorageError("image too large")
    if not data.startswith(b"\xff\xd8"):
        raise StorageError("not a JPEG image")
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "JPEG":
                raise StorageError("not a JPEG image")
            w, h = img.size
            if not (0 < w <= MAX_SIDE_PX and 0 < h <= MAX_SIDE_PX):
                raise StorageError("image dimensions out of range")
            out = io.BytesIO()
            img.convert("RGB").save(out, "JPEG", quality=85)
    except (OSError, Image.DecompressionBombError) as exc:
        raise StorageError("unreadable image") from exc
    return out.getvalue(), w, h
