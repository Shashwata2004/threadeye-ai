"""4-point scoring engine (PLAN.md §7). Pure functions, no I/O.

Steps: scoring set → selvage exclusion → continuous defects (4 points per yard touched) →
length/hole bands for the rest (cell = floor(center_yd)) → per-yard cap → total → per 100 sq yd →
verdict. Every step leaves a human-readable trail in ``ScoreResult.explanation``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from threadeye.core.scoring.profile import Band, RuleProfile
from threadeye.core.scoring.verdict import Verdict, classify

INCH_CM = 2.54
YARD_IN = 36.0


@dataclass(frozen=True)
class ScorableDefect:
    defect_id: str
    cls: str
    is_hole: bool
    length_in: float
    """Largest dimension of the defect, inches."""
    start_yd: float
    end_yd: float
    center_yd: float
    across_start_cm: float
    across_end_cm: float
    status: str = "confirmed"
    """pending | confirmed | rejected"""
    kind: str = "defect"
    """defect | nondefect"""


@dataclass(frozen=True)
class RollGeometry:
    length_yd: float
    """Yards the score is computed over (inspected or declared, per the profile's length_basis)."""
    width_in: float
    fabric_width_cm: float


@dataclass(frozen=True)
class DefectScore:
    points: int
    """Points this defect contributes before the per-yard cap (0 when excluded or not scored)."""
    cells: tuple[int, ...]
    excluded_reason: str | None
    continuous: bool
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    total_points: int
    per_100: float
    verdict: Verdict
    cells: dict[int, int]
    """Yard index → points after the per-yard cap."""
    uncapped_cells: dict[int, int]
    defects: dict[str, DefectScore]
    threshold: float
    explanation: list[str] = field(default_factory=list)

    @property
    def capped_points(self) -> int:
        return sum(self.uncapped_cells.values()) - self.total_points


def per_100(total_points: float, length_yd: float, width_in: float) -> float:
    """Points per 100 square yards: total × 3600 / (yards × width in inches)."""
    if length_yd <= 0:
        raise ValueError("yards inspected must be > 0")
    if width_in <= 0:
        raise ValueError("fabric width must be > 0")
    return total_points * 3600.0 / (length_yd * width_in)


def _round_to(value: float, step: float) -> float:
    decimals = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    return round(round(value / step) * step, decimals)


def _from_bands(length_in: float, bands: Iterable[Band]) -> int:
    for upper, points in bands:
        if upper is None or length_in <= upper + 1e-9:
            return points
    raise AssertionError("bands must end with an open-ended band")  # guaranteed by RuleProfile


def band_points(length_in: float, is_hole: bool, profile: RuleProfile) -> int:
    rounded = _round_to(length_in, profile.length_rounding_in)
    return _from_bands(rounded, profile.hole_bands_in if is_hole else profile.length_bands_in)


def _last_cell(geometry: RollGeometry) -> int:
    return max(0, math.ceil(geometry.length_yd) - 1)


def _clamp(cell: int, geometry: RollGeometry) -> int:
    return min(max(cell, 0), _last_cell(geometry))


def _in_selvage(d: ScorableDefect, geometry: RollGeometry, profile: RuleProfile) -> bool:
    rule = profile.selvage_exclusion
    band_cm = rule.distance_in * INCH_CM
    right_edge = geometry.fabric_width_cm - band_cm
    if rule.rule == "center_within":
        center = (d.across_start_cm + d.across_end_cm) / 2
        return center <= band_cm or center >= right_edge
    return d.across_end_cm <= band_cm or d.across_start_cm >= right_edge


def _is_continuous(d: ScorableDefect, profile: RuleProfile) -> bool:
    rule = profile.continuous
    if not rule.enabled:
        return False
    along_in = (d.end_yd - d.start_yd) * YARD_IN
    return along_in >= rule.min_along_in or d.cls in rule.classes_always


def _continuous_cells(d: ScorableDefect, geometry: RollGeometry) -> tuple[int, ...]:
    first = math.floor(d.start_yd)
    last = math.ceil(d.end_yd)
    cells = range(first, last) if last > first else range(first, first + 1)
    return tuple(sorted({_clamp(c, geometry) for c in cells}))


def _scored(d: ScorableDefect, final: bool) -> str | None:
    """None if the defect is in the scoring set, else the reason it is not."""
    if d.kind != "defect":
        return "not a defect (shown, not scored)"
    if d.status == "rejected":
        return "rejected by the inspector"
    if d.status == "pending" and final:
        return "not confirmed yet"
    if d.status not in {"pending", "confirmed"}:
        return f"unknown status {d.status!r}"
    return None


def score_roll(
    defects: Iterable[ScorableDefect],
    geometry: RollGeometry,
    profile: RuleProfile,
    *,
    final: bool = True,
) -> ScoreResult:
    """Score one roll. ``final=False`` also counts pending defects (the live, provisional score)."""
    per_defect: dict[str, DefectScore] = {}
    uncapped: dict[int, int] = defaultdict(int)
    explanation: list[str] = []

    for d in defects:
        not_scored = _scored(d, final)
        if not_scored:
            per_defect[d.defect_id] = DefectScore(0, (), not_scored, False, not_scored)
            continue
        if profile.selvage_exclusion.enabled and _in_selvage(d, geometry, profile):
            reason = f"within {profile.selvage_exclusion.distance_in:g} in of the selvage (buyer rule)"
            per_defect[d.defect_id] = DefectScore(0, (), reason, False, reason)
            explanation.append(f"{d.defect_id}: excluded, {reason}")
            continue
        if _is_continuous(d, profile):
            spanned = _continuous_cells(d, geometry)
            pts = profile.continuous.points_per_yard
            for c in spanned:
                uncapped[c] += pts
            reason = f"continuous defect: {pts} points in each of {len(spanned)} yard(s)"
            per_defect[d.defect_id] = DefectScore(pts * len(spanned), spanned, None, True, reason)
            explanation.append(f"{d.defect_id}: {reason} (yards {spanned[0]}–{spanned[-1]})")
            continue
        pts = band_points(d.length_in, d.is_hole, profile)
        cell = _clamp(math.floor(d.center_yd), geometry)
        uncapped[cell] += pts
        kind = "hole" if d.is_hole else "length"
        reason = f"{kind} {d.length_in:.2f} in → {pts} point(s)"
        per_defect[d.defect_id] = DefectScore(pts, (cell,), None, False, reason)
        explanation.append(f"{d.defect_id}: {reason}, yard {cell}")

    cap = profile.max_points_per_yard
    cells = {c: min(cap, p) for c, p in sorted(uncapped.items())}
    for c, p in sorted(uncapped.items()):
        if p > cap:
            explanation.append(f"yard {c}: {p} points capped at {cap}")

    total = sum(cells.values())
    p100 = per_100(total, geometry.length_yd, geometry.width_in)
    verdict = classify(
        p100,
        profile.threshold_per_100,
        profile.borderline.below,
        profile.borderline.above,
        profile.per100_rounding,
    )
    explanation.append(
        f"total {total} points × 3600 / ({geometry.length_yd:g} yd × {geometry.width_in:g} in) "
        f"= {round(p100, profile.per100_rounding)} per 100 sq yd → {verdict} "
        f"(threshold {profile.threshold_per_100:g})"
    )
    return ScoreResult(
        total_points=total,
        per_100=p100,
        verdict=verdict,
        cells=cells,
        uncapped_cells=dict(sorted(uncapped.items())),
        defects=per_defect,
        threshold=profile.threshold_per_100,
        explanation=explanation,
    )


def points_budget(profile: RuleProfile, declared_length_yd: float, width_in: float) -> float:
    """Points the whole roll may carry before failing: T × length × width / 3600 (live meter)."""
    return profile.threshold_per_100 * declared_length_yd * width_in / 3600.0
