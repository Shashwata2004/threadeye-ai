"""What every source reader produces: images with boxes in their own pixels, before any processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    src_cls: str
    """The class name as the source spells it (mapped to the ThreadEye taxonomy in classes.py)."""
    cls: str = ""

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class ImageRecord:
    source: str
    path: Path
    width: int
    height: int
    boxes: list[Box] = field(default_factory=list)
    group: str = ""
    """Images in one group always land in the same split (same physical defect, same photo session,
    augmented copies of one original…). Near-duplicate grouping adds to this."""
    defect_free: bool = False
    force_split: str | None = None
    """E.g. "test" for the AITEX fabric the demo sample roll is rendered from."""
    rotate: int = 0
    """Degrees clockwise (90 or 270) to turn the stored image so it matches its labels: a re-export that
    dropped the EXIF orientation left a fifth of the FabricSpotDefect photos sideways (sources.open_rgb)."""

    @property
    def key(self) -> str:
        """Unique per image and the same on every machine: sources reuse file names in their folders (Moratuwa
        hole/22.jpg and horizontal/22.jpg; WFDD 000.png in every fabric and defect folder), so the last four
        path parts, not the name alone."""
        return f"{self.source}:{'/'.join(self.path.parts[-4:])}"
