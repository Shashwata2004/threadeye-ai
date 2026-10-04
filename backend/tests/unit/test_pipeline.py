"""Pipeline units: coordinate mapping, sampling, de-dup, non-defect filter (PLAN.md §6, §11)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from threadeye.core.dedupe import Deduper, Sighting
from threadeye.core.frames import Calibration, FramePosition
from threadeye.core.geometry import RollBox, clip_to_view, roll_to_view, truncation, view_to_roll
from threadeye.core.nondefect import NonDefectFilter
from threadeye.core.sampling import SamplingConfig, StreamingSampler, coverage, plan
from threadeye.core.taxonomy import load_default_taxonomy

CAL = Calibration(px_per_cm=10, view_region=(0, 0, 1920, 1008), fabric_width_cm=150, selvage_band_px=15)


def pos(frame: int, y: float, *, x0: float = 200.0, state: str = "running", hand: bool = False) -> FramePosition:
    return FramePosition(frame, frame / 30, y, y / 914.4, (y + 1008) / 914.4, 18.0, state, x0, hand)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------- geometry
def test_view_to_roll_follows_the_verified_conventions() -> None:
    box = view_to_roll((600, 100, 640, 180), pos(0, 500.0, x0=200), CAL)
    assert box.along_start_cm == pytest.approx(60.0)  # (500 + 100) / 10
    assert box.along_end_cm == pytest.approx(68.0)
    assert box.across_start_cm == pytest.approx(40.0)  # (600 - 200) / 10
    assert box.across_end_cm == pytest.approx(44.0)
    assert box.length_in == pytest.approx(8.0 / 2.54)


@pytest.mark.parametrize(("x0", "scale"), [(200.0, 1.0), (213.7, 1.0), (180.2, 0.5)])
def test_roll_view_round_trip_with_drift_and_scale(x0: float, scale: float) -> None:
    p = pos(3, 1234.5, x0=x0)
    view = (500.0, 210.0, 560.0, 300.0)
    roll = view_to_roll(tuple(v * scale for v in view), p, CAL, image_scale=scale)  # type: ignore[arg-type]
    assert roll_to_view(roll, p, CAL) == pytest.approx(view)


def test_a_point_on_the_fabric_moves_with_the_fabric() -> None:
    roll = RollBox(100.0, 104.0, 50.0, 52.0)
    a = roll_to_view(roll, pos(0, 0.0, x0=200), CAL)
    b = roll_to_view(roll, pos(10, 300.0, x0=210), CAL)
    assert b[1] == pytest.approx(a[1] - 300)  # moved up by the travel
    assert b[0] == pytest.approx(a[0] + 10)  # drifted with the fabric edge


def test_truncation_and_clipping() -> None:
    assert truncation((10, 0, 50, 40), CAL) == "top"
    assert truncation((10, 990, 50, 1008), CAL) == "bottom"
    assert truncation((10, 0, 50, 1008), CAL) == "both"
    assert truncation((10, 100, 50, 140), CAL) is None
    assert clip_to_view((-10, -5, 30, 20), CAL) == (0.0, 0.0, 30, 20)
    assert clip_to_view((10, 2000, 30, 2100), CAL) is None


def test_rollbox_measures() -> None:
    a = RollBox(0, 10, 0, 10)
    b = RollBox(5, 15, 0, 10)
    assert a.iou(b) == pytest.approx(50 / 150)
    assert a.union(b) == RollBox(0, 15, 0, 10)
    assert RollBox.mean([a, b]) == RollBox(2.5, 12.5, 0, 10)
    with pytest.raises(ValueError):
        RollBox(10, 0, 0, 1)


# ------------------------------------------------------------------------------------------- sampling
def straight_track(n: int = 400, speed: float = 10.0) -> list[FramePosition]:
    return [pos(i, i * speed) for i in range(n)]


def test_samples_by_travel_with_overlap() -> None:
    p = plan(straight_track(), 1008)
    ys = [s.roll_y_top_px for s in p.samples]
    assert p.samples[0].reason == "first"
    gaps = [b - a for a, b in pairwise(ys)]
    assert all(g <= 1008 * 0.95 + 1e-6 for g in gaps)  # never less than min overlap
    assert all(g >= 1008 * 0.85 - 10 for g in gaps[:-1])  # one step apart (last may be shorter)
    assert p.samples[-1].frame == 399
    assert coverage(p, straight_track()) == pytest.approx(1.0)


def test_no_samples_while_stopped() -> None:
    track = [pos(i, min(i, 100) * 10.0, state="stopped" if 100 <= i < 160 else "running") for i in range(160)]
    track += [pos(i, (i - 59) * 10.0) for i in range(160, 300)]
    p = plan(track, 1008)
    assert not any(100 <= s.frame < 160 for s in p.samples)


def test_avoids_the_hand_when_a_clean_frame_is_close() -> None:
    track = [pos(i, i * 10.0, hand=86 <= i <= 88) for i in range(200)]
    p = plan(track, 1008)
    second = p.samples[1]
    assert second.reason == "hand_avoided"
    assert second.frame == 89
    assert second.roll_y_top_px - p.samples[0].roll_y_top_px <= 1008 * 0.95


def test_takes_the_hand_frame_when_no_clean_frame_fits() -> None:
    track = [pos(i, i * 10.0, hand=i >= 86) for i in range(200)]
    p = plan(track, 1008)
    assert p.samples[1].reason == "hand_fallback"
    assert coverage(p, track) == pytest.approx(1.0)


def test_coverage_reports_a_gap_honestly() -> None:
    track = [pos(0, 0.0), pos(1, 5000.0)]  # an impossible jump: 5000 px in one frame
    p = plan(track, 1008)
    assert coverage(p, track) < 1.0


def test_streaming_sampler_agrees_on_a_clean_track() -> None:
    track = straight_track()
    s = StreamingSampler(1008)
    streamed = [p.frame for p in track if s.offer(p)]
    planned = [x.frame for x in plan(track, 1008).samples if x.reason != "last"]
    assert streamed == planned


def test_sampling_config_validation() -> None:
    with pytest.raises(ValueError):
        SamplingConfig(overlap=0.05, min_overlap=0.1)


# ------------------------------------------------------------------------------------------- dedupe
def sighting(frame: int, box: RollBox, cls: str = "stain", **kw: object) -> Sighting:
    return Sighting(frame=frame, box=box, cls=cls, confidence=None, explanation="x", **kw)  # type: ignore[arg-type]


def test_two_sightings_of_one_defect_become_one_track() -> None:
    d = Deduper()
    t1, new1 = d.add(sighting(0, RollBox(100, 104, 40, 44)))
    t2, new2 = d.add(sighting(86, RollBox(100.4, 104.3, 40.2, 44.1)))
    assert new1 and not new2 and t1 is t2
    assert len(d.tracks) == 1
    assert t1.box.along_start_cm == pytest.approx(100.2)  # averaged


def test_near_centres_merge_far_ones_do_not() -> None:
    d = Deduper()
    d.add(sighting(0, RollBox(100, 101, 40, 41)))
    d.add(sighting(5, RollBox(102, 103, 41, 42)))  # centres 2.2 cm apart
    d.add(sighting(9, RollBox(150, 151, 40, 41)))  # 50 cm away
    assert [len(t.sightings) for t in d.tracks] == [2, 1]


def test_running_defect_pieces_are_joined_by_union() -> None:
    d = Deduper()
    d.add(sighting(0, RollBox(50, 150.8, 70, 71), "crease_mark", truncated="bottom"))
    d.add(sighting(86, RollBox(150.8, 230, 70, 71.2), "crease_mark", truncated="both"))
    assert len(d.tracks) == 1
    assert d.tracks[0].box == RollBox(50, 230, 70, 71.2)
    assert d.tracks[0].is_running


def test_truncated_sightings_do_not_shrink_a_fully_seen_box() -> None:
    d = Deduper()
    d.add(sighting(0, RollBox(100, 104, 40, 44)))
    d.add(sighting(9, RollBox(100, 102, 40, 44), truncated="top"))
    assert d.tracks[0].box == RollBox(100, 104, 40, 44)


def test_class_is_a_majority_vote() -> None:
    d = Deduper()
    for i, c in enumerate(["hole", "stain", "hole"]):
        d.add(sighting(i, RollBox(100, 101, 40, 41), c))
    assert d.tracks[0].cls == "hole"
    assert d.tracks[0].defect_no == "D-01"


# ------------------------------------------------------------------------------------------- non-defects
FILTER = NonDefectFilter(load_default_taxonomy(), fabric_width_cm=150, selvage_band_cm=1.5)


def one_track(box: RollBox, cls: str, hand: bool = False):  # type: ignore[no-untyped-def]
    d = Deduper()
    t, _ = d.add(sighting(0, box, cls, hand_visible=hand))
    return t


@pytest.mark.parametrize(
    ("box", "cls", "category"),
    [
        (RollBox(10, 12, 50, 52), "sticker", "sticker"),
        (RollBox(10, 12, -6, -1), "stain", "board"),
        (RollBox(10, 10.4, 0.4, 0.8), "hole", "pin_hole"),
        (RollBox(10, 10.4, 149.2, 149.6), "hole", "pin_hole"),
        (RollBox(10, 13, 0.4, 1.2), "hole", None),  # too big for a pin hole: a real hole
        (RollBox(10, 12, 50, 52), "stain", None),
    ],
)
def test_nondefect_rules(box: RollBox, cls: str, category: str | None) -> None:
    assert FILTER.classify(one_track(box, cls)).category == category


def test_hand_only_sightings_stay_defects_but_are_flagged() -> None:
    v = FILTER.classify(one_track(RollBox(10, 12, 50, 52), "stain", hand=True))
    assert v.category is None and v.uncertain == "hand_in_view"
