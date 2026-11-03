import pytest

from threadeye.core.cutting import CutDefect, cutting_sheet
from threadeye.core.scoring.profile import CuttingPolicy


def test_margins_merge_overlaps_and_remove_short_pieces() -> None:
    plan = cutting_sheet(
        10,
        [CutDefect(2, 3, 2), CutDefect(3.2, 4, 3), CutDefect(8.8, 9, 4)],
        CuttingPolicy(margin_in=3.6, min_piece_yd=1),
    )
    assert plan["usable_yd"] == 6.5
    assert plan["skipped_yd"] == 3.5
    assert plan["segments"] == [
        {"start_yd": 0, "end_yd": 1.9, "action": "keep"},
        {"start_yd": 1.9, "end_yd": 4.1, "action": "skip"},
        {"start_yd": 4.1, "end_yd": 8.700000000000001, "action": "keep"},
        {"start_yd": 8.700000000000001, "end_yd": 10, "action": "skip"},
    ]


def test_low_point_defects_are_not_cut_and_short_entire_roll_is_not_usable() -> None:
    assert cutting_sheet(10, [CutDefect(2, 3, 1)], CuttingPolicy())["usable_yd"] == 10
    assert cutting_sheet(0.5, [], CuttingPolicy())["usable_yd"] == 0


def test_outside_defects_and_clipping_preserve_length() -> None:
    plan = cutting_sheet(10, [CutDefect(-2, -1, 4), CutDefect(9, 12, 4)], CuttingPolicy(margin_in=0))
    assert plan["usable_yd"] == 9
    assert plan["skipped_yd"] == 1


@pytest.mark.parametrize("length", [0, -1, float("nan"), float("inf")])
def test_bad_lengths_are_rejected(length: float) -> None:
    with pytest.raises(ValueError):
        cutting_sheet(length, [], CuttingPolicy())


def test_invalid_defect_positions_are_rejected() -> None:
    with pytest.raises(ValueError):
        cutting_sheet(10, [CutDefect(5, 3, 4)], CuttingPolicy())
