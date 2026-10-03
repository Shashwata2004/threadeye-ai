"""Lot (delivery) verdict SPEC (PLAN.md §7.2 step 10). Written first in M0; implemented in M1 (owner D).

API contract:
  threadeye.core.scoring.lot.lot_verdict(total_rolls, verdicts, rules) -> LotResult
      verdicts: roll verdicts of inspected rolls: "PASS" | "FAIL" | "BORDERLINE" (undecided)
      rules: LotRules (PLAN.md §7.1 `lot:` block)
      LotResult.status: PENDING_SAMPLE | ACCEPT | HOLD_INSPECT_ALL | ACCEPT_WITH_REJECTS | REJECT
      LotResult.required_sample, .inspected, .failed, .fail_pct
"""

from __future__ import annotations

import pytest

lot = pytest.importorskip("threadeye.core.scoring.lot", reason="lot verdict lands in M1 (owner D)")

RULES = lot.LotRules(
    min_sample_pct=10,
    min_sample_rolls=1,
    hold_if_fail_pct_over=20,
    reject_if_fail_pct_over=50,
    borderline_counts_as="fail",
)


@pytest.mark.parametrize(
    ("total", "verdicts", "status"),
    [
        (30, ["PASS", "PASS"], "PENDING_SAMPLE"),
        (30, ["PASS"] * 3, "ACCEPT"),
        (30, ["PASS", "PASS", "FAIL"], "HOLD_INSPECT_ALL"),
        (30, ["PASS", "PASS", "BORDERLINE"], "HOLD_INSPECT_ALL"),
        (30, ["FAIL"] * 4 + ["PASS"] * 26, "ACCEPT_WITH_REJECTS"),
        (30, ["FAIL"] * 16 + ["PASS"] * 14, "REJECT"),
    ],
)
def test_lot_verdict(total: int, verdicts: list[str], status: str) -> None:
    assert lot.lot_verdict(total, verdicts, RULES).status == status


def test_required_sample_has_a_floor() -> None:
    r = lot.lot_verdict(5, [], RULES)
    assert r.required_sample == 1
    assert r.status == "PENDING_SAMPLE"


def test_fail_pct_reported() -> None:
    r = lot.lot_verdict(30, ["PASS", "PASS", "FAIL"], RULES)
    assert (r.inspected, r.failed) == (3, 1)
    assert r.fail_pct == pytest.approx(33.33, abs=0.01)
