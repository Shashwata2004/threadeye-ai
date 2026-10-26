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
from sqlalchemy import func, select
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


def put(db: Session, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """Store ``data`` under ``key`` durably; returns its SHA-256."""
    sha = hashlib.sha256(data).hexdigest()
    if get_settings().is_cloud:
        _check_key(key)
        stmt = insert(Blob).values(key=key, data=data, sha256=sha, size=len(data), content_type=content_type)
        # excluded.* reuses the inserted values: the bytes are sent once, not twice.
        update = {c: getattr(stmt.excluded, c) for c in ("data", "sha256", "size", "content_type")}
        db.execute(stmt.on_conflict_do_update(index_elements=[Blob.key], set_=update))
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


def put_many(db: Session, items: list[tuple[str, bytes]], content_type: str = "image/jpeg") -> list[str]:
    """``put`` for several files: on the cloud one statement for all of them (one round trip to a remote
    database, not one per file). Returns their SHA-256s."""
    if not get_settings().is_cloud:
        return [put(db, key, data, content_type) for key, data in items]
    if not items:
        return []
    shas = [hashlib.sha256(data).hexdigest() for _, data in items]
    rows = []
    for (key, data), sha in zip(items, shas, strict=True):
        _check_key(key)
        rows.append({"key": key, "data": data, "sha256": sha, "size": len(data), "content_type": content_type})
    stmt = insert(Blob).values(rows)
    update = {c: getattr(stmt.excluded, c) for c in ("data", "sha256", "size", "content_type")}
    db.execute(stmt.on_conflict_do_update(index_elements=[Blob.key], set_=update))
    return shas


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


def video_key(dataset_id: str) -> str:
    """Where a simulated roll's video is kept on the cloud profile (no local files on a serverless host)."""
    return f"datasets/{dataset_id}/roll_video.mp4"


def blob_size(db: Session, key: str) -> int | None:
    """Size of a stored file, without reading it (cloud profile only)."""
    if not get_settings().is_cloud:
        return None
    _check_key(key)
    size = db.scalar(select(Blob.size).where(Blob.key == key))
    return int(size) if size is not None else None


def read_range(db: Session, key: str, start: int, length: int) -> bytes:
    """Bytes ``start`` .. ``start + length - 1`` of a stored file (Postgres reads only that slice)."""
    _check_key(key)
    data = db.scalar(select(func.substring(Blob.data, start + 1, length)).where(Blob.key == key))
    if data is None:
        raise FileNotFoundError(key)
    return bytes(data)


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
