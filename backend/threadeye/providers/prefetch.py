"""PrefetchingDetector: a detector that looks at the picture, run on the coming frames in a background thread.

A live inspection's request (``/advance``) used to decode a frame, run the model and write the result in
the same request, one after the other. Against Supabase each request also waits on 7-15 database round
trips of ~0.5 s (2026-10-26, from Dhaka to the Tokyo database), so the model only started on a frame after
the database work for the previous ones: boxes came after the fabric had left the screen. Here the model
works through the sampled frames continuously, from its own reader of the same video file, and the request
takes the finished result. The results are the ones the request would have computed itself (same frames,
same JPEG encoding, same model); a frame the thread has not reached, or has already passed, is detected
in the request as before.

The thread stays at most ``window`` frames ahead of the last frame asked for, and stops after
``idle_s`` seconds without a request, on ``close()``, or at the end of the video.
"""

from __future__ import annotations

import atexit
import threading
import time
import weakref
from collections.abc import Callable, Iterable
from typing import Any

from threadeye.core.frames import FramePacket, SourceInfo
from threadeye.core.providers import DetectionResult, DetectorProvider, ProviderInfo

_RUNNING: weakref.WeakSet[PrefetchingDetector] = weakref.WeakSet()


@atexit.register
def _stop_all() -> None:
    """Stop the threads before the interpreter goes: one killed inside ONNX Runtime aborts the process."""
    for d in list(_RUNNING):
        d.close()
    for d in list(_RUNNING):
        if d._thread is not None:
            d._thread.join(timeout=5)


WAIT_S = 30.0
"""Longest a request waits for the thread to finish a frame it is working towards."""


class PrefetchingDetector(DetectorProvider):
    def __init__(
        self,
        inner: DetectorProvider,
        open_source: Callable[[], Any],
        frames: Iterable[int],
        *,
        window: int = 90,
        idle_s: float = 120.0,
    ) -> None:
        super().__init__(inner.config, inner.ctx)
        self.inner = inner
        self._open_source = open_source
        self._wanted = frozenset(frames)
        self.window = window
        self.idle_s = idle_s
        self._results: dict[int, DetectionResult] = {}
        self._cond = threading.Condition()
        self._asked = -1
        """The highest frame a request has asked for."""
        self._pos = -1
        """The next frame the thread will look at (-1: no thread yet)."""
        self._thread: threading.Thread | None = None
        self._stop = False
        self._last_call = time.monotonic()

    @property
    def info(self) -> ProviderInfo:
        return self.inner.info

    def prepare(self, source: SourceInfo) -> None:
        self.inner.prepare(source)

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self.inner.close()

    @property
    def ready_until(self) -> int:
        """The last frame the thread has finished (-1: none yet). A request that stops here does not wait."""
        with self._cond:
            return self._pos - 1

    def detect(self, frame: FramePacket) -> DetectionResult:
        f = frame.pos.frame
        with self._cond:
            self._last_call = time.monotonic()
            self._asked = max(self._asked, f)
            if self._thread is None and not self._stop:
                self._pos = f
                self._thread = threading.Thread(target=self._run, args=(f,), name="detector-prefetch", daemon=True)
                self._thread.start()
                _RUNNING.add(self)
            self._cond.notify_all()
            deadline = time.monotonic() + WAIT_S
            # Wait only for a frame the thread will still reach.
            while f not in self._results and self._working() and self._pos <= f and time.monotonic() < deadline:
                self._cond.wait(0.5)
            result = self._results.pop(f, None)
            for old in [k for k in self._results if k < f]:
                del self._results[old]
        return result if result is not None else self.inner.detect(frame)

    def _working(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop

    def _run(self, start: int) -> None:
        source = self._open_source()
        try:
            for packet in source.read(start, None, lambda p: p.frame in self._wanted):
                f = packet.pos.frame
                with self._cond:
                    while not self._stop and f > self._asked + self.window:
                        if time.monotonic() - self._last_call > self.idle_s:
                            self._stop = True
                        self._cond.wait(1.0)
                    if self._stop:
                        return
                    self._pos = f
                if packet.image is None:
                    continue
                result = self.inner.detect(packet)
                with self._cond:
                    if f >= self._asked:  # a request already past this frame detected it itself
                        self._results[f] = result
                    self._pos = f + 1
                    self._cond.notify_all()
        finally:
            close = getattr(source, "close", None)
            if close:
                close()
            with self._cond:
                self._pos = 1 << 62  # done: a request never waits on it again
                self._cond.notify_all()
