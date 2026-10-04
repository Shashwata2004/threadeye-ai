"""Frame sampling by fabric travel, not by frame count (PLAN.md §6.1 step 2).

Take a frame each time the fabric has moved ``view_height × (1 − overlap)``; none while the machine is
stopped; prefer a nearby frame without the inspector's hand when that keeps at least ``min_overlap``.
At 30 fps this sends ~1–2 % of frames to the detector while still seeing every centimetre of the roll.

``plan()`` runs over a whole file-source track (the plan is deterministic, so the browser can capture
exactly these frames). ``StreamingSampler`` makes the same decisions one frame at a time (live cameras).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from threadeye.core.frames import FramePosition

SampleReason = Literal["first", "travel", "hand_avoided", "hand_fallback", "last"]


@dataclass(frozen=True)
class SamplingConfig:
    overlap: float = 0.15
    min_overlap: float = 0.05
    skip_stopped: bool = True
    avoid_hand: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.min_overlap <= self.overlap < 1:
            raise ValueError("need 0 <= min_overlap <= overlap < 1")


@dataclass(frozen=True)
class Sample:
    frame: int
    roll_y_top_px: float
    reason: SampleReason


@dataclass(frozen=True)
class SamplingPlan:
    samples: tuple[Sample, ...]
    view_height_px: int
    step_px: float
    config: SamplingConfig

    @property
    def frames(self) -> list[int]:
        return [s.frame for s in self.samples]


def _usable(pos: FramePosition, cfg: SamplingConfig) -> bool:
    return not (cfg.skip_stopped and pos.state == "stopped")


def plan(track: Sequence[FramePosition], view_height_px: int, cfg: SamplingConfig | None = None) -> SamplingPlan:
    cfg = cfg or SamplingConfig()
    step = view_height_px * (1 - cfg.overlap)
    max_step = view_height_px * (1 - cfg.min_overlap)
    samples: list[Sample] = []
    if not track:
        return SamplingPlan((), view_height_px, step, cfg)

    first = next((p for p in track if _usable(p, cfg)), track[0])
    samples.append(Sample(first.frame, first.roll_y_top_px, "first"))
    last_y = first.roll_y_top_px
    i = first.frame + 1
    n = len(track)
    while i < n:
        pos = track[i]
        if not _usable(pos, cfg) or pos.roll_y_top_px - last_y < step:
            i += 1
            continue
        chosen, reason = pos, "travel"
        if cfg.avoid_hand and pos.hand_visible:
            chosen, reason = pos, "hand_fallback"
            j = i + 1
            while j < n and track[j].roll_y_top_px - last_y <= max_step:
                cand = track[j]
                if _usable(cand, cfg) and not cand.hand_visible:
                    chosen, reason = cand, "hand_avoided"
                    break
                j += 1
        samples.append(Sample(chosen.frame, chosen.roll_y_top_px, reason))  # type: ignore[arg-type]
        last_y = chosen.roll_y_top_px
        i = chosen.frame + 1

    tail = track[-1]
    if tail.roll_y_top_px > last_y and samples[-1].frame != tail.frame:
        samples.append(Sample(tail.frame, tail.roll_y_top_px, "last"))
    return SamplingPlan(tuple(samples), view_height_px, step, cfg)


def coverage(sampling: SamplingPlan, track: Sequence[FramePosition]) -> float:
    """Fraction of the roll seen by at least one sampled frame (1.0 = every centimetre)."""
    if not track or not sampling.samples:
        return 0.0
    h = sampling.view_height_px
    start, end = track[0].roll_y_top_px, track[-1].roll_y_top_px + h
    if end <= start:
        return 1.0
    covered = 0.0
    reach = start
    for s in sorted(sampling.samples, key=lambda s: s.roll_y_top_px):
        lo, hi = max(s.roll_y_top_px, reach), s.roll_y_top_px + h
        if hi > lo:
            covered += hi - lo
            reach = hi
    return min(1.0, covered / (end - start))


class StreamingSampler:
    """Online version of ``plan`` for live sources: decides frame by frame, no look-ahead.

    A hand frame is deferred while the travel budget allows; if the budget runs out it is taken.
    """

    def __init__(self, view_height_px: int, cfg: SamplingConfig | None = None) -> None:
        self.cfg = cfg or SamplingConfig()
        self.step = view_height_px * (1 - self.cfg.overlap)
        self.max_step = view_height_px * (1 - self.cfg.min_overlap)
        self.last_y: float | None = None

    def offer(self, pos: FramePosition) -> SampleReason | None:
        if not _usable(pos, self.cfg):
            return None
        if self.last_y is None:
            self.last_y = pos.roll_y_top_px
            return "first"
        moved = pos.roll_y_top_px - self.last_y
        if moved < self.step:
            return None
        if self.cfg.avoid_hand and pos.hand_visible and moved < self.max_step:
            return None  # wait for a clean frame while overlap allows
        self.last_y = pos.roll_y_top_px
        if self.cfg.avoid_hand and pos.hand_visible:
            return "hand_fallback"
        return "travel"
