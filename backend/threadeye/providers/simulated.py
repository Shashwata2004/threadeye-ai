"""SimulatedDetector: an imperfect detector driven by the simulator's answer key.

NOT AI. It exists so the whole pipeline (sampling, mapping, de-dup, non-defect filter, confirmation,
scoring, benchmark) can be built and tested before a real model exists. ``is_simulated=True`` makes
every screen and report show "SIMULATED DETECTIONS". ``confidence`` is always ``None``.

M0: interface + metadata only. M1 (owner C): visibility, mapping roll → frame coordinates
``(x0_px + fabric_x0_px[f], y0_px - roll_y_top_px[f])``, seeded miss / jitter / class confusion /
nuisance false-alarm behaviour (PLAN.md §6.3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from threadeye.core.frames import FramePacket
from threadeye.core.providers import DetectionResult, DetectorProvider, ProviderContext, ProviderInfo
from threadeye.core.taxonomy import load_default_taxonomy

VERSION = "0.1.0"

PERFECT: Mapping[str, Any] = {
    "seed": 0,
    "miss_rate": 0.0,
    "miss_mode": "per_defect",
    "jitter_px": 0.0,
    "confusion_rate": 0.0,
    "nuisance_flag_rate": 0.0,
    "nuisance_recognized_rate": 1.0,
    "selvage_pinhole_fp_rate": 0.0,
    "random_fp_per_frame": 0.0,
    "min_visible_fraction": 0.5,
}
REALISTIC: Mapping[str, Any] = {
    **PERFECT,
    "seed": 42,
    "miss_rate": 0.10,
    "jitter_px": 4.0,
    "confusion_rate": 0.10,
    "nuisance_flag_rate": 0.30,
    "nuisance_recognized_rate": 0.50,
    "selvage_pinhole_fp_rate": 0.05,
}
PRESETS: Mapping[str, Mapping[str, Any]] = {"perfect": PERFECT, "realistic": REALISTIC}


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(config), sort_keys=True).encode()).hexdigest()[:16]


class SimulatedDetector(DetectorProvider):
    def __init__(self, config: Mapping[str, Any], ctx: ProviderContext) -> None:
        merged = {**PERFECT, **dict(config)}
        super().__init__(merged, ctx)

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="simulated",
            version=VERSION,
            display_name="Simulated detector (answer key, not AI)",
            kind="simulated",
            is_simulated=True,
            requires_image=False,
            calibrated_confidence=False,
            bbox_quality="precise",
            classes=tuple(load_default_taxonomy().classes),
            config_hash=config_hash(self.config),
        )

    def detect(self, frame: FramePacket) -> DetectionResult:
        raise NotImplementedError("SimulatedDetector.detect is implemented in M1 (PLAN.md §6.3)")
