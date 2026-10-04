"""4-point engine SPEC (PLAN.md §7). Written first in M0; the engine lands in M1 (owner D).

The whole module is skipped until ``threadeye.core.scoring.four_point`` exists. When it lands, these
tests define "done". API contract the M1 implementation must provide:

  threadeye.core.scoring.profile
      RuleProfile.model_validate(dict)        # schema = PLAN.md §7.1
      default_profile() -> RuleProfile        # selvage 1 in ON, continuous 36 in, borderline ±2
      simulator_parity_profile() -> RuleProfile  # bands only; no continuous/selvage/borderline;
                                                 # length_basis = declared (roll_meta values)
  threadeye.core.scoring.four_point
      ScorableDefect(defect_id, cls, is_hole, length_in, start_yd, end_yd, center_yd,
                     across_start_cm, across_end_cm, status="confirmed", kind="defect")
      RollGeometry(length_yd, width_in, fabric_width_cm)
      band_points(length_in, is_hole, profile) -> int
      per_100(total_points, length_yd, width_in) -> float
      score_roll(defects, geometry, profile, *, final=True) -> ScoreResult
          .total_points: int   .per_100: float   .verdict: "PASS"|"BORDERLINE"|"FAIL"
          .cells: dict[int, int]   (yard index -> capped points)
          .defects: dict[str, DefectScore(points, cells, excluded_reason, continuous)]
  threadeye.core.scoring.verdict
      classify(per_100, threshold, below, above, rounding=2) -> "PASS"|"BORDERLINE"|"FAIL"
"""

from __future__ import annotations

import pytest

four_point = pytest.importorskip("threadeye.core.scoring.four_point", reason="4-point engine lands in M1 (owner D)")
from tests.conftest import MICRO_ROLL, SAMPLE_ROLL  # noqa: E402
from threadeye.core.scoring import verdict  # noqa: E402
from threadeye.core.scoring.profile import (  # noqa: E402
    RuleProfile,
    default_profile,
    simulator_parity_profile,
)

D = four_point.ScorableDefect
G = four_point.RollGeometry
FABRIC_CM = 152.4  # 60 in
GEO_60 = G(length_yd=120, width_in=60, fabric_width_cm=FABRIC_CM)


def d(
    did: str,
    cls: str,
    length_in: float,
    center: float,
    *,
    start: float | None = None,
    end: float | None = None,
    across: tuple[float, float] = (70.0, 72.0),
    hole: bool | None = None,
    status: str = "confirmed",
    kind: str = "defect",
) -> object:
    half = length_in / 36 / 2 if start is None else 0
    return D(
        defect_id=did,
        cls=cls,
        is_hole=(cls == "hole") if hole is None else hole,
        length_in=length_in,
        start_yd=center - half if start is None else start,
        end_yd=center + half if end is None else end,
        center_yd=center,
        across_start_cm=across[0],
        across_end_cm=across[1],
        status=status,
        kind=kind,
    )


def profile(**overrides: object) -> RuleProfile:
    base = default_profile().model_dump()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return RuleProfile.model_validate(base)


# ----------------------------------------------------------------------------------------- bands
@pytest.mark.parametrize(
    ("length_in", "is_hole", "points"),
    [
        (0.5, False, 1),
        (3.0, False, 1),
        (2.996, False, 1),
        (3.01, False, 2),
        (6.0, False, 2),
        (6.01, False, 3),
        (9.0, False, 3),
        (9.01, False, 4),
        (30.0, False, 4),
        (0.3, True, 2),
        (1.0, True, 2),
        (1.01, True, 4),
        (5.0, True, 4),
    ],
)
def test_band_points(length_in: float, is_hole: bool, points: int) -> None:
    assert four_point.band_points(length_in, is_hole, default_profile()) == points


# ----------------------------------------------------------------------------------------- per-yard cap
def test_per_yard_cap() -> None:
    r = four_point.score_roll(
        [d("d1", "hole", 0.5, 10.4), d("d2", "stain", 4, 10.7), d("d3", "slub", 2, 10.9)], GEO_60, profile()
    )
    assert r.cells == {10: 4}
    assert r.total_points == 4


def test_center_on_yard_boundary_goes_to_that_yard() -> None:
    r = four_point.score_roll([d("d1", "stain", 4, 7.0)], GEO_60, profile())
    assert r.cells == {7: 2}


# ----------------------------------------------------------------------------------------- continuous
def test_continuous_defect_scores_every_yard_it_touches() -> None:
    r = four_point.score_roll([d("c", "crease_mark", 122.4, 41.9, start=40.2, end=43.6)], GEO_60, profile())
    assert r.cells == {40: 4, 41: 4, 42: 4, 43: 4}
    assert r.total_points == 16
    assert r.defects["c"].continuous is True


def test_continuous_ending_exactly_on_a_yard_line() -> None:
    r = four_point.score_roll([d("c", "crease_mark", 100.8, 41.6, start=40.2, end=43.0)], GEO_60, profile())
    assert sorted(r.cells) == [40, 41, 42]
    assert r.total_points == 12


def test_continuous_by_class_even_when_short() -> None:
    r = four_point.score_roll([d("s", "shade_bar", 10.8, 10.35, start=10.2, end=10.5)], GEO_60, profile())
    assert r.cells == {10: 4}


def test_small_defect_inside_a_continuous_yard_is_capped() -> None:
    r = four_point.score_roll(
        [d("c", "crease_mark", 97.2, 73.85, start=72.5, end=75.2), d("k", "crease_mark", 7, 73.4)],
        GEO_60,
        profile(),
    )
    assert r.total_points == 16
    assert r.cells[73] == 4


# ----------------------------------------------------------------------------------------- selvage
@pytest.mark.parametrize(
    ("across", "enabled", "counted"),
    [
        ((0.5, 2.0), True, False),  # entirely inside the left 1-in band
        ((2.0, 4.0), True, True),  # partly inside → counted
        ((150.5, 152.0), True, False),  # entirely inside the right band (fabric 152.4 cm)
        ((0.5, 2.0), False, True),  # exclusion disabled
    ],
)
def test_selvage_exclusion(across: tuple[float, float], enabled: bool, counted: bool) -> None:
    p = profile(selvage_exclusion={"enabled": enabled})
    r = four_point.score_roll([d("k", "knot", 0.8, 5.5, across=across)], GEO_60, p)
    assert (r.total_points == 1) is counted
    if not counted:
        assert r.defects["k"].excluded_reason


# ----------------------------------------------------------------------------------------- worked example A
def test_worked_example_a() -> None:
    defects = [
        d("d1", "hole", 0.5, 10.4),
        d("d2", "stain", 4, 10.7),
        d("d3", "slub", 2, 10.9),
        d("d4", "crease_mark", 7, 55.2),
        d("d5", "hole", 1.5, 80.1),
        d("d6", "shade_bar", 97.2, 73.85, start=72.5, end=75.2),
        d("d7", "knot", 0.8, 90.3, across=(0.4, 1.3)),
    ]
    r = four_point.score_roll(defects, GEO_60, profile())
    assert r.total_points == 27
    assert r.per_100 == pytest.approx(13.5)
    assert r.verdict == "PASS"
    assert r.defects["d7"].points == 0


def test_per_100_formula() -> None:
    assert four_point.per_100(34, 50, 60) == pytest.approx(40.8)
    assert four_point.per_100(27, 120, 60) == pytest.approx(13.5)
    with pytest.raises(ValueError):
        four_point.per_100(1, 0, 60)


# ----------------------------------------------------------------------------------------- verdict
@pytest.mark.parametrize(
    ("p", "below", "above", "expected"),
    [
        (40.8, 2, 2, "BORDERLINE"),
        (40.8, 0, 0, "FAIL"),
        (39.6, 2, 2, "BORDERLINE"),
        (39.6, 0, 0, "PASS"),
        (38.0, 2, 2, "PASS"),
        (42.0, 2, 2, "BORDERLINE"),
        (42.01, 2, 2, "FAIL"),
        (40.004, 0, 0, "PASS"),
        (40.0, 0, 0, "PASS"),
        (46.45, 0, 0, "FAIL"),
        (46.45, 2, 2, "FAIL"),
    ],
)
def test_verdict_bands(p: float, below: float, above: float, expected: str) -> None:
    assert verdict.classify(p, threshold=40, below=below, above=above) == expected


def test_zero_defects_pass() -> None:
    r = four_point.score_roll([], GEO_60, profile())
    assert (r.total_points, r.per_100, r.verdict) == (0, 0.0, "PASS")


def test_zero_length_roll_is_an_error() -> None:
    with pytest.raises(ValueError):
        four_point.score_roll([], G(length_yd=0, width_in=60, fabric_width_cm=FABRIC_CM), profile())


# ----------------------------------------------------------------------------------------- scoring set
def test_provisional_vs_final_scoring_set() -> None:
    defects = [
        d("c", "stain", 4, 1.5),
        d("p", "stain", 4, 2.5, status="pending"),
        d("r", "stain", 4, 3.5, status="rejected"),
        d("n", "sticker", 2, 4.5, kind="nondefect"),
    ]
    final = four_point.score_roll(defects, GEO_60, profile(), final=True)
    provisional = four_point.score_roll(defects, GEO_60, profile(), final=False)
    assert final.total_points == 2
    assert provisional.total_points == 4


# ----------------------------------------------------------------------------------------- parity profile
def test_parity_profile_has_no_continuous_or_selvage_rule() -> None:
    p = simulator_parity_profile()
    long_defect = d("l", "crease_mark", 40, 5.5, start=4.95, end=6.06, across=(0.2, 1.0))
    r = four_point.score_roll([long_defect], GEO_60, p)
    assert r.cells == {5: 4}  # 4 points in its centre cell only; not excluded by selvage


def _parity_score(dataset):  # type: ignore[no-untyped-def]
    from threadeye.datasets.contracts import validate_dataset

    report, parsed = validate_dataset(dataset, require_media=False)
    assert parsed is not None, report.errors
    m = parsed.meta
    geo = G(length_yd=m.roll_length_yd, width_in=m.fabric_width_in, fabric_width_cm=m.fabric_width_cm)
    defects = [
        D(
            defect_id=g.defect_id,
            cls=g.cls,
            is_hole=g.cls == "hole",
            length_in=g.length_in,
            start_yd=g.start_yd,
            end_yd=g.end_yd,
            center_yd=g.center_yd,
            across_start_cm=g.x0_px / m.px_per_cm,
            across_end_cm=g.x1_px / m.px_per_cm,
        )
        for g in parsed.ground_truth
    ]
    return four_point.score_roll(defects, geo, simulator_parity_profile()), parsed


def test_micro_fixture_parity() -> None:
    r, _ = _parity_score(MICRO_ROLL)
    assert (r.total_points, round(r.per_100, 2), r.verdict) == (7, 142.24, "FAIL")


@pytest.mark.skipif(not (SAMPLE_ROLL / "roll_meta.json").exists(), reason="sample roll not in repo yet")
def test_sample_roll_parity_matches_roll_meta() -> None:
    r, parsed = _parity_score(SAMPLE_ROLL)
    es = parsed.meta.expected_score
    assert r.total_points == es.total_points == 10
    assert round(r.per_100, 2) == round(es.points_per_100_sq_yd, 2) == 46.45
    assert r.verdict == es.verdict == "FAIL"
    for g in parsed.ground_truth:  # per-defect parity with the answer key
        assert r.defects[g.defect_id].points == g.points
