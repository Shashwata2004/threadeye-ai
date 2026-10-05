"""File storage for evidence images (edge: a local volume; cloud: Supabase Storage from M6).

Power-loss safety (PLAN.md §12): write to a temp file, fsync, rename, and only then commit the row
that points at it. A crash leaves at most an orphan file, never a row pointing at a missing file.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from pathlib import Path

from PIL import Image

from threadeye.settings import get_settings

KEY = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-.]+)*$")
MAX_UPLOAD_BYTES = 1_500_000
MAX_SIDE_PX = 4096


class StorageError(ValueError):
    pass


def _path(key: str) -> Path:
    if not KEY.match(key) or ".." in key:
        raise StorageError(f"bad storage key {key!r}")
    return Path(get_settings().storage_dir) / key


def put(key: str, data: bytes) -> str:
    """Store ``data`` under ``key`` durably; returns its SHA-256."""
    target = _path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(target)
    return hashlib.sha256(data).hexdigest()


def get(key: str) -> bytes:
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
