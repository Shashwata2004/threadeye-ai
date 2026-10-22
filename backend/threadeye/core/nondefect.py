"""False-alarm filter: things on real fabric that are NOT defects (PLAN.md §6.1 step 7).

Stickers, loose threads, handling wrinkles, stenter pin holes, the board beside the fabric and the
inspector's hand cause most real-world false alarms. They are shown (grey, dashed), never scored, and
counted per category, and the inspector can promote one to a defect.

Rules, first match wins:
  a. the provider itself said it is a non-defect class
  b. the box lies outside the fabric                          → board
  c. a tiny hole inside the selvage band                      → pin_hole
  d. a yarn fault inside the selvage band                     → selvage_weave
  e. only ever seen with the hand in view                     → still a defect, flagged uncertain

A box is inside the selvage band when its centre is: the detector's box spills a little past the narrow band
around what it saw there. The selvage is woven differently from the body and carries the stenter pin row, and
the detector reads both as missing or broken yarns (the line-scan demo roll, 2026-10-22: 35 of 54 false
alarms). Inspection excludes the selvage like the buyers' 4-point rules do; a fault that reaches into the
body has its centre outside the band and stays a defect. Selvage faults are placed, not recognised: one the
inspector promotes is shown as a selvage defect (``selvage_class``). Public data has too few selvage
examples to teach a detector the class.
"""

from __future__ import annotations

from dataclasses import dataclass

from threadeye.core.dedupe import DefectTrack
from threadeye.core.geometry import RollBox
from threadeye.core.taxonomy import Taxonomy

INCH_CM = 2.54


@dataclass(frozen=True)
class NonDefectVerdict:
    category: str | None
    """None = a defect; otherwise the non-defect class (sticker, board, pin_hole, …)."""
    explanation: str
    uncertain: str | None = None


@dataclass(frozen=True)
class NonDefectConfig:
    pinhole_max_in: float = 0.3
    selvage_faults: frozenset[str] = frozenset({"broken_yarn", "missing_yarn", "other_defect"})
    """Detector classes that are selvage weave inside the selvage band, and a selvage defect when promoted
    (stains and holes keep theirs)."""


class NonDefectFilter:
    def __init__(
        self,
        taxonomy: Taxonomy,
        fabric_width_cm: float,
        selvage_band_cm: float,
        cfg: NonDefectConfig | None = None,
    ) -> None:
        self.taxonomy = taxonomy
        self.fabric_width_cm = fabric_width_cm
        self.selvage_band_cm = selvage_band_cm
        self.cfg = cfg or NonDefectConfig()

    def in_selvage(self, box: RollBox) -> bool:
        if self.selvage_band_cm <= 0:
            return False
        center = (box.across_start_cm + box.across_end_cm) / 2
        return center <= self.selvage_band_cm or center >= self.fabric_width_cm - self.selvage_band_cm

    def selvage_class(self, cls: str, box: RollBox) -> str:
        """The class to show for a detector defect: a yarn fault inside the selvage band (a non-defect until the
        inspector promotes it) is a selvage defect."""
        if cls in self.cfg.selvage_faults and self.in_selvage(box):
            return "selvage_defect"
        return cls

    def classify(self, track: DefectTrack) -> NonDefectVerdict:
        cls = self.taxonomy.resolve(track.cls)
        box = track.box
        if self.taxonomy.is_nondefect(cls):
            return NonDefectVerdict(cls, f"detector reported a non-defect: {cls}")
        if box.across_end_cm <= 0 or box.across_start_cm >= self.fabric_width_cm:
            return NonDefectVerdict("board", "outside the fabric edges (the board beside the fabric)")
        in_selvage = self.in_selvage(box)
        is_hole = cls in self.taxonomy.classes and self.taxonomy.classes[cls].is_hole
        if in_selvage and is_hole and box.length_in < self.cfg.pinhole_max_in:
            return NonDefectVerdict(
                "pin_hole", f"hole under {self.cfg.pinhole_max_in} in inside the selvage band (stenter pin)"
            )
        if in_selvage and cls in self.cfg.selvage_faults:
            return NonDefectVerdict(
                "selvage_weave", "yarn-like mark inside the selvage band (selvage weave, stenter pins)"
            )
        if all(s.hand_visible for s in track.sightings):
            return NonDefectVerdict(None, "defect", uncertain="hand_in_view")
        return NonDefectVerdict(None, "defect")
