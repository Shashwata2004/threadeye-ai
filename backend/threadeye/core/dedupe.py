"""Merge repeated sightings of the same physical defect (PLAN.md §6.1 step 6).

With 15 % overlap, a defect near a frame edge is seen twice; after a resume it may be seen again. In
roll coordinates those sightings coincide, so a new sighting joins an existing track when roll-box IoU
> 0.3 or centres are within 3 cm. A running defect longer than the view is only ever seen truncated by
the frame edge; such pieces are joined into one track by their union.

Box of a track = mean of its non-truncated sightings, or the union when all sightings are truncated.
Class = majority vote; ties go to the higher summed confidence, then to the first class seen.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from threadeye.core.geometry import RollBox, Truncation


@dataclass(frozen=True)
class Sighting:
    frame: int
    box: RollBox
    cls: str
    confidence: float | None
    explanation: str
    truncated: Truncation = None
    hand_visible: bool = False
    centrality_px: float = 0.0
    """Distance of the box centre from the view centre; smaller = better evidence photo."""


@dataclass
class DefectTrack:
    track_no: int
    sightings: list[Sighting] = field(default_factory=list)

    @property
    def defect_no(self) -> str:
        return f"D-{self.track_no:02d}"

    @property
    def box(self) -> RollBox:
        full = [s.box for s in self.sightings if s.truncated is None]
        if full:
            return RollBox.mean(full)
        out = self.sightings[0].box
        for s in self.sightings[1:]:
            out = out.union(s.box)
        return out

    @property
    def cls(self) -> str:
        votes = Counter(s.cls for s in self.sightings)
        top = max(votes.values())
        tied = [c for c, n in votes.items() if n == top]
        if len(tied) == 1:
            return tied[0]
        conf = {c: sum(s.confidence or 0.0 for s in self.sightings if s.cls == c) for c in tied}
        best = max(conf.values())
        first_seen = [s.cls for s in self.sightings if s.cls in tied and conf[s.cls] == best]
        return first_seen[0]

    @property
    def is_running(self) -> bool:
        return all(s.truncated is not None for s in self.sightings)

    @property
    def best_sighting(self) -> Sighting:
        clean = [s for s in self.sightings if not s.hand_visible] or self.sightings
        return min(clean, key=lambda s: (s.truncated is not None, s.centrality_px))

    @property
    def first_frame(self) -> int:
        return min(s.frame for s in self.sightings)

    @property
    def last_frame(self) -> int:
        return max(s.frame for s in self.sightings)

    @property
    def explanation(self) -> str:
        return self.best_sighting.explanation


@dataclass(frozen=True)
class DedupeConfig:
    iou_threshold: float = 0.3
    center_cm: float = 3.0
    search_window_cm: float = 120.0
    """Only tracks within this along-roll distance are compared (keeps it O(1) per sighting)."""
    running_gap_cm: float = 1.0
    running_across_overlap: float = 0.5


class Deduper:
    def __init__(self, cfg: DedupeConfig | None = None) -> None:
        self.cfg = cfg or DedupeConfig()
        self.tracks: list[DefectTrack] = []

    def _score(self, track: DefectTrack, s: Sighting) -> float | None:
        """Match strength (higher is better) or None if the sighting does not belong to the track."""
        box = track.box
        if abs(box.along_center_cm - s.box.along_center_cm) > self.cfg.search_window_cm + box.height_cm:
            return None
        iou = box.iou(s.box)
        if iou > self.cfg.iou_threshold:
            return 1.0 + iou
        dist = box.center_distance_cm(s.box)
        if dist <= self.cfg.center_cm:
            return 1.0 - dist / (self.cfg.center_cm * 10)
        if s.truncated is not None and track.is_running and self._continues(box, s.box):
            return 0.5
        return None

    def _continues(self, a: RollBox, b: RollBox) -> bool:
        """b extends running defect a along the roll (touching/overlapping, same across band)."""
        gap = max(a.along_start_cm, b.along_start_cm) - min(a.along_end_cm, b.along_end_cm)
        if gap > self.cfg.running_gap_cm:
            return False
        across = min(a.across_end_cm, b.across_end_cm) - max(a.across_start_cm, b.across_start_cm)
        narrower = min(a.width_cm, b.width_cm)
        return narrower > 0 and across / narrower >= self.cfg.running_across_overlap

    def add(self, s: Sighting) -> tuple[DefectTrack, bool]:
        """Attach a sighting; returns (track, created)."""
        scored = [(sc, t) for t in self.tracks if (sc := self._score(t, s)) is not None]
        if scored:
            _, track = max(scored, key=lambda x: x[0])
            track.sightings.append(s)
            return track, False
        track = DefectTrack(track_no=len(self.tracks) + 1, sightings=[s])
        self.tracks.append(track)
        return track, True
