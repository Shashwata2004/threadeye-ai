"""The inspection runner: frames in → defects, non-defects and a live score out (PLAN.md §6).

``advance(until_frame)`` processes every frame after the checkpoint up to ``until_frame`` and returns
the events it produced. The same call serves all three clocks:

- browser-clocked live inspection (M2): the browser plays the video and calls /advance
- headless runs (tests, verification, benchmark): ``run_to_end()``
- server-clocked webcams (later): the worker calls it as frames arrive

Inspector decisions (confirm, reject, change type, promote a non-defect, edit length, add a missed
defect) go through ``decide()`` and also return events; ``decide_many()`` applies one decision to
several defects at once (confirm every pending defect).

Pure: no database, no web framework. The caller persists the events (with their idempotency keys)
and the defect projections in one transaction, which is what makes a resume after a power cut safe.
``restore()`` rebuilds a runner from its stored events: detections are replayed (the detector is not
called again, so this also works for image-based detectors), then the inspector's decisions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from threadeye.core.dedupe import DedupeConfig, Deduper, DefectTrack, Sighting
from threadeye.core.frames import FrameImage, FramePosition, FrameSource, SourceInfo
from threadeye.core.geometry import INCH_CM, YARD_CM, RollBox, clip_to_view, view_to_roll
from threadeye.core.geometry import truncation as truncation_of
from threadeye.core.nondefect import NonDefectFilter, NonDefectVerdict
from threadeye.core.providers import DetectorProvider
from threadeye.core.sampling import SamplingConfig, SamplingPlan, coverage, plan
from threadeye.core.scoring.four_point import (
    DefectScore,
    RollGeometry,
    ScorableDefect,
    ScoreResult,
    points_budget,
    score_roll,
)
from threadeye.core.scoring.profile import RuleProfile
from threadeye.core.taxonomy import Taxonomy, load_default_taxonomy

DECISION_ACTIONS = ("confirm", "reject", "reclassify", "promote", "length", "manual", "reopen")


class DecisionError(ValueError):
    """The decision does not apply to this defect (e.g. confirming a non-defect)."""


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
    length_override_in: float | None = None
    promoted: bool = False
    reject_reason: str | None = None


@dataclass(frozen=True)
class ManualDefect:
    """A defect the detector missed, added by the inspector.

    Either drawn as a box on a video frame (``roll_box`` and ``bbox_px`` set: exact position and size,
    and the frame is an evidence photo and a training label), or entered by hand as a length at a yard.
    """

    defect_no: str
    cls: str
    center_yd: float
    across_cm: float
    length_in: float
    frame: int
    note: str | None = None
    roll_box: RollBox | None = None
    bbox_px: tuple[float, float, float, float] | None = None

    @property
    def box(self) -> RollBox:
        if self.roll_box is not None:
            return self.roll_box
        half = self.length_in * INCH_CM / 2
        along = self.center_yd * YARD_CM
        return RollBox(max(0.0, along - half), along + half, max(0.0, self.across_cm - half), self.across_cm + half)


@dataclass
class _Progress:
    frames_processed: int = 0
    frames_sampled: int = 0
    detections: int = 0
    yards_inspected: float = 0.0
    last_state: str | None = None
    sampled_positions: list[FramePosition] = field(default_factory=list)


KeyFn = Callable[[str, str], str]
"""(event type, defect number or "") → idempotency key."""


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
        self.manual: list[ManualDefect] = []
        self.manual_states: dict[str, DefectState] = {}
        self.checkpoint = -1
        self._progress = _Progress()
        self._emitted: dict[str, dict[str, Any]] = {}
        """Last defect view sent per defect: only changes are emitted as events."""
        self._evidence: dict[int, FrameImage] = {}
        """Pictures of frames the detector found a defect on (not only non-defects), until take_evidence()."""

    # ------------------------------------------------------------------------------------ helpers
    def _key(self, frame: int, kind: str, suffix: str = "") -> str:
        return f"{self.inspection_id}:{frame}:{kind}{':' + suffix if suffix else ''}"

    def _event(self, frame: int, type_: str, payload: dict[str, Any], suffix: str = "") -> RunnerEvent:
        return RunnerEvent(type_, payload, self._key(frame, type_, suffix))

    def _verdict(self, track: DefectTrack) -> NonDefectVerdict:
        return self.filter.classify(track)

    def _track(self, defect_no: str) -> DefectTrack | None:
        return next((t for t in self.deduper.tracks if t.defect_no == defect_no), None)

    def _manual(self, defect_no: str) -> ManualDefect | None:
        return next((m for m in self.manual if m.defect_no == defect_no), None)

    def defect_numbers(self) -> list[str]:
        return [t.defect_no for t in self.deduper.tracks] + [m.defect_no for m in self.manual]

    def defect_view(self, track: DefectTrack, points: int | None = None) -> dict[str, Any]:
        """The defect projection: what the UI, reports and the database store."""
        verdict = self._verdict(track)
        state = self.states.get(track.track_no, DefectState())
        box = track.box
        predicted = self.taxonomy.resolve(track.sightings[0].cls)
        current = state.reclassified_to or self.filter.selvage_class(self.taxonomy.resolve(track.cls), box)
        is_nondefect = bool(verdict.category) and not state.promoted
        best = track.best_sighting
        length = state.length_override_in or box.length_in
        return {
            "defect_no": track.defect_no,
            "origin": "detector",
            "predicted_cls": predicted,
            "current_cls": current,
            "kind": "nondefect" if is_nondefect else "defect",
            "nondefect_category": verdict.category if is_nondefect else None,
            "uncertain": verdict.uncertain,
            "status": state.status,
            "reject_reason": state.reject_reason,
            "start_yd": round(box.start_yd, 4),
            "end_yd": round(box.end_yd, 4),
            "center_yd": round(box.center_yd, 4),
            "across_start_cm": round(box.across_start_cm, 2),
            "across_end_cm": round(box.across_end_cm, 2),
            "length_in": round(length, 3),
            "length_source": "inspector" if state.length_override_in else "pixels",
            "is_running": track.is_running,
            "sightings": len(track.sightings),
            "first_frame": track.first_frame,
            "last_frame": track.last_frame,
            "best_frame": best.frame,
            "best_bbox_px": [round(v, 1) for v in best.view_box] if best.view_box else None,
            "explanation": verdict.explanation if is_nondefect else track.explanation,
            "points": points,
            "provider": self.provider.info.label,
        }

    def manual_view(self, m: ManualDefect, points: int | None = None) -> dict[str, Any]:
        state = self.manual_states.get(m.defect_no, DefectState(status="confirmed"))
        box = m.box
        note = f": {m.note}" if m.note else ""
        drawn = m.roll_box is not None
        how = "drawn on the video" if drawn else "entered by hand"
        return {
            "defect_no": m.defect_no,
            "origin": "manual",
            "predicted_cls": m.cls,
            "current_cls": state.reclassified_to or m.cls,
            "kind": "defect",
            "nondefect_category": None,
            "uncertain": None,
            "status": state.status,
            "reject_reason": state.reject_reason,
            "start_yd": round(box.start_yd, 4),
            "end_yd": round(box.end_yd, 4),
            "center_yd": round(m.center_yd, 4),
            "across_start_cm": round(box.across_start_cm, 2),
            "across_end_cm": round(box.across_end_cm, 2),
            "length_in": round(state.length_override_in or m.length_in, 3),
            "length_source": "pixels" if drawn and not state.length_override_in else "inspector",
            "is_running": False,
            "sightings": 0,
            "first_frame": m.frame,
            "last_frame": m.frame,
            "best_frame": m.frame,
            "best_bbox_px": [round(v, 1) for v in m.bbox_px] if m.bbox_px else None,
            "explanation": f"Added by the inspector, {how} (missed by the detector){note}",
            "points": points,
            "provider": "inspector",
        }

    # ------------------------------------------------------------------------------------ main loop
    def _ingest(self, pos: FramePosition, det: Mapping[str, Any], scale: float) -> tuple[DefectTrack, bool]:
        """Map one detection (view pixels of frame ``pos``) into the roll and de-duplicate it."""
        calib = self.calibration
        bbox = tuple(float(v) for v in det["bbox_px"])
        roll_box = view_to_roll(bbox, pos, calib, scale)  # type: ignore[arg-type]
        view_box = tuple(v / scale for v in bbox)
        trunc = truncation_of(view_box, calib)  # type: ignore[arg-type]
        cy = (view_box[1] + view_box[3]) / 2
        return self.deduper.add(
            Sighting(
                frame=pos.frame,
                box=roll_box,
                cls=str(det["cls"]),
                confidence=det.get("confidence"),
                explanation=str(det["explanation"]),
                truncated=trunc,
                hand_visible=bool(pos.hand_visible),
                centrality_px=abs(cy - calib.view_height_px / 2),
                view_box=view_box,  # type: ignore[arg-type]
            )
        )

    def take_evidence(self) -> dict[int, FrameImage]:
        """The pictures of the frames the detector found a defect on since the last call (for their evidence
        photos; frames with only non-defects, such as the selvage weave on every strip, wait for the browser's
        capture), cleared on reading."""
        evidence, self._evidence = self._evidence, {}
        return evidence

    def advance(self, until_frame: int) -> list[RunnerEvent]:
        """Process frames (checkpoint, until_frame]. Idempotent: re-processing returns no events."""
        until_frame = min(until_frame, len(self.track) - 1)
        if until_frame <= self.checkpoint:
            return []
        events: list[RunnerEvent] = []

        def needs_image(p: FramePosition) -> bool:
            return self.provider.info.requires_image and p.frame in self._sample_frames

        created: set[str] = set()
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
                shows_defect = False
                for det in result.detections:
                    raw = {
                        "cls": det.cls,
                        "confidence": det.confidence,
                        "explanation": det.explanation,
                        "bbox_px": [round(v, 1) for v in det.bbox_px],
                    }
                    track, is_new = self._ingest(pos, raw, scale)
                    shows_defect = shows_defect or self._verdict(track).category is None
                    if is_new:
                        created.add(track.defect_no)
                    raw["truncated"] = track.sightings[-1].truncated
                    raw["defect_no"] = track.defect_no
                    mapped.append(raw)
                if shows_defect and packet.image is not None:
                    self._evidence[pos.frame] = packet.image
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
                            "image_scale": scale,
                            "detections": mapped,
                        },
                    )
                )
            self.checkpoint = pos.frame

        frame = self.checkpoint
        events += self._sync(
            lambda type_, no: self._key(frame, type_, no),
            lambda no: "detected" if no in created else "updated",
        )
        if self.checkpoint >= 0:
            events.append(self._event(self.checkpoint, "score.updated", self.score_payload()))
        return events

    def run_to_end(self) -> list[RunnerEvent]:
        return self.advance(len(self.track) - 1)

    @property
    def finished(self) -> bool:
        return self.checkpoint >= len(self.track) - 1

    # ------------------------------------------------------------------------------------ decisions
    def decide(self, defect_no: str | None, decision: Mapping[str, Any], key: KeyFn) -> list[RunnerEvent]:
        """Apply one inspector decision and return the events it causes.

        ``decision["action"]`` is one of ``DECISION_ACTIONS``. The target defect's event carries the
        decision, which is how ``restore()`` replays it.
        """
        if decision["action"] == "manual" and "frame" not in decision:
            # Pin the frame in the stored decision so a replay rebuilds the same defect.
            decision = {**decision, "frame": max(self.checkpoint, 0)}
        target = self.apply_decision(defect_no, decision)
        events = self._sync(
            key,
            lambda no: decision["action"] if no == target else "rescored",
            decisions={target: dict(decision)},
        )
        return [*events, RunnerEvent("score.updated", self.score_payload(), key("score.updated", ""))]

    def decide_many(self, defect_nos: Iterable[str], decision: Mapping[str, Any], key: KeyFn) -> list[RunnerEvent]:
        """One decision applied to several defects (e.g. confirm every pending defect up to a yard).

        Each defect's event carries the decision, exactly as if it had been decided on its own, so a
        replay does not need to know about bulk actions. All or nothing: a defect the decision does
        not apply to raises before anything changes.
        """
        numbers = list(dict.fromkeys(defect_nos))
        if decision["action"] == "manual":
            raise DecisionError("missed defects are added one at a time")
        for no in numbers:
            if self._track(no) is None and self._manual(no) is None:
                raise KeyError(no)
            if decision["action"] != "reopen" and self._is_nondefect(no):
                raise DecisionError(f"{no} is a non-defect: promote it to a defect first")
        for no in numbers:
            self.apply_decision(no, decision)
        done = set(numbers)
        events = self._sync(
            key,
            lambda no: decision["action"] if no in done else "rescored",
            decisions={no: dict(decision) for no in numbers},
        )
        return [*events, RunnerEvent("score.updated", self.score_payload(), key("score.updated", ""))]

    def pending_defects(self, up_to_yd: float | None = None) -> list[str]:
        """Defects (not non-defects) still waiting for a decision, optionally only up to a yard."""
        return [
            v["defect_no"]
            for v in sorted(self.views().values(), key=lambda v: (v["center_yd"], v["defect_no"]))
            if v["kind"] == "defect" and v["status"] == "pending" and (up_to_yd is None or v["center_yd"] <= up_to_yd)
        ]

    def _is_nondefect(self, defect_no: str) -> bool:
        track = self._track(defect_no)
        if track is None:
            return False
        state = self.states.get(track.track_no, DefectState())
        return bool(self._verdict(track).category) and not state.promoted

    def apply_decision(self, defect_no: str | None, decision: Mapping[str, Any], *, strict: bool = True) -> str:
        """Change the state of a defect. Returns the defect number it applied to."""
        action = decision["action"]
        if action not in DECISION_ACTIONS:
            raise DecisionError(f"unknown action {action!r}")
        if action == "manual":
            number = defect_no or f"M-{len(self.manual) + 1:02d}"
            self.manual.append(self._manual_defect(number, decision))
            self.manual_states[number] = DefectState(status="confirmed")
            return number

        if defect_no is None:
            raise DecisionError("a defect number is required")
        track = self._track(defect_no)
        manual = self._manual(defect_no)
        if track is None and manual is None:
            raise KeyError(defect_no)
        if track is not None:
            state = self.states.setdefault(track.track_no, DefectState())
            is_nondefect = bool(self._verdict(track).category) and not state.promoted
        else:
            state = self.manual_states.setdefault(defect_no, DefectState(status="confirmed"))
            is_nondefect = False

        if strict and is_nondefect and action not in {"promote", "reopen"}:
            raise DecisionError("this is a non-defect: promote it to a defect first")
        if action == "confirm":
            state.status, state.reject_reason = "confirmed", None
        elif action == "reject":
            state.status, state.reject_reason = "rejected", decision.get("reason_category") or "other"
        elif action == "reclassify":
            state.reclassified_to = self._defect_class(decision["to_cls"])
            state.status, state.reject_reason = "confirmed", None
        elif action == "promote":
            if strict and not is_nondefect:
                raise DecisionError("only non-defects can be promoted")
            state.promoted = True
            to_cls = decision.get("to_cls")
            current = state.reclassified_to or (self.taxonomy.resolve(track.cls) if track else "other_defect")
            if to_cls:
                state.reclassified_to = self._defect_class(to_cls)
            elif self.taxonomy.is_nondefect(current):
                state.reclassified_to = "other_defect"
            state.status, state.reject_reason = "confirmed", None
        elif action == "length":
            state.length_override_in = float(decision["length_in"])
        elif action == "reopen":
            state.status, state.reject_reason = "pending", None
        return defect_no

    def _manual_defect(self, number: str, decision: Mapping[str, Any]) -> ManualDefect:
        cls = self._defect_class(decision["cls"])
        frame = int(decision.get("frame", max(self.checkpoint, 0)))
        note = decision.get("note")
        if decision.get("bbox_px") is not None:
            # Drawn on the video: the box (view pixels of ``frame``) gives position and size.
            if not 0 <= frame < len(self.track):
                raise DecisionError(f"frame {frame} is outside this roll")
            x0, y0, x1, y1 = (float(v) for v in decision["bbox_px"])
            clipped = clip_to_view((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), self.calibration)
            if clipped is None or clipped[2] - clipped[0] < 2 or clipped[3] - clipped[1] < 2:
                raise DecisionError("draw the box around the defect, inside the camera view")
            box = view_to_roll(clipped, self.track[frame], self.calibration)
            length = decision.get("length_in")
            return ManualDefect(
                defect_no=number,
                cls=cls,
                center_yd=box.center_yd,
                across_cm=box.across_center_cm,
                length_in=float(length) if length is not None else box.length_in,
                frame=frame,
                note=note,
                roll_box=box,
                bbox_px=clipped,
            )
        if decision.get("center_yd") is None or decision.get("length_in") is None:
            raise DecisionError("a missed defect needs a box drawn on the video, or a yard and a length")
        return ManualDefect(
            defect_no=number,
            cls=cls,
            center_yd=float(decision["center_yd"]),
            across_cm=float(decision["across_cm"] if decision.get("across_cm") is not None else self._mid_across()),
            length_in=float(decision["length_in"]),
            frame=frame,
            note=note,
        )

    def _defect_class(self, cls: str) -> str:
        resolved = self.taxonomy.resolve(str(cls))
        dc = self.taxonomy.classes.get(resolved)
        if dc is None or dc.kind != "defect":
            raise DecisionError(f"{cls!r} is not a defect class")
        return resolved

    def _mid_across(self) -> float:
        return self.calibration.fabric_width_cm / 2

    def set_status(self, defect_no: str, status: str, reclassify_to: str | None = None) -> None:
        if status not in {"pending", "confirmed", "rejected"}:
            raise ValueError(f"bad status {status!r}")
        action = {"pending": "reopen", "confirmed": "confirm", "rejected": "reject"}[status]
        if reclassify_to:
            action = "reclassify"
        self.apply_decision(defect_no, {"action": action, "to_cls": reclassify_to}, strict=False)

    def confirm_all(self) -> None:
        """Headless helper: accept every detector defect (tests, verification with a perfect preset)."""
        for t in self.deduper.tracks:
            state = self.states.setdefault(t.track_no, DefectState())
            if state.status == "pending":
                state.status = "confirmed"

    # ------------------------------------------------------------------------------------ events
    def views(self) -> dict[str, dict[str, Any]]:
        """Current view of every defect and non-defect, with points from the provisional score."""
        score = self.score(final=False)
        out: dict[str, dict[str, Any]] = {}
        for t in self.deduper.tracks:
            out[t.defect_no] = self._with_score(self.defect_view(t), score)
        for m in self.manual:
            out[m.defect_no] = self._with_score(self.manual_view(m), score)
        return out

    @staticmethod
    def _with_score(view: dict[str, Any], score: ScoreResult | None) -> dict[str, Any]:
        ds: DefectScore | None = score.defects.get(view["defect_no"]) if score else None
        view["points"] = ds.points if ds and not ds.excluded_reason else None
        view["is_continuous"] = bool(ds and ds.continuous)
        view["excluded_reason"] = ds.excluded_reason if ds else None
        view["points_reason"] = ds.reason if ds else None
        return view

    def _sync(
        self,
        key: KeyFn,
        change: Callable[[str], str],
        *,
        decisions: Mapping[str, dict[str, Any]] | None = None,
    ) -> list[RunnerEvent]:
        """One ``defect.upserted`` event for every defect whose view changed since it was last sent.

        A decided defect always gets an event (it carries the decision, which ``restore()`` replays).
        """
        decisions = decisions or {}
        events = []
        for no, view in self.views().items():
            if self._emitted.get(no) == view and no not in decisions:
                continue
            payload: dict[str, Any] = {"defect": view, "change": change(no)}
            if no in decisions:
                payload["decision"] = decisions[no]
            events.append(RunnerEvent("defect.upserted", payload, key("defect.upserted", no)))
            self._emitted[no] = view
        return events

    def restore(self, events: Iterable[tuple[str, Mapping[str, Any]]], checkpoint_frame: int) -> None:
        """Rebuild state from stored events (in ``seq`` order) without calling the detector again."""
        progress = self._progress
        for type_, payload in events:
            if type_ == "detection.batch":
                pos = self.track[int(payload["frame"])]
                scale = float(payload.get("image_scale") or 1.0)
                for det in payload["detections"]:
                    self._ingest(pos, det, scale)
                    progress.detections += 1
            elif type_ == "frame.sampled":
                progress.frames_sampled += 1
                progress.sampled_positions.append(self.track[int(payload["frame"])])
            elif type_ == "defect.upserted":
                decision = payload.get("decision")
                if decision:
                    self.apply_decision(payload["defect"]["defect_no"], decision, strict=False)
                self._emitted[payload["defect"]["defect_no"]] = dict(payload["defect"])
        self.checkpoint = min(checkpoint_frame, len(self.track) - 1)
        if self.checkpoint >= 0:
            seen = self.track[: self.checkpoint + 1]
            progress.frames_processed = len(seen)
            progress.yards_inspected = max(p.bottom_yd for p in seen)
            progress.last_state = seen[-1].state

    # ------------------------------------------------------------------------------------ scoring
    @property
    def yards_inspected(self) -> float:
        return self._progress.yards_inspected

    def position(self, frame: int | None = None) -> FramePosition | None:
        f = self.checkpoint if frame is None else frame
        return self.track[f] if 0 <= f < len(self.track) else None

    def scorable(self) -> list[ScorableDefect]:
        out = []
        views = [self.defect_view(t) for t in self.deduper.tracks] + [self.manual_view(m) for m in self.manual]
        boxes = [t.box for t in self.deduper.tracks] + [m.box for m in self.manual]
        for view, box in zip(views, boxes, strict=True):
            cls = view["current_cls"]
            dc = self.taxonomy.classes.get(cls)
            out.append(
                ScorableDefect(
                    defect_id=view["defect_no"],
                    cls=cls,
                    is_hole=bool(dc and dc.is_hole),
                    length_in=view["length_in"] if view["length_source"] == "inspector" else box.length_in,
                    start_yd=box.start_yd,
                    end_yd=box.end_yd,
                    center_yd=box.center_yd,
                    across_start_cm=box.across_start_cm,
                    across_end_cm=box.across_end_cm,
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

    def counts(self) -> dict[str, int]:
        views = self.views().values()
        defects = [v for v in views if v["kind"] == "defect"]
        return {
            "defects": len(defects),
            "pending": sum(1 for v in defects if v["status"] == "pending"),
            "confirmed": sum(1 for v in defects if v["status"] == "confirmed"),
            "rejected": sum(1 for v in defects if v["status"] == "rejected"),
        }

    def verdict_settled(self) -> bool:
        """True when the defects still pending cannot change the verdict.

        The confirmed-only score is the lowest the roll can get (every pending defect rejected), the
        provisional score the highest (every pending defect confirmed). If both give the same verdict,
        deciding the rest changes the points but not PASS/BORDERLINE/FAIL.
        """
        low, high = self.score(final=True), self.score(final=False)
        return low is not None and high is not None and low.verdict == high.verdict

    def score_payload(self) -> dict[str, Any]:
        s = self.score(final=False)
        final = self.score(final=True)
        p = self.profile
        views = [self.defect_view(t) for t in self.deduper.tracks]
        nondefects: dict[str, int] = {}
        for v in views:
            if v["nondefect_category"]:
                nondefects[v["nondefect_category"]] = nondefects.get(v["nondefect_category"], 0) + 1
        counts = self.counts()
        return {
            "provisional_points": s.total_points if s else 0,
            "per_100_provisional": round(s.per_100, p.per100_rounding) if s else None,
            "provisional_verdict": s.verdict if s else None,
            "confirmed_points": final.total_points if final else 0,
            "per_100_confirmed": round(final.per_100, p.per100_rounding) if final else None,
            "confirmed_verdict": final.verdict if final else None,
            "verdict_settled": bool(s and final and s.verdict == final.verdict),
            "cells": {str(k): v for k, v in s.cells.items()} if s else {},
            "threshold": p.threshold_per_100,
            "borderline_below": p.borderline.below,
            "borderline_above": p.borderline.above,
            "points_budget": round(points_budget(p, self.roll.declared_length_yd, self.roll.width_in), 2)
            if self.roll.declared_length_yd
            else None,
            "yards_inspected": round(self.yards_inspected, 3),
            "at_frame": self.checkpoint,
            "coverage_pct": round(self.coverage() * 100, 1),
            "defects": counts["defects"],
            "pending": counts["pending"],
            "confirmed": counts["confirmed"],
            "rejected": counts["rejected"],
            "nondefects_ignored": nondefects,
        }


def fabric_width_in(fabric_width_cm: float) -> float:
    return fabric_width_cm / INCH_CM
