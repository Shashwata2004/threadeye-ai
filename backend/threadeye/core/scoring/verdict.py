"""Roll verdict from points per 100 sq yd (PLAN.md §7.2 step 7).

PASS if p ≤ T − b₋ · BORDERLINE if T − b₋ < p ≤ T + b₊ · FAIL if p > T + b₊, with p rounded first.
With b₋ = b₊ = 0 this is the standard rule: ≤ T passes, > T fails.
"""

from __future__ import annotations

from typing import Literal

Verdict = Literal["PASS", "BORDERLINE", "FAIL"]


def classify(per_100: float, threshold: float, below: float, above: float, rounding: int = 2) -> Verdict:
    p = round(per_100, rounding)
    if p <= round(threshold - below, rounding):
        return "PASS"
    if p <= round(threshold + above, rounding):
        return "BORDERLINE"
    return "FAIL"
