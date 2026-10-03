"""FrameSource contract (PLAN.md §6.2).

A FrameSource provides the position of every frame (from ``frames.csv`` for file sources, from a
PositionProvider for live cameras) and the image of a frame on demand. The sampler decides from
positions alone which frames need an image, so file sources never decode frames they do not use.

Implementations (``threadeye.sources``):
- ``VideoFileSource``: simulator video + frames.csv, server-side decode (edge, headless runs). M1.
- ``CaptureFrameSource``: frames.csv track + JPEGs captured by the browser (live, both profiles). M2.
- ``WebcamSource``: STUB until the PVC-pipe test rig (camera index + PositionProvider).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Rect = tuple[int, int, int, int]
"""x, y, w, h in raw video pixels."""

MachineState = Literal["running", "stopped", "unknown"]
SourceKind = Literal["video_file", "webcam", "browser_capture"]


class NotSeekable(Exception):
    """Raised by live sources that cannot jump to a roll position (e.g. a webcam)."""


@dataclass(frozen=True)
class Calibration:
    px_per_cm: float
    view_region: Rect
    """Camera view without the simulator's info bar: (0, 0, 1920, 1008) for the sample roll."""
    fabric_width_cm: float
    selvage_band_px: float | None = None

    def __post_init__(self) -> None:
        if self.px_per_cm <= 0:
            raise ValueError("px_per_cm must be > 0")
        if self.view_region[2] <= 0 or self.view_region[3] <= 0:
            raise ValueError("view_region width/height must be > 0")
        if self.fabric_width_cm <= 0:
            raise ValueError("fabric_width_cm must be > 0")

    @property
    def view_height_px(self) -> int:
        return self.view_region[3]


@dataclass(frozen=True)
class FramePosition:
    frame: int
    time_s: float
    roll_y_top_px: float
    """Roll-space y (px) of the top row of the view. ``roll_y_px = roll_y_top_px + y``."""
    top_yd: float
    bottom_yd: float
    speed_m_min: float | None
    state: MachineState
    fabric_x0_px: float | None
    """Left fabric edge in view pixels (the fabric drifts sideways)."""
    hand_visible: bool | None


@dataclass(frozen=True)
class FrameImage:
    """Encoded frame image. Decoding to arrays happens outside the core (``threadeye.sources``)."""

    jpeg: bytes
    width: int
    height: int
    scale: float = 1.0
    """Image pixels per source view pixel (a 960-px browser capture of a 1920-px view has 0.5)."""


@dataclass(frozen=True)
class FramePacket:
    pos: FramePosition
    image: FrameImage | None = None


@dataclass(frozen=True)
class SourceInfo:
    kind: SourceKind
    is_simulated: bool
    fps: float
    frame_count: int | None
    """None for live sources."""
    calibration: Calibration
    roll_length_yd: float | None
    descriptor: Mapping[str, Any] = field(default_factory=dict)
    """Dataset id + file SHA-256s; pinned on the inspection for reproducibility."""


class FrameSource(ABC):
    @abstractmethod
    def open(self) -> SourceInfo: ...

    @abstractmethod
    def track(self) -> Sequence[FramePosition] | None:
        """Full position track for file sources; ``None`` for live sources."""

    @abstractmethod
    def read(
        self,
        start: int,
        stop: int | None,
        want_image: Callable[[FramePosition], bool],
    ) -> Iterator[FramePacket]:
        """Yield frames ``start <= frame < stop`` (``stop=None``: until the source ends).

        Images are attached only where ``want_image(pos)`` is true.
        """

    def frame_for_yard(self, yd: float) -> int:
        """First frame whose view contains roll position ``yd`` (resume support)."""
        raise NotSeekable(type(self).__name__)

    @abstractmethod
    def close(self) -> None: ...
