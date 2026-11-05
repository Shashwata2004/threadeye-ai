import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from linescan_release import rank_validation, release_reasons, rendered_pilot_reasons


def test_precision_constraint_precedes_recall_and_test_scores():
    assert rank_validation({"precision": 0.84, "broken_right_recall": 1}) is None
    a = rank_validation(
        {"precision": 0.9, "broken_right_recall": 0.8, "false_alarms": 3, "seconds": 4}
    )
    b = rank_validation(
        {"precision": 0.99, "broken_right_recall": 0.7, "false_alarms": 0, "seconds": 1}
    )
    assert a > b


def test_release_requires_every_gate_and_local_cpu_measurement():
    regression = [{"tp": 7, "fp": 0, "broken_right": 2} for _ in range(4)]
    metrics = {"recall": 0.9, "precision": 0.9, "broken_right_recall": 0.85}
    assert release_reasons(regression, metrics, metrics, [1.1, 1.2]) == []
    assert release_reasons(regression, metrics, metrics, [])
    unopened = release_reasons(regression, metrics, {}, [1.1])
    assert any("final_test: not evaluated" in reason for reason in unopened)
    assert not any("final_test: recall below" in reason for reason in unopened)
    assert release_reasons(regression, metrics, metrics, [float("nan")])
    assert release_reasons(
        regression,
        metrics,
        metrics,
        [1.1],
        native_validation={**metrics, "recall": 0.84},
    )
    assert release_reasons(regression[:3], metrics, metrics, [1.1])
    regression[0]["fp"] = 2
    assert any(
        "original video" in r
        for r in release_reasons(regression, metrics, metrics, [1.1])
    )
    assert any(
        "correct broken-yarn" in r
        for r in release_reasons(
            regression, metrics, {**metrics, "broken_right_recall": 0.79}, [1.1]
        )
    )


def test_rendered_pilot_requires_video_improvement_before_full_training():
    gate = {
        "native_precision_min": 0.85,
        "regression_broken_right_min": 1,
        "regression_tp_min": 23,
        "regression_fp_max": 14,
        "original_fp_max": 1,
        "original_broken_right_min": 1,
        "validation_precision_min": 0.4076,
        "validation_recall_min": 0.5333,
        "validation_broken_right_recall_min": 0.4827,
    }
    rows = [{"tp": n, "fp": 0, "broken_right": 0} for n in [5, 3, 7, 8]]
    native = {"precision": 0.99}
    video = {"precision": 0.8, "recall": 0.8, "broken_right_recall": 0.8}
    assert any(
        "correct broken yarn on original videos" in reason
        for reason in rendered_pilot_reasons(rows, native, video, gate)
    )
    rows[0]["broken_right"] = 1
    assert rendered_pilot_reasons(rows, native, video, gate) == []
    rows[0]["broken_right"], rows[3]["broken_right"] = 0, 1
    assert any(
        "original-video correct broken yarn" in reason
        for reason in rendered_pilot_reasons(rows, native, video, gate)
    )
    rows[0]["broken_right"] = 1
    assert rendered_pilot_reasons(rows, native, {**video, "precision": 0.3}, gate)
