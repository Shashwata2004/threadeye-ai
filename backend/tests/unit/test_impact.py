"""Business comparisons must use paired measurements and keep missing evidence unknown."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from threadeye.services.impact import Observation, read_pilot, summarize_pilot


def row(method: str, **changes: object) -> Observation:
    return Observation.model_validate(
        {
            "roll_id": "R1",
            "method": method,
            "seconds": 100,
            "truth_defects": 7,
            "missed_defects": 2,
            "false_alarms": 0,
            **changes,
        }
    )


def test_paired_totals_include_negative_results_and_do_not_invent_yield_or_money() -> None:
    result = summarize_pilot([row("manual"), row("assisted", seconds=120, missed_defects=3)])
    assert result["time_reduction_pct"] == -20
    assert result["missed_reduction_pct"] == -50
    assert result["usable_gain_yd"] is None and result["loss_reduction_bdt"] is None


def test_aggregate_time_uses_totals_not_average_percentages() -> None:
    result = summarize_pilot(
        [
            row("manual", seconds=100),
            row("assisted", seconds=50),
            row("manual", roll_id="R2", seconds=900),
            row("assisted", roll_id="R2", seconds=900),
        ]
    )
    assert result["time_reduction_pct"] == 5


def test_zero_baseline_misses_are_undefined_not_a_hundred_percent_improvement() -> None:
    result = summarize_pilot([row("manual", missed_defects=0), row("assisted", missed_defects=0)])
    assert result["missed_reduction_pct"] is None


def test_yield_and_loss_require_measurements_for_both_methods() -> None:
    result = summarize_pilot(
        [
            row("manual", usable_yd=80, loss_bdt=500),
            row("assisted", usable_yd=82, loss_bdt=600),
        ]
    )
    assert result["usable_gain_yd"] == 2
    assert result["loss_reduction_bdt"] == -100


@pytest.mark.parametrize(
    "observations",
    [[], [row("manual")], [row("manual"), row("manual")], [row("manual"), row("assisted", truth_defects=8)]],
)
def test_invalid_comparisons_are_rejected(observations: list[Observation]) -> None:
    with pytest.raises(ValueError):
        summarize_pilot(observations)


@pytest.mark.parametrize(
    "changes",
    [
        {"seconds": 0},
        {"seconds": float("nan")},
        {"seconds": float("inf")},
        {"missed_defects": 8},
        {"loss_bdt": -1},
        {"truth_defects": 1.5},
    ],
)
def test_impossible_measurements_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        row("manual", **changes)


def test_blank_optional_csv_fields_remain_unknown(tmp_path: Path) -> None:
    path = tmp_path / "pilot.csv"
    path.write_text(
        "roll_id,method,seconds,truth_defects,missed_defects,false_alarms,usable_yd,loss_bdt\n"
        "R1,manual,100,7,2,0,,\nR1,assisted,80,7,1,1,,\n"
    )
    result = summarize_pilot(read_pilot(path))
    assert result["time_reduction_pct"] == 20
    assert result["missed_reduction_pct"] == 50
    assert result["loss_reduction_bdt"] is None
