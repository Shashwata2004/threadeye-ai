"""Lot (delivery) verdict (PLAN.md §7.2 step 10).

PENDING_SAMPLE until enough rolls are inspected. Then, while some rolls are still uninspected:
ACCEPT if the fail rate is within the hold limit, else HOLD_INSPECT_ALL. Once every roll is
inspected: REJECT above the reject limit, ACCEPT_WITH_REJECTS if any roll failed, else ACCEPT.
A supervisor confirms the lot decision.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from threadeye.core.scoring.profile import LotRules

LotStatus = Literal["PENDING_SAMPLE", "ACCEPT", "HOLD_INSPECT_ALL", "ACCEPT_WITH_REJECTS", "REJECT"]

__all__ = ["LotResult", "LotRules", "LotStatus", "lot_verdict", "required_sample"]


@dataclass(frozen=True)
class LotResult:
    status: LotStatus
    required_sample: int
    inspected: int
    failed: int
    fail_pct: float


def required_sample(total_rolls: int, rules: LotRules) -> int:
    by_pct = math.ceil(round(total_rolls * rules.min_sample_pct / 100.0, 9))
    return min(total_rolls, max(rules.min_sample_rolls, by_pct)) if total_rolls > 0 else 0


def lot_verdict(total_rolls: int, verdicts: Sequence[str], rules: LotRules) -> LotResult:
    """``verdicts``: one per inspected roll, PASS | FAIL | BORDERLINE (undecided)."""
    required = max(required_sample(total_rolls, rules), 1 if total_rolls else 0)
    inspected = len(verdicts)
    fail_like = {"FAIL", "BORDERLINE"} if rules.borderline_counts_as == "fail" else {"FAIL"}
    failed = sum(1 for v in verdicts if v in fail_like)
    fail_pct = round(failed / inspected * 100.0, 2) if inspected else 0.0

    status: LotStatus
    if inspected < required:
        status = "PENDING_SAMPLE"
    elif inspected < total_rolls:
        status = "ACCEPT" if fail_pct <= rules.hold_if_fail_pct_over else "HOLD_INSPECT_ALL"
    elif fail_pct > rules.reject_if_fail_pct_over:
        status = "REJECT"
    else:
        status = "ACCEPT_WITH_REJECTS" if failed else "ACCEPT"
    return LotResult(status, required, inspected, failed, fail_pct)
