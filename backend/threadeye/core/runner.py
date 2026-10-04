"""The inspection runner: frames in → defects, non-defects and a live score out (PLAN.md §6).

``advance(until_frame)`` processes every frame after the checkpoint up to ``until_frame`` and returns
the events it produced. The same call serves all three clocks:

- browser-clocked live inspection (M2): the browser plays the video and calls /advance
- headless runs (tests, verification, benchmark): ``run_to_end()``
- server-clocked webcams (later): the worker calls it as frames arrive

Pure: no database, no web framework. The caller persists the events (with their idempotency keys)
and the defect projections in one transaction, which is what makes a resume after a power cut safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from threadeye.core.dedupe import DedupeConfig, Deduper, DefectTrack, Sighting
from threadeye.core.frames import FramePosition, FrameSource, SourceInfo
from threadeye.core.geometry import INCH_CM, view_to_roll
from threadeye.core.geometry import truncation as truncation_of
from threadeye.core.nondefect import NonDefectFilter, NonDefectVerdict
from threadeye.core.providers import DetectorProvider
from threadeye.core.sampling import SamplingConfig, SamplingPlan, coverage, plan
from threadeye.core.scoring.four_point import (
    RollGeometry,
    ScorableDefect,
    ScoreResult,
    points_budget,
    score_roll,
)
from threadeye.core.scoring.profile import RuleProfile
from threadeye.core.taxonomy import Taxonomy, load_default_taxonomy


@dataclass(frozen=True)
class RollSpec:
    """What scoring needs to know about the roll."""

    width_in: float
    declared_length_yd: float | None = None


@dataclass(frozen=True)
class RunnerEvent:
    type: str
    payload: dict[str, Any]
    idempotency_key: str


@dataclass
class DefectState:
    status: str = "pending"
    reclassified_to: str | None = None


@dataclass
class _Progress:
    frames_processed: int = 0
    frames_sampled: int = 0
    detections: int = 0
    yards_inspected: float = 0.0
    last_state: str | None = None
    sampled_positions: list[FramePosition] = field(default_factory=list)


class Runner:
    def __init__(
        self,
        source: FrameSource,
        provider: DetectorProvider,
        profile: RuleProfile,
        roll: RollSpec,
        *,
        inspection_id: str = "headless",
        taxonomy: Taxonomy | None = None,
        sampling: SamplingConfig | None = None,
        dedupe: DedupeConfig | None = None,
    ) -> None:
        self.source = source
        self.provider = provider
        self.profile = profile
        self.roll = roll
        self.inspection_id = inspection_id
        self.taxonomy = taxonomy or load_default_taxonomy()
        self.info: SourceInfo = source.open()
        provider.prepare(self.info)
        calib = self.info.calibration
        self.calibration = calib
        track = source.track()
        if track is None:
            raise NotImplementedError("live (server-clocked) sources use StreamingSampler; arrives with webcams")
        self.track = track
        self.plan: SamplingPlan = plan(track, calib.view_height_px, sampling)
        self._sample_frames = {s.frame: s for s in self.plan.samples}
        self.deduper = Deduper(dedupe)
        band_cm = (calib.selvage_band_px or 0.0) / calib.px_per_cm
        self.filter = NonDefectFilter(self.taxonomy, calib.fabric_width_cm, band_cm)
        self.states: dict[int, DefectState] = {}
        self.checkpoint = -1
        self._progress = _Progress()

    # ------------------------------------------------------------------------------------ helpers
    def _key(self, frame: int, kind: str, suffix: str = "") -> str:
        return f"{self.inspection_id}:{frame}:{kind}{':' + suffix if suffix else ''}"

    def _event(self, frame: int, type_: str, payload: dict[str, Any], suffix: str = "") -> RunnerEvent:
        return RunnerEvent(type_, payload, self._key(frame, type_, suffix))

    def _verdict(self, track: DefectTrack) -> NonDefectVerdict:
        return self.filter.classify(track)

    def defect_view(self, track: DefectTrack, points: int | None = None) -> dict[str, Any]:
        """The defect projection: what the UI, reports and the database store."""
        verdict = self._verdict(track)
        state = self.states.get(track.track_no, DefectState())
        box = track.box
        predicted = self.taxonomy.resolve(track.sightings[0].cls)
        current = state.reclassified_to or self.taxonomy.resolve(track.cls)
        best = track.best_sighting
        return {
            "defect_no": track.defect_no,
            "origin": "detector",
            "predicted_cls": predicted,
            "current_cls": current,
            "kind": "nondefect" if verdict.category else "defect",
            "nondefect_category": verdict.category,
            "uncertain": verdict.uncertain,
            "status": state.status,
            "start_yd": round(box.start_yd, 4),
            "end_yd": round(box.end_yd, 4),
            "center_yd": round(box.center_yd, 4),
            "across_start_cm": round(box.across_start_cm, 2),
            "across_end_cm": round(box.across_end_cm, 2),
            "length_in": round(box.length_in, 3),
            "length_source": "pixels",
            "is_running": track.is_running,
            "sightings": len(track.sightings),
            "first_frame": track.first_frame,
            "last_frame": track.last_frame,
            "best_frame": best.frame,
            "explanation": verdict.explanation if verdict.category else track.explanation,
            "points": points,
            "provider": self.provider.info.label,
        }

    # ------------------------------------------------------------------------------------ main loop
    def advance(self, until_frame: int) -> list[RunnerEvent]:
        """Process frames (checkpoint, until_frame]. Idempotent: re-processing returns no events."""
        if until_frame <= self.checkpoint:
            return []
        events: list[RunnerEvent] = []

        def needs_image(p: FramePosition) -> bool:
            return self.provider.info.requires_image and p.frame in self._sample_frames

        changed: dict[int, DefectTrack] = {}
        calib = self.calibration
        progress = self._progress

        for packet in self.source.read(self.checkpoint + 1, until_frame + 1, needs_image):
            pos = packet.pos
            progress.frames_processed += 1
            progress.yards_inspected = max(progress.yards_inspected, pos.bottom_yd)
            if progress.last_state is not None and pos.state != progress.last_state:
                kind = "machine.stopped" if pos.state == "stopped" else "machine.started"
                events.append(self._event(pos.frame, kind, {"frame": pos.frame, "at_yd": round(pos.bottom_yd, 3)}))
            progress.last_state = pos.state

            sample = self._sample_frames.get(pos.frame)
            if sample is not None:
                progress.frames_sampled += 1
                progress.sampled_positions.append(pos)
                events.append(
                    self._event(
                        pos.frame,
                        "frame.sampled",
                        {
                            "frame": pos.frame,
                            "top_yd": round(pos.top_yd, 4),
                            "bottom_yd": round(pos.bottom_yd, 4),
                            "hand_visible": bool(pos.hand_visible),
                            "sample_reason": sample.reason,
                            "image": packet.image is not None,
                        },
                    )
                )
                result = self.provider.detect(packet)
                scale = packet.image.scale if packet.image else 1.0
                mapped = []
                for det in result.detections:
                    roll_box = view_to_roll(det.bbox_px, pos, calib, scale)
                    view_box = tuple(v / scale for v in det.bbox_px)
                    trunc = truncation_of(view_box, calib)  # type: ignore[arg-type]
                    cy = (view_box[1] + view_box[3]) / 2
                    track, _created = self.deduper.add(
                        Sighting(
                            frame=pos.frame,
                            box=roll_box,
                            cls=det.cls,
                            confidence=det.confidence,
                            explanation=det.explanation,
                            truncated=trunc,
                            hand_visible=bool(pos.hand_visible),
                            centrality_px=abs(cy - calib.view_height_px / 2),
                        )
                    )
                    changed[track.track_no] = track
                    mapped.append(
                        {
                            "cls": det.cls,
                            "confidence": det.confidence,
                            "explanation": det.explanation,
                            "bbox_px": [round(v, 1) for v in det.bbox_px],
                            "truncated": trunc,
                            "defect_no": track.defect_no,
                        }
                    )
                progress.detections += len(mapped)
                events.append(
                    self._event(
                        pos.frame,
                        "detection.batch",
                        {
                            "frame": pos.frame,
                            "provider": result.provider.label,
                            "latency_ms": round(result.latency_ms, 2),
                            "error": result.error,
                            "detections": mapped,
                        },
                    )
                )
            self.checkpoint = pos.frame

        if changed:
            score = self.score(final=False)
            for track in sorted(changed.values(), key=lambda t: t.track_no):
                pts = score.defects[track.defect_no].points if score else None
                events.append(
                    self._event(
                        self.checkpoint,
                        "defect.upserted",
                        {"defect": self.defect_view(track, pts), "change": "detected"},
                        suffix=track.defect_no,
                    )
                )
        if self.checkpoint >= 0:
            events.append(self._event(self.checkpoint, "score.updated", self.score_payload()))
        return events

    def run_to_end(self) -> list[RunnerEvent]:
        return self.advance(len(self.track) - 1)

    # ------------------------------------------------------------------------------------ status
    def set_status(self, defect_no: str, status: str, reclassify_to: str | None = None) -> None:
        if status not in {"pending", "confirmed", "rejected"}:
            raise ValueError(f"bad status {status!r}")
        for t in self.deduper.tracks:
            if t.defect_no == defect_no:
                self.states[t.track_no] = DefectState(status, reclassify_to)
                return
        raise KeyError(defect_no)

    def confirm_all(self) -> None:
        """Headless helper: accept every detector defect (tests, verification with a perfect preset)."""
        for t in self.deduper.tracks:
            self.states.setdefault(t.track_no, DefectState()).status = "confirmed"

    # ------------------------------------------------------------------------------------ scoring
    @property
    def yards_inspected(self) -> float:
        return self._progress.yards_inspected

    def scorable(self) -> list[ScorableDefect]:
        out = []
        for t in self.deduper.tracks:
            view = self.defect_view(t)
            cls = view["current_cls"]
            dc = self.taxonomy.classes.get(cls)
            out.append(
                ScorableDefect(
                    defect_id=t.defect_no,
                    cls=cls,
                    is_hole=bool(dc and dc.is_hole),
                    length_in=t.box.length_in,
                    start_yd=t.box.start_yd,
                    end_yd=t.box.end_yd,
                    center_yd=t.box.center_yd,
                    across_start_cm=t.box.across_start_cm,
                    across_end_cm=t.box.across_end_cm,
                    status=view["status"],
                    kind=view["kind"],
                )
            )
        return out

    def geometry(self) -> RollGeometry | None:
        length = (
            self.roll.declared_length_yd
            if self.profile.length_basis == "declared" and self.roll.declared_length_yd
            else self.yards_inspected
        )
        if not length:
            return None
        return RollGeometry(length, self.roll.width_in, self.calibration.fabric_width_cm)

    def score(self, *, final: bool = False) -> ScoreResult | None:
        geometry = self.geometry()
        if geometry is None:
            return None
        return score_roll(self.scorable(), geometry, self.profile, final=final)

    def coverage(self) -> float:
        sampled = SamplingPlan(
            tuple(s for s in self.plan.samples if s.frame <= self.checkpoint),
            self.plan.view_height_px,
            self.plan.step_px,
            self.plan.config,
        )
        seen = [p for p in self.track if p.frame <= self.checkpoint]
        return coverage(sampled, seen)

    def score_payload(self) -> dict[str, Any]:
        s = self.score(final=False)
        p = self.profile
        tracks = [self.defect_view(t) for t in self.deduper.tracks]
        nondefects: dict[str, int] = {}
        for v in tracks:
            if v["nondefect_category"]:
                nondefects[v["nondefect_category"]] = nondefects.get(v["nondefect_category"], 0) + 1
        return {
            "provisional_points": s.total_points if s else 0,
            "per_100_provisional": round(s.per_100, p.per100_rounding) if s else None,
            "provisional_verdict": s.verdict if s else None,
            "cells": {str(k): v for k, v in s.cells.items()} if s else {},
            "threshold": p.threshold_per_100,
            "borderline_below": p.borderline.below,
            "borderline_above": p.borderline.above,
            "points_budget": round(points_budget(p, self.roll.declared_length_yd, self.roll.width_in), 2)
            if self.roll.declared_length_yd
            else None,
            "yards_inspected": round(self.yards_inspected, 3),
            "coverage_pct": round(self.coverage() * 100, 1),
            "defects": sum(1 for v in tracks if v["kind"] == "defect"),
            "nondefects_ignored": nondefects,
        }


def fabric_width_in(fabric_width_cm: float) -> float:
    return fabric_width_cm / INCH_CM
