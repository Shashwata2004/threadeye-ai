"""PrefetchingDetector: the background thread hands out the same results the request would compute."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

from threadeye.core.frames import FrameImage, FramePacket, FramePosition
from threadeye.core.providers import DetectionResult, DetectorProvider, ProviderInfo
from threadeye.providers.prefetch import PrefetchingDetector

INFO = ProviderInfo(
    provider_id="fake",
    version="1",
    display_name="fake",
    kind="local_model",
    is_simulated=False,
    requires_image=True,
    calibrated_confidence=False,
    bbox_quality="precise",
    classes=("stain",),
    config_hash="x",
)


def pos(f: int) -> FramePosition:
    return FramePosition(f, f / 3, f * 10.0, 0.0, 0.1, 20.0, "running", 0.0, False)


class Source:
    def read(self, start: int, stop: int | None, want: Callable[[FramePosition], bool]) -> Iterator[FramePacket]:
        for f in range(start, 200 if stop is None else stop):
            p = pos(f)
            yield FramePacket(p, FrameImage(b"jpeg", 10, 10, 1.0) if want(p) else None)


class Slow(DetectorProvider):
    """Takes 20 ms a frame; records which thread ran each frame."""

    def __init__(self) -> None:
        super().__init__({}, None)  # type: ignore[arg-type]
        self.by_thread: dict[int, str] = {}

    @property
    def info(self) -> ProviderInfo:
        return INFO

    def detect(self, frame: FramePacket) -> DetectionResult:
        time.sleep(0.02)
        self.by_thread[frame.pos.frame] = threading.current_thread().name
        return DetectionResult(frame.pos.frame, [], 20.0, INFO)


def packet(f: int) -> FramePacket:
    return FramePacket(pos(f), FrameImage(b"jpeg", 10, 10, 1.0))


def test_the_thread_detects_ahead_and_requests_take_its_results() -> None:
    inner = Slow()
    d = PrefetchingDetector(inner, Source, frames=range(0, 200, 2), window=10)
    assert d.detect(packet(0)).frame == 0  # starts the thread there
    time.sleep(0.4)  # it works ahead, but no further than the window
    ahead = max(inner.by_thread)
    assert 8 <= ahead <= 12
    results: list[Any] = [d.detect(packet(f)) for f in range(2, 12, 2)]
    assert [r.frame for r in results] == [2, 4, 6, 8, 10]
    assert all(inner.by_thread[f] == "detector-prefetch" for f in range(2, 12, 2))
    d.close()


def test_a_frame_the_thread_has_passed_is_detected_in_the_request() -> None:
    inner = Slow()
    d = PrefetchingDetector(inner, Source, frames=range(0, 200, 2), window=10)
    d.detect(packet(20))
    assert d.detect(packet(4)).frame == 4  # behind the thread's start: detected here
    assert inner.by_thread[4] == threading.current_thread().name
    d.close()


def test_ready_until_follows_the_thread() -> None:
    inner = Slow()
    d = PrefetchingDetector(inner, Source, frames=range(0, 200, 2), window=10)
    assert d.ready_until == -2  # no thread yet
    d.detect(packet(0))
    time.sleep(0.3)
    assert 6 <= d.ready_until <= 12  # finished frames, never more than the window ahead
    d.close()
