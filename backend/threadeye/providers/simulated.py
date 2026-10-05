"""SimulatedDetector: an imperfect detector driven by the simulator's answer key (PLAN.md §6.3).

NOT AI. It lets the whole pipeline (sampling, mapping, de-dup, non-defect filter, confirmation,
scoring, benchmark) be built and measured before a real model exists. ``is_simulated=True`` makes every
screen and report show "SIMULATED DETECTIONS". ``confidence`` is always ``None``.

It uses only frame positions and the answer key, never pixels, so it needs no images.
Every random choice is keyed by (seed, object, frame): results do not depend on call order and are
identical after a resume.

Imperfections (all configurable; the ``perfect`` preset turns every one off):
- miss_rate: a defect is never reported (per defect) or skipped in some frames (per sighting)
- jitter_px: Gaussian noise on each box edge
- confusion_rate: the defect is reported as another defect class
- nuisance_flag_rate: a sticker/thread/wrinkle is reported AS A DEFECT (a false alarm)
- nuisance_recognized_rate: a nuisance is reported as its non-defect class (filtered, not scored)
- selvage_pinhole_fp_rate: a small hole is reported in the selvage band (stenter pin holes)
- random_fp_per_frame: an unexplained false alarm on plain fabric
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from threadeye.core.frames import Calibration, FramePacket, SourceInfo
from threadeye.core.geometry import YARD_CM, clip_to_view
from threadeye.core.providers import (
    BBox,
    Detection,
    DetectionResult,
    DetectorProvider,
    ProviderContext,
    ProviderInfo,
    ProviderNotConfigured,
)
from threadeye.core.taxonomy import Taxonomy, load_default_taxonomy

if TYPE_CHECKING:  # typing only: the key arrives as data through ProviderContext
    from threadeye.datasets.answer_key import AnswerKey

VERSION = "1.0.0"

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

# What a confused detector might call a nuisance when it raises a false alarm.
FALSE_ALARM_CLASS = {"sticker": "stain", "loose_thread": "slub", "wrinkle": "crease_mark"}


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(config), sort_keys=True).encode()).hexdigest()[:16]


class SimulatedDetector(DetectorProvider):
    def __init__(self, config: Mapping[str, Any], ctx: ProviderContext) -> None:
        unknown = set(config) - set(PERFECT)
        if unknown:
            raise ValueError(f"unknown simulated-detector settings: {', '.join(sorted(unknown))}")
        super().__init__({**PERFECT, **dict(config)}, ctx)
        self.taxonomy: Taxonomy = load_default_taxonomy()
        self._calib: Calibration | None = None
        key = ctx.answer_key
        self._key: AnswerKey | None = key if hasattr(key, "defects") and hasattr(key, "nuisances") else None
        self._defect_classes = sorted(
            c for c, dc in self.taxonomy.classes.items() if dc.kind == "defect" and c != "other_defect"
        )

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
            classes=tuple(self.taxonomy.classes),
            config_hash=config_hash(self.config),
        )

    # ------------------------------------------------------------------------------------ helpers
    def _rng(self, *key: object) -> random.Random:
        digest = hashlib.sha256("|".join(map(str, (self.config["seed"], *key))).encode()).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311  (simulation, not crypto)

    def prepare(self, source: SourceInfo) -> None:
        dataset_dir = self.ctx.extras.get("dataset_dir")
        if self._key is None and dataset_dir:
            # The only runtime path from the API to ground truth, and it stays inside this provider
            # (import-linter allows exactly this one import; see pyproject.toml).
            from threadeye.datasets.answer_key import load_answer_key

            self._key = load_answer_key(dataset_dir, require_media=False)
        if self._key is None:
            raise ProviderNotConfigured(
                "SimulatedDetector needs the dataset's answer key (ProviderContext.answer_key or extras['dataset_dir'])"
            )
        self._calib = source.calibration

    def _jitter(self, box: BBox, rng: random.Random) -> BBox:
        s = float(self.config["jitter_px"])
        if s <= 0:
            return box
        x0, y0, x1, y1 = (v + rng.gauss(0.0, s) for v in box)
        return (min(x0, x1 - 1), min(y0, y1 - 1), max(x1, x0 + 1), max(y1, y0 + 1))

    # ------------------------------------------------------------------------------------ detect
    def detect(self, frame: FramePacket) -> DetectionResult:
        if self._calib is None or self._key is None:
            raise ProviderNotConfigured("call prepare() first")
        started = time.perf_counter()
        calib, pos = self._calib, frame.pos
        ppc = calib.px_per_cm
        view_h = calib.view_height_px
        x_off = pos.fabric_x0_px or 0.0
        top = pos.roll_y_top_px
        out: list[Detection] = []
        min_vis = float(self.config["min_visible_fraction"])

        for gt in self._key.defects:
            # Answer-key boxes are ROLL coordinates: x from the fabric's left edge, y absolute.
            full = (gt.x0_px + x_off, gt.y0_px - top, gt.x1_px + x_off, gt.y1_px - top)
            visible = clip_to_view(full, calib)
            if visible is None or (visible[3] - visible[1]) < min_vis * (full[3] - full[1]):
                continue
            if self.config["miss_mode"] == "per_defect":
                if self._rng("miss", gt.defect_id).random() < self.config["miss_rate"]:
                    continue
            elif self._rng("miss", gt.defect_id, pos.frame).random() < self.config["miss_rate"]:
                continue
            rng = self._rng("box", gt.defect_id, pos.frame)
            box = clip_to_view(self._jitter(visible, rng), calib) or visible
            true_cls = self.taxonomy.resolve(gt.cls)
            cls, note = true_cls, ""
            crng = self._rng("confuse", gt.defect_id)
            if crng.random() < self.config["confusion_rate"]:
                cls = crng.choice([c for c in self._defect_classes if c != true_cls] or [true_cls])
                note = f", class confused from {true_cls}"
            jitter = ", box jitter" if self.config["jitter_px"] else ""
            out.append(
                Detection(
                    bbox_px=box,
                    cls=cls,
                    confidence=None,
                    explanation=f"SIMULATED: answer-key defect {gt.defect_id} ({true_cls}){jitter}{note}",
                    attributes={"answer_key_id": gt.defect_id},
                )
            )

        for i, n in enumerate(self._key.nuisances):
            if n.appears_frame is not None and pos.frame < n.appears_frame:
                continue
            half = n.extent_cm / 2
            along_c = n.center_yd * YARD_CM
            full = (
                (n.across_cm - half) * ppc + x_off,
                (along_c - half) * ppc - top,
                (n.across_cm + half) * ppc + x_off,
                (along_c + half) * ppc - top,
            )
            visible = clip_to_view(full, calib)
            if visible is None:
                continue
            decide = self._rng("nuisance", i).random()
            flag = float(self.config["nuisance_flag_rate"])
            recognise = float(self.config["nuisance_recognized_rate"])
            if decide < flag:
                cls = FALSE_ALARM_CLASS.get(n.type, "other_defect")
                why = f"SIMULATED FALSE ALARM: a {n.type.replace('_', ' ')} reported as {cls}"
            elif decide < flag + recognise * (1 - flag):
                cls = n.type
                why = f"SIMULATED: recognised a {n.type.replace('_', ' ')} (not a defect)"
            else:
                continue
            out.append(
                Detection(bbox_px=visible, cls=cls, confidence=None, explanation=why, attributes={"nuisance": n.type})
            )

        prng = self._rng("pinhole", pos.frame)
        if prng.random() < self.config["selvage_pinhole_fp_rate"]:
            band_px = calib.selvage_band_px or 0.8 * ppc
            cx = x_off + prng.uniform(0.2 * band_px, 0.8 * band_px)
            cy = prng.uniform(0.1, 0.9) * view_h
            r = 0.2 * ppc
            out.append(
                Detection(
                    (cx - r, cy - r, cx + r, cy + r),
                    "hole",
                    None,
                    "SIMULATED FALSE ALARM: stenter pin hole in the selvage band",
                    {"nuisance": "pin_hole"},
                )
            )

        frng = self._rng("random_fp", pos.frame)
        if frng.random() < self.config["random_fp_per_frame"]:
            fabric_w_px = calib.fabric_width_cm * ppc
            cx = x_off + frng.uniform(0.2, 0.8) * fabric_w_px
            cy = frng.uniform(0.1, 0.9) * view_h
            r = 0.6 * ppc
            out.append(
                Detection(
                    (cx - r, cy - r, cx + r, cy + r),
                    "other_defect",
                    None,
                    "SIMULATED FALSE ALARM: unexplained",
                    {"nuisance": "unexplained"},
                )
            )

        return DetectionResult(
            frame=pos.frame,
            detections=out,
            latency_ms=(time.perf_counter() - started) * 1000,
            provider=self.info,
        )
