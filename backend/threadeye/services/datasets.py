"""Simulated rolls that can be inspected: directories under ``THREADEYE_DATASETS_DIR``.

A roll directory holds the simulator's files (roll_meta.json, frames.csv, ...) and, for the live
screen, a browser-playable video. A roll with a ``HIDDEN`` file is not offered for new inspections (an old demo
roll kept for the tests); it can still be opened by id. This module only reads public facts about a roll (length, width,
frame count, video file). It never reads the answer key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from threadeye.settings import get_settings
from threadeye.sources.simulated_roll import TrackFrameSource, VideoFileSource

DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
# First match wins: a small web preview (scripts/make_web_preview.py) before the full-size video.
VIDEO_FILES = (("roll_web.webm", "video/webm"), ("roll_web.mp4", "video/mp4"), ("roll_video.mp4", "video/mp4"))
PREFERRED = ("linescan_roll", "sample_roll", "demo_roll")
HIDDEN = "HIDDEN"


class DatasetNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DatasetInfo:
    id: str
    path: Path
    roll_length_yd: float
    fabric_width_in: float
    fabric_width_cm: float
    frames: int
    fps: float
    mode: str
    note: str | None
    video_file: str | None
    video_type: str | None
    is_simulated: bool = True

    @property
    def video_path(self) -> Path | None:
        return self.path / self.video_file if self.video_file else None


def root() -> Path:
    return Path(get_settings().datasets_dir)


def _info(directory: Path) -> DatasetInfo | None:
    try:
        meta: dict[str, Any] = json.loads((directory / "roll_meta.json").read_text(encoding="utf-8"))
        video = next(((name, kind) for name, kind in VIDEO_FILES if (directory / name).is_file()), (None, None))
        return DatasetInfo(
            id=directory.name,
            path=directory,
            roll_length_yd=float(meta["roll_length_yd"]),
            fabric_width_in=float(meta["fabric_width_in"]),
            fabric_width_cm=float(meta["fabric_width_cm"]),
            frames=int(meta["frames"]),
            fps=float(meta["fps"]),
            mode=str(meta.get("mode", "")),
            note=meta.get("fixture_note") or meta.get("note"),
            video_file=video[0],
            video_type=video[1],
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_datasets(base: Path | None = None) -> list[DatasetInfo]:
    base = base or root()
    if not base.is_dir():
        return []
    found = []
    for d in sorted(base.iterdir()):
        if (
            d.is_dir()
            and DATASET_ID.match(d.name)
            and (d / "roll_meta.json").is_file()
            and (d / "frames.csv").is_file()
            and not (d / HIDDEN).exists()
        ):
            info = _info(d)
            if info:
                found.append(info)
    # The line-scan roll first (the demo), then the first sample roll, the synthetic demo roll, the rest.
    return sorted(found, key=lambda i: (PREFERRED.index(i.id) if i.id in PREFERRED else len(PREFERRED), i.id))


def get_dataset(dataset_id: str, base: Path | None = None) -> DatasetInfo:
    if not DATASET_ID.match(dataset_id):
        raise DatasetNotFound(dataset_id)
    directory = (base or root()) / dataset_id
    info = _info(directory) if (directory / "frames.csv").is_file() else None
    if info is None:
        raise DatasetNotFound(dataset_id)
    return info


@lru_cache(maxsize=8)
def _source(path: str, mtime: float) -> TrackFrameSource:
    return TrackFrameSource(path)


def track_source(info: DatasetInfo) -> TrackFrameSource:
    """Parsed positions of a roll, cached until frames.csv changes."""
    return _source(str(info.path), (info.path / "frames.csv").stat().st_mtime)


def video_source(info: DatasetInfo) -> VideoFileSource:
    """A roll whose frames are decoded here (for detectors that look at the image). One per runner:
    it reads the video sequentially and keeps its position."""
    return VideoFileSource(info.path)
