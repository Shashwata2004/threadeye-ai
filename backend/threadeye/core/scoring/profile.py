"""Buyer rule profile: every number of the 4-point system is configurable (PLAN.md §7.1).

Profiles are stored as JSON (``rule_profiles.rules``) and validated here. A profile version is
immutable once active, so an old inspection is always re-scored with the rules it was inspected under.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Band = tuple[float | None, int]
"""(upper bound in inches, points). ``None`` = open-ended (the last band)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContinuousRule(_Model):
    enabled: bool = True
    min_along_in: float = Field(36.0, gt=0)
    points_per_yard: int = Field(4, ge=1, le=4)
    classes_always: tuple[str, ...] = ("shade_bar",)


class SelvageRule(_Model):
    enabled: bool = True
    distance_in: float = Field(1.0, ge=0)
    rule: Literal["entirely_within", "center_within"] = "entirely_within"


class BorderlineBand(_Model):
    below: float = Field(2.0, ge=0)
    above: float = Field(2.0, ge=0)


class LengthCheck(_Model):
    tolerance_pct: float = Field(0.5, ge=0)
    tolerance_yd: float = Field(0.25, ge=0)


class WidthCheck(_Model):
    tolerance_in: float = Field(0.5, ge=0)


class LotRules(_Model):
    min_sample_pct: float = Field(10.0, gt=0, le=100)
    min_sample_rolls: int = Field(1, ge=1)
    hold_if_fail_pct_over: float = Field(20.0, ge=0, le=100)
    reject_if_fail_pct_over: float = Field(50.0, ge=0, le=100)
    borderline_counts_as: Literal["fail", "pass"] = "fail"


class CuttingPolicy(_Model):
    min_points_to_cut: int = Field(2, ge=1, le=4)
    margin_in: float = Field(2.0, ge=0)
    min_piece_yd: float = Field(1.0, ge=0)


def _check_bands(bands: tuple[Band, ...]) -> tuple[Band, ...]:
    if not bands:
        raise ValueError("at least one band is required")
    previous = 0.0
    for i, (upper, points) in enumerate(bands):
        if not 1 <= points <= 4:
            raise ValueError(f"band {i}: points must be 1..4")
        last = i == len(bands) - 1
        if upper is None:
            if not last:
                raise ValueError("only the last band may be open-ended (null)")
            continue
        if upper <= previous:
            raise ValueError("band upper bounds must increase")
        previous = upper
    if bands[-1][0] is not None:
        raise ValueError("the last band must be open-ended (null upper bound)")
    return bands


class RuleProfile(_Model):
    name: str = "Default 4-point"
    length_bands_in: tuple[Band, ...] = ((3.0, 1), (6.0, 2), (9.0, 3), (None, 4))
    hole_bands_in: tuple[Band, ...] = ((1.0, 2), (None, 4))
    length_rounding_in: float = Field(0.01, gt=0)
    max_points_per_yard: int = Field(4, ge=1)
    continuous: ContinuousRule = ContinuousRule()
    selvage_exclusion: SelvageRule = SelvageRule()
    threshold_per_100: float = Field(40.0, gt=0)
    borderline: BorderlineBand = BorderlineBand()
    per100_rounding: int = Field(2, ge=0, le=6)
    width_basis: Literal["declared", "measured", "cuttable"] = "declared"
    length_basis: Literal["inspected", "declared"] = "inspected"
    length_check: LengthCheck = LengthCheck()
    width_check: WidthCheck = WidthCheck()
    lot: LotRules = LotRules()
    cutting: CuttingPolicy = CuttingPolicy()
    report_title: str = "4-point inspection report"

    @field_validator("length_bands_in", "hole_bands_in")
    @classmethod
    def _valid_bands(cls, v: tuple[Band, ...]) -> tuple[Band, ...]:
        return _check_bands(v)

    @field_validator("report_title")
    @classmethod
    def _honest_title(cls, v: str) -> str:
        lowered = v.lower()
        if "astm" in lowered or "aql" in lowered:
            raise ValueError("do not claim ASTM/AQL compliance; call it a 4-point inspection report")
        return v

    def rules_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def default_profile() -> RuleProfile:
    """Factory defaults. Values marked "to be validated" by the textile member (PLAN.md §2)."""
    return RuleProfile()


def simulator_parity_profile() -> RuleProfile:
    """The rules the simulator used for ``roll_meta.expected_score`` (verified, PLAN.md §2)."""
    return RuleProfile(
        name="Simulator parity",
        continuous=ContinuousRule(enabled=False),
        selvage_exclusion=SelvageRule(enabled=False),
        borderline=BorderlineBand(below=0.0, above=0.0),
        length_basis="declared",
    )
