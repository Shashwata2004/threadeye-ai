from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_model_candidates import compare, markdown


def evidence() -> tuple[dict, dict, dict, dict]:
    before = {"model_sha256": "old", "rolls": [{"dataset": "sample", "sha256": {"roll_video.mp4": "same", "model_info.json": "old"},
              "inference_threads": 2, "evaluation": {"tp": 4, "fp": 0, "fn": 3, "recall": 4 / 7, "precision": 1}}]}
    after = copy.deepcopy(before)
    after["model_sha256"] = "new"
    after["rolls"][0]["evaluation"].update(tp=6, fn=1, recall=6 / 7)
    tiles = {"tiles": 100, "defects": 20, "found_any_class": 0.5, "found_right_class": 0.4, "precision": 0.8,
             "false_alarms_per_100_tiles": 1, "nondefects_called_defect": 0,
             "per_class": {"broken_yarn": {"recall": 0.3}, "crease_mark": {"recall": 0.5}}}
    return before, after, tiles, copy.deepcopy(tiles)


def test_better_roll_detection_with_stable_overall_results_qualifies() -> None:
    assert compare(*evidence())["qualified_for_review"]


def test_fewer_misses_alone_does_not_justify_more_false_alarms() -> None:
    before, after, tiles, newer = evidence()
    after["rolls"][0]["evaluation"]["fp"] = 2
    result = compare(before, after, tiles, newer)
    assert not result["qualified_for_review"]
    assert "roll-suite false alarms increased" in result["reasons"]


def test_comparison_rejects_changed_video_or_test_population() -> None:
    before, after, tiles, newer = evidence()
    after["rolls"][0]["sha256"]["roll_video.mp4"] = "different"
    with pytest.raises(ValueError, match="input changed"):
        compare(before, after, tiles, newer)
    before, after, tiles, newer = evidence()
    newer["tiles"] += 1
    with pytest.raises(ValueError, match="population changed"):
        compare(before, after, tiles, newer)


def test_overall_regression_blocks_candidate_even_if_demo_improves() -> None:
    before, after, tiles, newer = evidence()
    newer["found_any_class"] = 0.45
    assert not compare(before, after, tiles, newer)["qualified_for_review"]


def test_more_detections_cannot_hide_worse_roll_scoring() -> None:
    before, after, tiles, newer = evidence()
    before["rolls"][0]["decision_replay"] = {"verdict_agrees": True, "model_per_100": 35, "oracle_per_100": 36}
    after["rolls"][0]["decision_replay"] = {"verdict_agrees": False, "model_per_100": 45, "oracle_per_100": 36}
    result = compare(before, after, tiles, newer)
    assert not result["qualified_for_review"]
    assert "roll score error increased" in result["reasons"]


def test_bangla_report_shows_old_video_and_overall_results() -> None:
    before, after, tiles, newer = evidence()
    before["rolls"][0]["dataset"] = after["rolls"][0]["dataset"] = "linescan_roll"
    text = markdown(compare(before, after, tiles, newer), before, after, tiles, newer)
    assert "4/7" in text and "6/7" in text
    assert "আগের একই সামগ্রিক test dataset" in text
    assert "স্বয়ংক্রিয়ভাবে অ্যাপে বসায় না" in text
