"""Simulated detector, runner (incl. resume equivalence), evaluation, and end-to-end on the fixture."""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest

from tests.conftest import MICRO_ROLL, SAMPLE_ROLL
from threadeye.core.evaluation import Prediction, TruthDefect, TruthNuisance, evaluate
from threadeye.core.frames import FramePacket
from threadeye.core.geometry import RollBox
from threadeye.core.providers import ProviderContext, ProviderNotConfigured
from threadeye.core.runner import RollSpec, Runner
from threadeye.core.scoring.profile import default_profile, simulator_parity_profile
from threadeye.datasets.answer_key import load_answer_key
from threadeye.providers.simulated import PERFECT, REALISTIC, SimulatedDetector
from threadeye.services.benchmark import run_roll
from threadeye.sources.simulated_roll import TrackFrameSource


def make_runner(config=PERFECT, inspection_id: str = "t") -> Runner:  # type: ignore[no-untyped-def]
    key = load_answer_key(MICRO_ROLL, require_media=False)
    source = TrackFrameSource(MICRO_ROLL)
    meta = source.parsed.meta
    det = SimulatedDetector(config, ProviderContext(answer_key=key))
    return Runner(
        source,
        det,
        simulator_parity_profile(),
        RollSpec(width_in=meta.fabric_width_in, declared_length_yd=meta.roll_length_yd),
        inspection_id=inspection_id,
    )


def defects_of(r: Runner) -> list[tuple[str, str, str | None, float, float]]:
    return [
        (v["defect_no"], v["current_cls"], v["nondefect_category"], v["center_yd"], v["length_in"])
        for v in (r.defect_view(t) for t in r.deduper.tracks)
    ]


# ------------------------------------------------------------------------------------------- detector
def test_simulated_detector_needs_its_answer_key_and_prepare() -> None:
    det = SimulatedDetector(PERFECT, ProviderContext())
    source = TrackFrameSource(MICRO_ROLL)
    with pytest.raises(ProviderNotConfigured):
        det.prepare(source.open())
    with pytest.raises(ValueError, match="unknown"):
        SimulatedDetector({"miss_rat": 0.1}, ProviderContext())


def test_simulated_detector_is_deterministic_and_order_independent() -> None:
    key = load_answer_key(MICRO_ROLL, require_media=False)
    source = TrackFrameSource(MICRO_ROLL)
    info = source.open()
    track = source.track()
    frames = [0, 86, 150, 204]

    def run(order: list[int]) -> dict[int, list[tuple[object, ...]]]:
        det = SimulatedDetector(REALISTIC, ProviderContext(answer_key=key))
        det.prepare(info)
        return {
            f: [(d.cls, d.bbox_px, d.explanation) for d in det.detect(FramePacket(track[f])).detections] for f in order
        }

    assert run(frames) == run(list(reversed(frames)))
    det = SimulatedDetector(PERFECT, ProviderContext(answer_key=key))
    det.prepare(info)
    assert all(d.confidence is None for d in det.detect(FramePacket(track[0])).detections)


def test_miss_rate_one_finds_nothing_and_flag_rate_one_raises_false_alarms() -> None:
    r = make_runner({**PERFECT, "miss_rate": 1.0, "nuisance_flag_rate": 1.0})
    r.run_to_end()
    views = [r.defect_view(t) for t in r.deduper.tracks]
    assert all("FALSE ALARM" in v["explanation"] for v in views)
    assert {v["current_cls"] for v in views} == {"slub"}  # the loose thread, misread as a slub


# ------------------------------------------------------------------------------------------- runner
def test_run_to_end_matches_the_fixture_answer() -> None:
    r = make_runner()
    events = r.run_to_end()
    r.confirm_all()
    score = r.score(final=True)
    assert score is not None
    assert (score.total_points, round(score.per_100, 2), score.verdict) == (7, 142.24, "FAIL")
    assert len({e.idempotency_key for e in events}) == len(events)
    assert r.advance(204) == []  # already processed: idempotent


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_resuming_in_pieces_gives_the_same_result(seed: int) -> None:
    """The pure core of the power-loss guarantee: any split of the work gives identical output."""
    whole = make_runner(REALISTIC)
    whole_events = whole.run_to_end()

    pieces = make_runner(REALISTIC)
    cuts = [*sorted(random.Random(seed).sample(range(1, 204), 6)), 204]
    piece_events = []
    for c in cuts:
        piece_events += pieces.advance(c)

    assert defects_of(pieces) == defects_of(whole)
    whole_score, piece_score = whole.score(), pieces.score()
    assert whole_score and piece_score and whole_score.total_points == piece_score.total_points
    sampled = [e.idempotency_key for e in whole_events if e.type == "frame.sampled"]
    assert sampled == [e.idempotency_key for e in piece_events if e.type == "frame.sampled"]


def test_score_payload_counts_ignored_nondefects() -> None:
    r = make_runner()
    events = r.run_to_end()
    last = [e for e in events if e.type == "score.updated"][-1].payload
    assert last["nondefects_ignored"] == {"loose_thread": 1}
    assert last["coverage_pct"] == 100.0
    assert last["points_budget"] == pytest.approx(40 * 3.0 * 59.055 / 3600, abs=0.01)


# ------------------------------------------------------------------------------------------- evaluation
def test_evaluation_explains_false_positives() -> None:
    truths = [
        TruthDefect("G1", "hole", RollBox(10, 11, 40, 41), 2),
        TruthDefect("G2", "stain", RollBox(80, 90, 60, 70), 2),
    ]
    nuisances = [TruthNuisance("sticker", RollBox(50, 55, 1, 4))]
    preds = [
        Prediction("P1", "knot", RollBox(10.2, 11.1, 40, 41), True),  # matches G1, wrong class
        Prediction("P2", "stain", RollBox(51, 54, 1.5, 3.5), True),  # the sticker: false alarm
        Prediction("P3", "loose_thread", RollBox(30, 31, 30, 31), False, "loose_thread"),
    ]
    r = evaluate(preds, truths, nuisances, fabric_width_cm=150, selvage_band_cm=1.5)
    assert (r.tp, r.fp, r.fn) == (1, 1, 1)
    assert r.precision == 0.5 and r.recall == 0.5
    assert r.class_accuracy == 0.0
    assert r.fp_by_type == {"sticker": 1}
    assert r.missed == ["G2"]
    assert r.nondefects_ignored == {"loose_thread": 1}
    assert r.recall_per_class == {"hole": 1.0, "stain": 0.0}


# ------------------------------------------------------------------------------------------- end to end
def test_benchmark_service_on_the_fixture() -> None:
    run = run_roll(MICRO_ROLL)
    assert run.matches_expected
    assert run.truth_score.total_points == run.expected["total_points"]
    assert run.evaluation.recall == 1.0 and run.evaluation.precision == 1.0
    assert run.frames_sampled / run.frames < 0.05


def test_realistic_runs_are_reproducible() -> None:
    a = run_roll(MICRO_ROLL, preset="realistic", profile=default_profile())
    b = run_roll(MICRO_ROLL, preset="realistic", profile=default_profile())
    assert a.defects == b.defects and a.score.total_points == b.score.total_points


def test_video_source_gives_the_same_result(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    roll = tmp_path / "roll"
    shutil.copytree(MICRO_ROLL, roll)
    writer = cv2.VideoWriter(str(roll / "roll_video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1920, 1044))
    for i in range(205):
        frame = np.full((1044, 1920, 3), (120, 70, 30), dtype=np.uint8)
        cv2.putText(frame, f"SIMULATED FEED {i}", (40, 1030), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    run = run_roll(roll, use_video=True)
    assert run.matches_expected
    sampled = [e for e in run.events if e.type == "frame.sampled"]
    assert sampled and not any(e.payload["image"] for e in sampled)  # simulated detector needs no pixels


@pytest.mark.skipif(not (SAMPLE_ROLL / "roll_meta.json").exists(), reason="sample roll not in repo yet")
def test_sample_roll_end_to_end_matches_roll_meta() -> None:
    run = run_roll(SAMPLE_ROLL)
    assert (run.score.total_points, round(run.score.per_100, 2), run.score.verdict) == (10, 46.45, "FAIL")
    assert run.matches_expected
    assert run.evaluation.recall == 1.0
