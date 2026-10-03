"""DetectorProvider contract (PLAN.md §6.2, §13).

Every detector (simulated, API, local ONNX model, classical baseline) implements this interface.
Nothing downstream (mapping, de-dup, non-defect filter, scoring, UI, reports) may depend on which
provider is active. The provider's ``ProviderInfo`` is pinned on each inspection and printed on
every screen and report. ``is_simulated`` drives the "SIMULATED DETECTIONS" banner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from threadeye.core.frames import FramePacket, SourceInfo

BBox = tuple[float, float, float, float]
"""x0, y0, x1, y1 in view pixels of THIS frame (after the view_region crop)."""

ProviderKind = Literal["simulated", "api", "local_model", "classical"]
BBoxQuality = Literal["precise", "approximate"]


@dataclass(frozen=True)
class Detection:
    bbox_px: BBox
    cls: str
    """Taxonomy class id: a defect class or a non-defect class (sticker, loose_thread, ...)."""
    confidence: float | None
    """None unless the provider's confidence is calibrated. Never invent a number."""
    explanation: str
    """Human-readable reason. Required."""
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        x0, y0, x1, y1 = self.bbox_px
        if not (x1 > x0 and y1 > y0):
            raise ValueError(f"degenerate bbox {self.bbox_px}")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be None or within [0, 1]")
        if not self.explanation.strip():
            raise ValueError("explanation is required")


@dataclass(frozen=True)
class ProviderInfo:
    provider_id: str
    version: str
    display_name: str
    kind: ProviderKind
    is_simulated: bool
    requires_image: bool
    calibrated_confidence: bool
    bbox_quality: BBoxQuality
    classes: tuple[str, ...]
    config_hash: str

    @property
    def label(self) -> str:
        """Short label for UI/report footers, e.g. ``simulated@1.0.0``."""
        return f"{self.provider_id}@{self.version}"


@dataclass(frozen=True)
class DetectionResult:
    frame: int
    detections: list[Detection]
    latency_ms: float
    provider: ProviderInfo
    error: str | None = None
    """A provider failure is reported here and surfaced to the inspector, never hidden."""


@dataclass(frozen=True)
class ProviderContext:
    """What a provider may use. ``answer_key`` is given ONLY to providers of kind "simulated"."""

    seed: int = 0
    answer_key: Any | None = None
    storage: Any | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)


class DetectorProvider(ABC):
    def __init__(self, config: Mapping[str, Any], ctx: ProviderContext) -> None:
        self.config = dict(config)
        self.ctx = ctx

    @property
    @abstractmethod
    def info(self) -> ProviderInfo: ...

    def prepare(self, source: SourceInfo) -> None:  # noqa: B027  (optional hook)
        """Load a model / oracle and warm up. Called once per inspection."""

    @abstractmethod
    def detect(self, frame: FramePacket) -> DetectionResult: ...

    def close(self) -> None:  # noqa: B027  (optional hook)
        """Release resources."""


class ProviderNotConfigured(RuntimeError):
    """The provider exists as a stub or is missing configuration (API key, model file)."""
