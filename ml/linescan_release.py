"""Line-scan validation selection and non-negotiable release gates (no model installation)."""

from __future__ import annotations

import math


def rendered_pilot_reasons(regression, native, validation, gate):
    if len(regression) != 4:
        return ["pilot: four regression videos required"]
    checks = {
        "native validation precision": native.get("precision", 0)
        >= gate["native_precision_min"],
        "correct broken yarn on original videos": sum(
            r["broken_right"] for r in regression
        )
        >= gate["regression_broken_right_min"],
        "regression detections retained": sum(r["tp"] for r in regression)
        >= gate["regression_tp_min"],
        "regression false alerts": sum(r["fp"] for r in regression)
        <= gate["regression_fp_max"],
        "original-video false alerts": regression[0]["fp"] <= gate["original_fp_max"],
        "original-video correct broken yarn": regression[0]["broken_right"]
        >= gate.get("original_broken_right_min", 0),
        "video validation precision": validation.get("precision", 0)
        >= gate["validation_precision_min"],
        "video validation recall": validation.get("recall", 0)
        >= gate["validation_recall_min"],
        "video validation correct broken yarn": validation.get("broken_right_recall", 0)
        >= gate["validation_broken_right_recall_min"],
    }
    return [
        "pilot: " + name + " did not meet the predeclared improvement condition"
        for name, passed in checks.items()
        if not passed
    ]


def rank_validation(result):
    if result.get("precision", 0) < 0.85:
        return None
    return (
        result.get("broken_right_recall", 0),
        -result.get("false_alarms", 0),
        -result.get("seconds", float("inf")),
    )


def release_reasons(
    regression, validation, final_test, cpu_ratios, *, native_validation=None
):
    reasons = []
    if len(regression) != 4:
        return ["regression: all four frozen videos are required"]
    if sum(r["tp"] for r in regression) < 26:
        reasons.append("regression: fewer than 26/30 defects")
    if sum(r["broken_right"] for r in regression) < 5:
        reasons.append("regression: fewer than 5/7 broken yarn correctly classified")
    if sum(r["fp"] for r in regression) > 14:
        reasons.append("regression: over 14 false alerts")
    if regression[0]["fp"] > 1:
        reasons.append("original video: over one false alert")
    groups = [("validation", validation)]
    if final_test:
        groups.append(("final_test", final_test))
    else:
        reasons.append("final_test: not evaluated because validation did not pass")
    if native_validation is not None:
        groups.append(("native image validation", native_validation))
    for name, metrics in groups:
        if metrics.get("recall", 0) < 0.85:
            reasons.append(name + ": recall below 85%")
        if metrics.get("precision", 0) < 0.85:
            reasons.append(name + ": precision below 85%")
        if metrics.get("broken_right_recall", 0) < 0.8:
            reasons.append(name + ": correct broken-yarn recall below 80%")
    if not cpu_ratios or any(
        not math.isfinite(r) or r <= 0 or r > 1.5 for r in cpu_ratios
    ):
        reasons.append(
            "laptop CPU processing exceeds 1.5x video duration or was not measured"
        )
    return reasons
