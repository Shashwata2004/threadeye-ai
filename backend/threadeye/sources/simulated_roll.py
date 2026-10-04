"""Frame sources for a simulated roll directory (roll_meta.json + frames.csv [+ roll_video.mp4]).

``TrackFrameSource``  positions only, no images. Enough for providers that do not need pixels (the
                      simulated detector) and for computing the sampling plan.
``VideoFileSource``   the same positions plus decoded, view-region-cropped frames (OpenCV, edge only;
                      installed with the ``vision`` extra). Imported lazily so the cloud bundle stays lean.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from threadeye.core.frames import (
    Calibration,
    FrameImage,
    FramePacket,
    FramePosition,
    FrameSource,
    SourceInfo,
)
from threadeye.datasets.contracts import FILES, ParsedDataset, validate_dataset


class InvalidRoll(ValueError):
    pass


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_roll(directory: str | Path, *, require_media: bool) -> ParsedDataset:
    report, parsed = validate_dataset(directory, require_media=require_media)
    if parsed is None:
        raise InvalidRoll("; ".join(str(e) for e in report.errors[:5]))
    return parsed


class TrackFrameSource(FrameSource):
    def __init__(self, directory: str | Path, *, require_media: bool = False) -> None:
        self.directory = Path(directory)
        self.parsed = load_roll(self.directory, require_media=require_media)
        m = self.parsed.meta
        self.calibration = Calibration(
            px_per_cm=m.px_per_cm,
            view_region=(m.view_region.x, m.view_region.y, m.view_region.w, m.view_region.h),
            fabric_width_cm=m.fabric_width_cm,
            selvage_band_px=m.selvage_band_px,
        )
        self._track = [
            FramePosition(
                frame=r.frame,
                time_s=r.time_s,
                roll_y_top_px=r.roll_y_top_px,
                top_yd=r.top_yd,
                bottom_yd=r.bottom_yd,
                speed_m_min=r.speed_m_min,
                state=r.state,
                fabric_x0_px=r.fabric_x0_px,
                hand_visible=r.hand_visible,
            )
            for r in self.parsed.frames
        ]

    def open(self) -> SourceInfo:
        m = self.parsed.meta
        return SourceInfo(
            kind="video_file",
            is_simulated=True,
            fps=m.fps,
            frame_count=len(self._track),
            calibration=self.calibration,
            roll_length_yd=m.roll_length_yd,
            descriptor={
                "dataset": self.directory.name,
                "mode": m.mode,
                "frames_csv_sha256": _sha256(self.directory / FILES["frames"]),
                "roll_meta_sha256": _sha256(self.directory / FILES["meta"]),
                "video_sha256": _sha256(self.directory / FILES["video"]),
            },
        )

    def track(self) -> Sequence[FramePosition]:
        return self._track

    def read(self, start: int, stop: int | None, want_image: Callable[[FramePosition], bool]) -> Iterator[FramePacket]:
        end = len(self._track) if stop is None else min(stop, len(self._track))
        for pos in self._track[max(0, start) : end]:
            yield FramePacket(pos, None)

    def frame_for_yard(self, yd: float) -> int:
        for pos in self._track:
            if pos.top_yd <= yd <= pos.bottom_yd:
                return pos.frame
        raise ValueError(f"yard {yd} is not in this roll")

    def close(self) -> None:
        pass


class VideoFileSource(TrackFrameSource):
    """Decodes frames sequentially (exact frame indices; no seeking inaccuracies)."""

    def __init__(self, directory: str | Path, *, jpeg_quality: int = 90) -> None:
        super().__init__(directory, require_media=True)
        self.jpeg_quality = jpeg_quality
        self._cap: Any = None
        self._next = 0

    def _cv2(self) -> Any:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise RuntimeError("VideoFileSource needs OpenCV: install the 'vision' extra") from exc
        return cv2

    def _open_capture(self) -> None:
        cv2 = self._cv2()
        self._cap = cv2.VideoCapture(str(self.directory / FILES["video"]))
        if not self._cap.isOpened():
            raise InvalidRoll("could not open roll_video.mp4")
        self._next = 0

    def read(self, start: int, stop: int | None, want_image: Callable[[FramePosition], bool]) -> Iterator[FramePacket]:
        cv2 = self._cv2()
        if self._cap is None or start < self._next:
            self._open_capture()
        x, y, w, h = self.calibration.view_region
        end = len(self._track) if stop is None else min(stop, len(self._track))
        while self._next < end:
            ok, img = self._cap.read()
            index = self._next
            self._next += 1
            if not ok:
                raise InvalidRoll(f"video ended at frame {index}, frames.csv has {len(self._track)}")
            if index < start:
                continue
            pos = self._track[index]
            image = None
            if want_image(pos):
                crop = img[y : y + h, x : x + w]
                ok_enc, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                if not ok_enc:
                    raise InvalidRoll(f"could not encode frame {index}")
                image = FrameImage(buf.tobytes(), int(crop.shape[1]), int(crop.shape[0]), 1.0)
            yield FramePacket(pos, image)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
